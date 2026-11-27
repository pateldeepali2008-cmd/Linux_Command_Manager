// ============================================================
// Linux Command Manager - Frontend JavaScript (fetch & DOM)
// ============================================================

// Global array to store all loaded commands
let allCommands = [];
let currentCategory = 'All';
let isEditing = false; // Tracks whether modal is in "Add" or "Edit" mode

// DOM Elements
const commandsGrid = document.getElementById('commandsGrid');
const searchInput = document.getElementById('searchInput');
const categoryFilters = document.getElementById('categoryFilters');
const commandCountText = document.getElementById('commandCountText');
const emptyState = document.getElementById('emptyState');

// Modal Elements
const commandModal = document.getElementById('commandModal');
const modalTitle = document.getElementById('modalTitle');
const commandForm = document.getElementById('commandForm');
const commandNameInput = document.getElementById('commandName');
const commandCategorySelect = document.getElementById('commandCategory');
const commandDescriptionInput = document.getElementById('commandDescription');
const openAddModalBtn = document.getElementById('openAddModalBtn');
const closeModalBtn = document.getElementById('closeModalBtn');
const cancelModalBtn = document.getElementById('cancelModalBtn');
const nameHelp = document.getElementById('nameHelp');

// Toast Element
const toastContainer = document.getElementById('toastContainer');

// ------------------------------------------------------------
// 1. Fetch & Load Commands from Flask GET API
// ------------------------------------------------------------
async function loadCommands() {
    try {
        const response = await fetch('/api/commands');
        if (!response.ok) {
            throw new Error('Failed to fetch commands');
        }
        allCommands = await response.json();
        filterAndRender();
    } catch (error) {
        console.error('Error loading commands:', error);
        showToast('Error loading commands from server', 'error');
    }
}

// ------------------------------------------------------------
// 2. Filter & Render Commands
// ------------------------------------------------------------
function filterAndRender() {
    const searchTerm = searchInput.value.trim().toLowerCase();

    // Filter by search term AND selected category
    const filtered = allCommands.filter(cmd => {
        const nameMatch = cmd.name.toLowerCase().includes(searchTerm);
        const descMatch = cmd.description.toLowerCase().includes(searchTerm);
        const matchesSearch = nameMatch || descMatch;

        const cmdCategory = cmd.category || 'General';
        const matchesCategory = currentCategory === 'All' || cmdCategory.toLowerCase() === currentCategory.toLowerCase();

        return matchesSearch && matchesCategory;
    });

    renderCommands(filtered);
}

function renderCommands(commands) {
    commandsGrid.innerHTML = '';

    // Update count text
    commandCountText.textContent = `Showing ${commands.length} command${commands.length === 1 ? '' : 's'}`;

    if (commands.length === 0) {
        emptyState.classList.remove('hidden');
        return;
    } else {
        emptyState.classList.add('hidden');
    }

    commands.forEach(cmd => {
        const card = document.createElement('div');
        card.className = 'command-card';

        const categoryClass = getBadgeClass(cmd.category || 'General');

        card.innerHTML = `
            <div class="card-top">
                <div class="card-header">
                    <span class="command-name">${escapeHtml(cmd.name)}</span>
                    <span class="badge ${categoryClass}">${escapeHtml(cmd.category || 'General')}</span>
                </div>
                <p class="command-desc">${escapeHtml(cmd.description)}</p>
            </div>
            <div class="card-actions">
                <button class="btn btn-copy" onclick="copyCommand('${escapeHtml(cmd.name)}')">
                    📋 Copy
                </button>
                <div class="card-actions-left">
                    <button class="btn btn-action" onclick="openEditModal('${escapeHtml(cmd.name)}')">
                        ✏️ Edit
                    </button>
                    <button class="btn btn-action btn-delete" onclick="deleteCommand('${escapeHtml(cmd.name)}')">
                        🗑️ Delete
                    </button>
                </div>
            </div>
        `;

        commandsGrid.appendChild(card);
    });
}

// Category badge color helper
function getBadgeClass(category) {
    const cat = category.toLowerCase();
    switch (cat) {
        case 'files': return 'badge-files';
        case 'permissions': return 'badge-permissions';
        case 'networking': return 'badge-networking';
        case 'git': return 'badge-git';
        case 'processes': return 'badge-processes';
        default: return 'badge-general';
    }
}

// ------------------------------------------------------------
// 3. Search & Category Filter Listeners
// ------------------------------------------------------------
searchInput.addEventListener('input', () => {
    filterAndRender();
});

categoryFilters.addEventListener('click', (e) => {
    if (e.target.classList.contains('filter-pill')) {
        // Remove active class from all pills
        document.querySelectorAll('.filter-pill').forEach(pill => pill.classList.remove('active'));
        // Add active class to clicked pill
        e.target.classList.add('active');
        currentCategory = e.target.dataset.category;
        filterAndRender();
    }
});

// ------------------------------------------------------------
// 4. Copy Command to Clipboard
// ------------------------------------------------------------
function copyCommand(name) {
    navigator.clipboard.writeText(name)
        .then(() => {
            showToast(`Copied "${name}" to clipboard!`, 'success');
        })
        .catch(() => {
            showToast('Failed to copy', 'error');
        });
}

// ------------------------------------------------------------
// 5. Modal Handling: Add & Edit
// ------------------------------------------------------------
function openAddModal() {
    isEditing = false;
    modalTitle.textContent = 'Add New Command';
    commandNameInput.value = '';
    commandNameInput.disabled = false;
    commandCategorySelect.value = 'General';
    commandDescriptionInput.value = '';
    nameHelp.textContent = 'Linux command name (e.g. ls, grep, ps)';
    commandModal.classList.remove('hidden');
    commandNameInput.focus();
}

function openEditModal(name) {
    const cmd = allCommands.find(c => c.name.toLowerCase() === name.toLowerCase());
    if (!cmd) return;

    isEditing = true;
    modalTitle.textContent = `Edit Command: ${cmd.name}`;
    commandNameInput.value = cmd.name;
    commandNameInput.disabled = true; // Name cannot be changed during edit
    commandCategorySelect.value = cmd.category || 'General';
    commandDescriptionInput.value = cmd.description;
    nameHelp.textContent = 'Command name cannot be changed.';
    commandModal.classList.remove('hidden');
    commandDescriptionInput.focus();
}

function closeModal() {
    commandModal.classList.add('hidden');
}

openAddModalBtn.addEventListener('click', openAddModal);
closeModalBtn.addEventListener('click', closeModal);
cancelModalBtn.addEventListener('click', closeModal);

// Close modal when clicking outside of modal card
commandModal.addEventListener('click', (e) => {
    if (e.target === commandModal) {
        closeModal();
    }
});

// ------------------------------------------------------------
// 6. Submit Form (POST or PUT via fetch)
// ------------------------------------------------------------
commandForm.addEventListener('submit', async (e) => {
    e.preventDefault();

    const name = commandNameInput.value.trim();
    const category = commandCategorySelect.value;
    const description = commandDescriptionInput.value.trim();

    if (!description) {
        showToast('Description is required', 'error');
        return;
    }

    if (!isEditing && !name) {
        showToast('Command name is required', 'error');
        return;
    }

    try {
        if (!isEditing) {
            // ---- POST Request (Add new) ----
            const response = await fetch('/api/commands', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name, category, description })
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || 'Failed to add command');
            }

            showToast(`Command "${name}" added successfully!`, 'success');

            // Reset category filter to 'All' so new command is immediately visible
            currentCategory = 'All';
            document.querySelectorAll('.filter-pill').forEach(pill => {
                pill.classList.toggle('active', pill.dataset.category === 'All');
            });
            searchInput.value = '';
        } else {
            // ---- PUT Request (Update existing) ----
            const response = await fetch(`/api/commands/${encodeURIComponent(name)}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ category, description })
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || 'Failed to update command');
            }

            showToast(`Command "${name}" updated successfully!`, 'success');
        }

        closeModal();
        loadCommands(); // Reload updated list
    } catch (error) {
        showToast(error.message, 'error');
    }
});

// ------------------------------------------------------------
// 7. Delete Command (DELETE via fetch)
// ------------------------------------------------------------
async function deleteCommand(name) {
    const confirmed = confirm(`Are you sure you want to delete the command "${name}"?`);
    if (!confirmed) return;

    try {
        const response = await fetch(`/api/commands/${encodeURIComponent(name)}`, {
            method: 'DELETE'
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || 'Failed to delete command');
        }

        showToast(`Command "${name}" deleted!`, 'success');
        loadCommands(); // Reload updated list
    } catch (error) {
        showToast(error.message, 'error');
    }
}

// ------------------------------------------------------------
// 8. Toast Notifications
// ------------------------------------------------------------
function showToast(message, type = 'success') {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = (type === 'success' ? '✓ ' : '✕ ') + message;

    toastContainer.appendChild(toast);

    setTimeout(() => {
        toast.remove();
    }, 3000);
}

// HTML Escape helper to prevent XSS
function escapeHtml(str) {
    if (!str) return '';
    return str.toString()
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

// ------------------------------------------------------------
// 9. Initial Load on Page Startup
// ------------------------------------------------------------
document.addEventListener('DOMContentLoaded', loadCommands);
