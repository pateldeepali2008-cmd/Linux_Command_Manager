import os
import json
import sqlite3
from flask import Flask, jsonify, request, render_template

app = Flask(__name__)

# Database file path
DB_FILE = "commands.db"
JSON_BACKUP_FILE = "commands.json"

# Helper function: Get a SQLite database connection
def get_db_connection():
    """Connects to SQLite database and returns rows as dictionary-like objects."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row  # row['name'] access karne ke liye
    return conn

# Database Initialization & Auto-Migration from commands.json
def init_db():
    """Creates tables if they don't exist and migrates existing JSON commands."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Create commands table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS commands (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            description TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'General'
        )
    """)
    conn.commit()

    # Check if table is empty; if so, populate from commands.json
    cursor.execute("SELECT COUNT(*) FROM commands")
    count = cursor.fetchone()[0]

    if count == 0 and os.path.exists(JSON_BACKUP_FILE):
        try:
            with open(JSON_BACKUP_FILE, "r") as f:
                json_data = json.load(f)
            for item in json_data:
                name = item.get("name", "").strip()
                desc = item.get("description", "").strip()
                cat = item.get("category", "General").strip()
                if name and desc:
                    cursor.execute(
                        "INSERT OR IGNORE INTO commands (name, description, category) VALUES (?, ?, ?)",
                        (name, desc, cat if cat else "General")
                    )
            conn.commit()
            print("Successfully migrated data from commands.json to SQLite database!")
        except Exception as e:
            print("Error migrating from JSON:", e)

    conn.close()

# Initialize DB on app startup
init_db()

# ----------------- ROUTES ----------------- #

# Frontend Dashboard
@app.route("/")
def home():
    return render_template("index.html")

# 1. GET API - Retrieve all commands from SQLite
@app.route("/api/commands", methods=["GET"])
def get_commands():
    conn = get_db_connection()
    rows = conn.execute("SELECT id, name, description, category FROM commands ORDER BY id ASC").fetchall()
    conn.close()

    # Convert sqlite rows to regular python list of dicts
    commands = [dict(row) for row in rows]
    return jsonify(commands)

# 2. POST API - Add a new command to SQLite
@app.route("/api/commands", methods=["POST"])
def add_command():
    new_command = request.get_json()

    # Input validation
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
    cursor = conn.cursor()

    # Duplicate check (case-insensitive in SQLite)
    existing = cursor.execute(
        "SELECT id FROM commands WHERE LOWER(name) = LOWER(?)",
        (cmd_name,)
    ).fetchone()

    if existing:
        conn.close()
        return jsonify({"error": f"Command '{cmd_name}' already exists!"}), 409

    # Insert into database
    cursor.execute(
        "INSERT INTO commands (name, description, category) VALUES (?, ?, ?)",
        (cmd_name, cmd_description, cmd_category)
    )
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()

    new_entry = {
        "id": new_id,
        "name": cmd_name,
        "description": cmd_description,
        "category": cmd_category
    }

    return jsonify({
        "message": "Command added successfully to database",
        "command": new_entry
    }), 201

# 3. PUT API - Update an existing command in SQLite
@app.route("/api/commands/<string:name>", methods=["PUT"])
def update_command(name):
    update_data = request.get_json()

    if not update_data:
        return jsonify({"error": "Request body must be a valid JSON"}), 400

    conn = get_db_connection()
    target_name = name.strip()

    # Find the command
    existing = conn.execute(
        "SELECT id, name, description, category FROM commands WHERE LOWER(name) = LOWER(?)",
        (target_name,)
    ).fetchone()

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

    # Update in SQLite
    conn.execute(
        "UPDATE commands SET description = ?, category = ? WHERE id = ?",
        (new_desc, new_cat, cmd_id)
    )
    conn.commit()
    conn.close()

    updated_entry = {
        "id": cmd_id,
        "name": existing["name"],
        "description": new_desc,
        "category": new_cat
    }

    return jsonify({
        "message": f"Command '{existing['name']}' updated successfully in database",
        "command": updated_entry
    }), 200

# 4. DELETE API - Remove a command from SQLite
@app.route("/api/commands/<string:name>", methods=["DELETE"])
def delete_command(name):
    conn = get_db_connection()
    target_name = name.strip()

    # Find command
    existing = conn.execute(
        "SELECT id, name FROM commands WHERE LOWER(name) = LOWER(?)",
        (target_name,)
    ).fetchone()

    if not existing:
        conn.close()
        return jsonify({"error": f"Command '{name}' not found"}), 404

    # Delete from SQLite
    conn.execute("DELETE FROM commands WHERE id = ?", (existing["id"],))
    conn.commit()
    conn.close()

    return jsonify({
        "message": f"Command '{existing['name']}' deleted successfully from database"
    }), 200

if __name__ == "__main__":
    app.run(debug=True)
