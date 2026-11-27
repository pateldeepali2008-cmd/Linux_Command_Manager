import os
import json
import sqlite3
from flask import Flask, jsonify, request, render_template

app = Flask(__name__)

# Check if PostgreSQL Database URL is provided (Render sets this automatically)
DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    # SQLAlchemy / psycopg2 compatibility fix for Render
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

IS_POSTGRES = bool(DATABASE_URL)

if IS_POSTGRES:
    import psycopg2
    from psycopg2.extras import RealDictCursor

# Files
SQLITE_DB_FILE = "commands.db"
JSON_BACKUP_FILE = "commands.json"
PARAM = "%s" if IS_POSTGRES else "?"

# Helper function: Get Database Connection
def get_db_connection():
    """Returns a connection to PostgreSQL (on Render) or SQLite (locally)."""
    if IS_POSTGRES:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    else:
        conn = sqlite3.connect(SQLITE_DB_FILE)
        conn.row_factory = sqlite3.Row
        return conn

def get_cursor(conn):
    """Returns a cursor that produces dictionary-like rows."""
    if IS_POSTGRES:
        return conn.cursor(cursor_factory=RealDictCursor)
    return conn.cursor()

# Helper function: Sync database state back to commands.json as backup
def sync_to_json(commands_list):
    """Saves updated commands back to commands.json so backup is always fresh."""
    try:
        with open(JSON_BACKUP_FILE, "w") as f:
            json.dump(commands_list, f, indent=4)
    except Exception as e:
        print("Warning: could not sync to JSON:", e)

# Database Initialization & Auto-Migration from commands.json
def init_db():
    """Initializes tables and seeds data from commands.json if table is empty."""
    conn = get_db_connection()
    cursor = get_cursor(conn)

    # 1. Create commands table
    if IS_POSTGRES:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS commands (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) UNIQUE NOT NULL,
                description TEXT NOT NULL,
                category VARCHAR(100) NOT NULL DEFAULT 'General'
            );
        """)
    else:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS commands (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                description TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'General'
            );
        """)
    conn.commit()

    # 2. Check if table is empty
    cursor.execute("SELECT COUNT(*) FROM commands;")
    row = cursor.fetchone()
    count = row["count"] if (IS_POSTGRES and isinstance(row, dict)) else row[0]

    # 3. Seed data from commands.json if database is fresh
    if count == 0 and os.path.exists(JSON_BACKUP_FILE):
        try:
            with open(JSON_BACKUP_FILE, "r") as f:
                json_data = json.load(f)
            for item in json_data:
                name = item.get("name", "").strip()
                desc = item.get("description", "").strip()
                cat = item.get("category", "General").strip()
                if name and desc:
                    if IS_POSTGRES:
                        cursor.execute(
                            "INSERT INTO commands (name, description, category) VALUES (%s, %s, %s) ON CONFLICT (name) DO NOTHING;",
                            (name, desc, cat if cat else "General")
                        )
                    else:
                        cursor.execute(
                            "INSERT OR IGNORE INTO commands (name, description, category) VALUES (?, ?, ?);",
                            (name, desc, cat if cat else "General")
                        )
            conn.commit()
            print("Successfully initialized database and migrated commands from commands.json!")
        except Exception as e:
            print("Migration error:", e)

    conn.close()

# Run initialization on startup
init_db()

# ----------------- ROUTES ----------------- #

@app.route("/")
def home():
    return render_template("index.html")

# 1. GET API - Retrieve all commands
@app.route("/api/commands", methods=["GET"])
def get_commands():
    conn = get_db_connection()
    cursor = get_cursor(conn)
    cursor.execute("SELECT id, name, description, category FROM commands ORDER BY id ASC;")
    rows = cursor.fetchall()
    conn.close()

    commands = [dict(row) for row in rows]
    return jsonify(commands)

# 2. POST API - Add a new command
@app.route("/api/commands", methods=["POST"])
def add_command():
    new_command = request.get_json()

    if not new_command or "name" not in new_command or "description" not in new_command:
        return jsonify({"error": "Both 'name' and 'description' are required"}), 400

    cmd_name = new_command["name"].strip()
    cmd_description = new_command["description"].strip()
    cmd_category = new_command.get("category", "General").strip()
    if not cmd_category:
        cmd_category = "General"

    if not cmd_name or not cmd_description:
        return jsonify({"error": "'name' and 'description' cannot be empty"}), 400

    conn = get_db_connection()
    cursor = get_cursor(conn)

    # Duplicate check (case-insensitive)
    cursor.execute(f"SELECT id FROM commands WHERE LOWER(name) = LOWER({PARAM});", (cmd_name,))
    existing = cursor.fetchone()

    if existing:
        conn.close()
        return jsonify({"error": f"Command '{cmd_name}' already exists!"}), 409

    # Insert into database
    if IS_POSTGRES:
        cursor.execute(
            "INSERT INTO commands (name, description, category) VALUES (%s, %s, %s) RETURNING id;",
            (cmd_name, cmd_description, cmd_category)
        )
        new_id = cursor.fetchone()["id"]
    else:
        cursor.execute(
            "INSERT INTO commands (name, description, category) VALUES (?, ?, ?);",
            (cmd_name, cmd_description, cmd_category)
        )
        new_id = cursor.lastrowid

    conn.commit()

    # Fetch updated list to sync JSON backup
    cursor.execute("SELECT name, description, category FROM commands ORDER BY id ASC;")
    all_cmds = [dict(r) for r in cursor.fetchall()]
    conn.close()

    sync_to_json(all_cmds)

    new_entry = {
        "id": new_id,
        "name": cmd_name,
        "description": cmd_description,
        "category": cmd_category
    }

    return jsonify({
        "message": "Command added successfully",
        "command": new_entry
    }), 201

# 3. PUT API - Update an existing command
@app.route("/api/commands/<string:name>", methods=["PUT"])
def update_command(name):
    update_data = request.get_json()

    if not update_data:
        return jsonify({"error": "Request body must be a valid JSON"}), 400

    conn = get_db_connection()
    cursor = get_cursor(conn)
    target_name = name.strip()

    cursor.execute(f"SELECT id, name, description, category FROM commands WHERE LOWER(name) = LOWER({PARAM});", (target_name,))
    existing = cursor.fetchone()

    if not existing:
        conn.close()
        return jsonify({"error": f"Command '{name}' not found"}), 404

    cmd_id = existing["id"]
    new_desc = existing["description"]
    new_cat = existing["category"]

    if "description" in update_data:
        desc_val = update_data["description"].strip()
        if not desc_val:
            conn.close()
            return jsonify({"error": "'description' cannot be empty"}), 400
        new_desc = desc_val

    if "category" in update_data:
        cat_val = update_data["category"].strip()
        if cat_val:
            new_cat = cat_val

    cursor.execute(
        f"UPDATE commands SET description = {PARAM}, category = {PARAM} WHERE id = {PARAM};",
        (new_desc, new_cat, cmd_id)
    )
    conn.commit()

    # Sync JSON
    cursor.execute("SELECT name, description, category FROM commands ORDER BY id ASC;")
    all_cmds = [dict(r) for r in cursor.fetchall()]
    conn.close()

    sync_to_json(all_cmds)

    return jsonify({
        "message": f"Command '{existing['name']}' updated successfully",
        "command": {
            "id": cmd_id,
            "name": existing["name"],
            "description": new_desc,
            "category": new_cat
        }
    }), 200

# 4. DELETE API - Delete a command
@app.route("/api/commands/<string:name>", methods=["DELETE"])
def delete_command(name):
    conn = get_db_connection()
    cursor = get_cursor(conn)
    target_name = name.strip()

    cursor.execute(f"SELECT id, name FROM commands WHERE LOWER(name) = LOWER({PARAM});", (target_name,))
    existing = cursor.fetchone()

    if not existing:
        conn.close()
        return jsonify({"error": f"Command '{name}' not found"}), 404

    cursor.execute(f"DELETE FROM commands WHERE id = {PARAM};", (existing["id"],))
    conn.commit()

    # Sync JSON
    cursor.execute("SELECT name, description, category FROM commands ORDER BY id ASC;")
    all_cmds = [dict(r) for r in cursor.fetchall()]
    conn.close()

    sync_to_json(all_cmds)

    return jsonify({
        "message": f"Command '{existing['name']}' deleted successfully"
    }), 200

if __name__ == "__main__":
    app.run(debug=True)
