"""Status UI routes for displaying emulator state with authentication and management.

Provides a web interface to view the status of all services and objects
in the OpenStack emulator, with authentication support and CRUD operations.
"""

import uuid
from datetime import datetime, timezone
from typing import TypedDict

import httpx
from fastapi import APIRouter, Cookie, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from emulator.core.database import db
from emulator.core.models import (
    FloatingIP,
    FloatingIPStatus,
    GlanceImage,
    ImageStatus,
    ImageVisibility,
    Network,
    NetworkStatus,
    Port,
    PortStatus,
    Project,
    Router,
    RouterStatus,
    SecurityGroup,
    Server,
    ServerStatus,
    Snapshot,
    SnapshotStatus,
    Subnet,
    User,
    Volume,
    VolumeStatus,
)

router = APIRouter()


class ServiceInfo(TypedDict):
    port: int
    name: str


# Service configuration (must match emulator/__init__.py)
SERVICES: dict[str, ServiceInfo] = {
    "keystone": {"port": 5000, "name": "Identity"},
    "nova": {"port": 8774, "name": "Compute"},
    "cinder": {"port": 8776, "name": "Block Storage"},
    "glance": {"port": 9292, "name": "Image"},
    "neutron": {"port": 9696, "name": "Networking"},
}


# Pydantic models for API requests
class LoginRequest(BaseModel):
    username: str
    password: str
    project_name: str | None = None


class ServerCreateRequest(BaseModel):
    name: str
    flavor_id: str
    image_id: str | None = None
    network_id: str | None = None


class VolumeCreateRequest(BaseModel):
    name: str
    size: int
    description: str | None = None
    volume_type: str | None = None


class NetworkCreateRequest(BaseModel):
    name: str
    admin_state_up: bool = True
    shared: bool = False
    external: bool = False


class SubnetCreateRequest(BaseModel):
    name: str
    network_id: str
    cidr: str
    ip_version: int = 4
    gateway_ip: str | None = None
    enable_dhcp: bool = True


class RouterCreateRequest(BaseModel):
    name: str
    admin_state_up: bool = True
    external_network_id: str | None = None


class FloatingIPCreateRequest(BaseModel):
    floating_network_id: str
    port_id: str | None = None


class SecurityGroupCreateRequest(BaseModel):
    name: str
    description: str | None = None


class ProjectCreateRequest(BaseModel):
    name: str
    description: str | None = None
    enabled: bool = True


class UserCreateRequest(BaseModel):
    name: str
    password: str
    email: str | None = None
    enabled: bool = True


class ImageCreateRequest(BaseModel):
    name: str
    disk_format: str = "qcow2"
    container_format: str = "bare"
    visibility: str = "public"


class KeypairCreateRequest(BaseModel):
    name: str
    public_key: str | None = None


class SnapshotCreateRequest(BaseModel):
    name: str
    volume_id: str
    description: str | None = None


# CSS styles for the status page
CSS_STYLES = """
<style>
    * {
        box-sizing: border-box;
        margin: 0;
        padding: 0;
    }
    body {
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        background: #f5f5f5;
        color: #333;
        line-height: 1.6;
    }
    .container {
        max-width: 1400px;
        margin: 0 auto;
        padding: 20px;
    }
    header {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        color: white;
        padding: 30px 0;
        margin-bottom: 30px;
    }
    header h1 {
        font-size: 2rem;
        margin-bottom: 5px;
    }
    header p {
        opacity: 0.8;
    }
    .service-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
        gap: 20px;
        margin-bottom: 30px;
    }
    .service-card {
        background: white;
        border-radius: 12px;
        padding: 20px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        border-left: 4px solid #667eea;
    }
    .service-card.offline {
        border-left-color: #e53e3e;
        opacity: 0.7;
    }
    .service-card h3 {
        display: flex;
        align-items: center;
        gap: 10px;
        margin-bottom: 10px;
    }
    .status-dot {
        width: 12px;
        height: 12px;
        border-radius: 50%;
        background: #48bb78;
    }
    .status-dot.offline {
        background: #e53e3e;
    }
    .service-info {
        font-size: 0.9rem;
        color: #666;
    }
    .section {
        background: white;
        border-radius: 12px;
        padding: 25px;
        margin-bottom: 20px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
    }
    .section h2 {
        color: #1a1a2e;
        margin-bottom: 20px;
        padding-bottom: 10px;
        border-bottom: 2px solid #eee;
    }
    .resource-group {
        margin-bottom: 25px;
    }
    .resource-group h3 {
        color: #4a5568;
        font-size: 1.1rem;
        margin-bottom: 15px;
        display: flex;
        align-items: center;
        gap: 10px;
    }
    .resource-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 15px;
    }
    .resource-header h3 {
        margin-bottom: 0;
    }
    .count-badge {
        background: #667eea;
        color: white;
        padding: 2px 10px;
        border-radius: 12px;
        font-size: 0.8rem;
    }
    table {
        width: 100%;
        border-collapse: collapse;
        font-size: 0.9rem;
    }
    th, td {
        text-align: left;
        padding: 12px;
        border-bottom: 1px solid #eee;
    }
    th {
        background: #f8f9fa;
        font-weight: 600;
        color: #4a5568;
    }
    tr:hover {
        background: #f8f9fa;
    }
    .status-badge {
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 0.8rem;
        font-weight: 500;
    }
    .status-active, .status-available, .status-healthy {
        background: #c6f6d5;
        color: #22543d;
    }
    .status-build, .status-creating {
        background: #fef3c7;
        color: #92400e;
    }
    .status-error, .status-failed {
        background: #fed7d7;
        color: #9b2c2c;
    }
    .status-down, .status-shutoff {
        background: #e2e8f0;
        color: #4a5568;
    }
    .empty-state {
        text-align: center;
        padding: 40px;
        color: #718096;
    }
    .uuid {
        font-family: monospace;
        font-size: 0.85rem;
        color: #666;
    }
    .refresh-btn, .btn {
        background: #667eea;
        color: white;
        border: none;
        padding: 10px 20px;
        border-radius: 8px;
        cursor: pointer;
        font-size: 0.9rem;
        text-decoration: none;
        display: inline-block;
    }
    .refresh-btn:hover, .btn:hover {
        background: #5a67d8;
    }
    .btn-sm {
        padding: 6px 12px;
        font-size: 0.8rem;
    }
    .btn-success {
        background: #48bb78;
    }
    .btn-success:hover {
        background: #38a169;
    }
    .btn-danger {
        background: #e53e3e;
    }
    .btn-danger:hover {
        background: #c53030;
    }
    .btn-secondary {
        background: #718096;
    }
    .btn-secondary:hover {
        background: #5a6775;
    }
    .header-actions {
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    .tabs {
        display: flex;
        gap: 5px;
        margin-bottom: 20px;
        border-bottom: 2px solid #eee;
        padding-bottom: 5px;
    }
    .tab {
        padding: 10px 20px;
        border: none;
        background: none;
        cursor: pointer;
        font-size: 0.95rem;
        color: #666;
        border-bottom: 2px solid transparent;
        margin-bottom: -7px;
    }
    .tab:hover {
        color: #333;
    }
    .tab.active {
        color: #667eea;
        border-bottom-color: #667eea;
    }
    .tab-content {
        display: none;
    }
    .tab-content.active {
        display: block;
    }
    /* Authentication styles */
    .auth-section {
        display: flex;
        align-items: center;
        gap: 15px;
    }
    .user-info {
        display: flex;
        align-items: center;
        gap: 10px;
        color: white;
    }
    .user-info .user-icon {
        width: 36px;
        height: 36px;
        background: #667eea;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: bold;
    }
    .login-btn {
        background: rgba(255,255,255,0.2);
        color: white;
        border: 1px solid rgba(255,255,255,0.3);
        padding: 8px 16px;
        border-radius: 6px;
        cursor: pointer;
        font-size: 0.9rem;
    }
    .login-btn:hover {
        background: rgba(255,255,255,0.3);
    }
    .logout-btn {
        background: transparent;
        color: #fca5a5;
        border: 1px solid #fca5a5;
        padding: 6px 12px;
        border-radius: 6px;
        cursor: pointer;
        font-size: 0.85rem;
    }
    .logout-btn:hover {
        background: rgba(252, 165, 165, 0.1);
    }
    /* Modal styles */
    .modal {
        display: none;
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0, 0, 0, 0.5);
        z-index: 1000;
        align-items: center;
        justify-content: center;
    }
    .modal.active {
        display: flex;
    }
    .modal-content {
        background: white;
        border-radius: 12px;
        padding: 30px;
        width: 90%;
        max-width: 500px;
        max-height: 90vh;
        overflow-y: auto;
        box-shadow: 0 20px 50px rgba(0, 0, 0, 0.3);
    }
    .modal-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 20px;
        padding-bottom: 15px;
        border-bottom: 1px solid #eee;
    }
    .modal-header h3 {
        font-size: 1.25rem;
        color: #1a1a2e;
    }
    .modal-close {
        background: none;
        border: none;
        font-size: 1.5rem;
        cursor: pointer;
        color: #666;
        padding: 0;
        line-height: 1;
    }
    .modal-close:hover {
        color: #333;
    }
    .form-group {
        margin-bottom: 20px;
    }
    .form-group label {
        display: block;
        margin-bottom: 6px;
        font-weight: 500;
        color: #4a5568;
    }
    .form-group input, .form-group select, .form-group textarea {
        width: 100%;
        padding: 10px 12px;
        border: 1px solid #e2e8f0;
        border-radius: 6px;
        font-size: 0.95rem;
        transition: border-color 0.2s;
    }
    .form-group input:focus, .form-group select:focus, .form-group textarea:focus {
        outline: none;
        border-color: #667eea;
        box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
    }
    .form-group input[type="checkbox"] {
        width: auto;
        margin-right: 8px;
    }
    .form-group .checkbox-label {
        display: flex;
        align-items: center;
        cursor: pointer;
    }
    .form-actions {
        display: flex;
        gap: 10px;
        justify-content: flex-end;
        margin-top: 25px;
        padding-top: 20px;
        border-top: 1px solid #eee;
    }
    .form-error {
        background: #fed7d7;
        color: #9b2c2c;
        padding: 10px 15px;
        border-radius: 6px;
        margin-bottom: 15px;
        font-size: 0.9rem;
    }
    .form-success {
        background: #c6f6d5;
        color: #22543d;
        padding: 10px 15px;
        border-radius: 6px;
        margin-bottom: 15px;
        font-size: 0.9rem;
    }
    /* Action buttons in tables */
    .action-btns {
        display: flex;
        gap: 5px;
    }
    .action-btn {
        padding: 4px 8px;
        font-size: 0.75rem;
        border-radius: 4px;
        cursor: pointer;
        border: none;
        color: white;
    }
    .action-btn.edit {
        background: #667eea;
    }
    .action-btn.delete {
        background: #e53e3e;
    }
    .action-btn:hover {
        opacity: 0.9;
    }
    /* Toast notifications */
    .toast-container {
        position: fixed;
        top: 20px;
        right: 20px;
        z-index: 2000;
    }
    .toast {
        background: #1a1a2e;
        color: white;
        padding: 15px 20px;
        border-radius: 8px;
        margin-bottom: 10px;
        box-shadow: 0 4px 15px rgba(0, 0, 0, 0.2);
        animation: slideIn 0.3s ease;
    }
    .toast.success {
        background: #48bb78;
    }
    .toast.error {
        background: #e53e3e;
    }
    @keyframes slideIn {
        from {
            transform: translateX(100%);
            opacity: 0;
        }
        to {
            transform: translateX(0);
            opacity: 1;
        }
    }
    /* Read-only notice */
    .readonly-notice {
        background: #fef3c7;
        color: #92400e;
        padding: 12px 20px;
        border-radius: 8px;
        margin-bottom: 20px;
        display: flex;
        align-items: center;
        gap: 10px;
    }
    .readonly-notice svg {
        flex-shrink: 0;
    }
</style>
"""

# JavaScript for interactivity
JS_SCRIPT = """
<script>
    // Tab switching
    function switchTab(tabName) {
        document.querySelectorAll('.tab-content').forEach(el => {
            el.classList.remove('active');
        });
        document.querySelectorAll('.tab').forEach(el => {
            el.classList.remove('active');
        });
        document.getElementById('tab-' + tabName).classList.add('active');
        document.querySelector('[data-tab="' + tabName + '"]').classList.add('active');
    }

    // Modal functions
    function openModal(modalId) {
        document.getElementById(modalId).classList.add('active');
        document.body.style.overflow = 'hidden';
    }

    function closeModal(modalId) {
        document.getElementById(modalId).classList.remove('active');
        document.body.style.overflow = '';
        // Clear form errors
        const errorEl = document.querySelector('#' + modalId + ' .form-error');
        if (errorEl) errorEl.style.display = 'none';
    }

    // Close modal on backdrop click
    document.querySelectorAll('.modal').forEach(modal => {
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                modal.classList.remove('active');
                document.body.style.overflow = '';
            }
        });
    });

    // Toast notifications
    function showToast(message, type = 'success') {
        const container = document.getElementById('toast-container');
        const toast = document.createElement('div');
        toast.className = 'toast ' + type;
        toast.textContent = message;
        container.appendChild(toast);
        setTimeout(() => {
            toast.remove();
        }, 4000);
    }

    // Login form submission
    async function handleLogin(event) {
        event.preventDefault();
        const form = event.target;
        const errorEl = document.getElementById('login-error');
        errorEl.style.display = 'none';

        const data = {
            username: form.username.value,
            password: form.password.value,
            project_name: form.project_name.value || null
        };

        try {
            const response = await fetch('/api/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });

            if (response.ok) {
                location.reload();
            } else {
                const result = await response.json();
                errorEl.textContent = result.detail || 'Login failed';
                errorEl.style.display = 'block';
            }
        } catch (error) {
            errorEl.textContent = 'Network error. Please try again.';
            errorEl.style.display = 'block';
        }
    }

    // Logout
    async function handleLogout() {
        try {
            await fetch('/api/logout', { method: 'POST' });
            location.reload();
        } catch (error) {
            showToast('Logout failed', 'error');
        }
    }

    // Generic resource creation
    async function createResource(resourceType, formId, modalId) {
        const form = document.getElementById(formId);
        const errorEl = document.querySelector('#' + modalId + ' .form-error');
        if (errorEl) errorEl.style.display = 'none';

        const formData = new FormData(form);
        const data = {};
        formData.forEach((value, key) => {
            if (value !== '') {
                // Handle checkboxes and numbers
                if (form.elements[key].type === 'checkbox') {
                    data[key] = form.elements[key].checked;
                } else if (form.elements[key].type === 'number') {
                    data[key] = parseInt(value, 10);
                } else {
                    data[key] = value;
                }
            }
        });

        try {
            const response = await fetch('/api/' + resourceType, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });

            if (response.ok) {
                closeModal(modalId);
                showToast(resourceType.slice(0, -1).charAt(0).toUpperCase() + resourceType.slice(0, -1).slice(1) + ' created successfully');
                setTimeout(() => location.reload(), 1000);
            } else {
                const result = await response.json();
                if (errorEl) {
                    errorEl.textContent = result.detail || 'Creation failed';
                    errorEl.style.display = 'block';
                } else {
                    showToast(result.detail || 'Creation failed', 'error');
                }
            }
        } catch (error) {
            if (errorEl) {
                errorEl.textContent = 'Network error. Please try again.';
                errorEl.style.display = 'block';
            } else {
                showToast('Network error', 'error');
            }
        }
    }

    // Generic resource deletion
    async function deleteResource(resourceType, resourceId, resourceName) {
        if (!confirm('Are you sure you want to delete "' + resourceName + '"?')) {
            return;
        }

        try {
            const response = await fetch('/api/' + resourceType + '/' + resourceId, {
                method: 'DELETE'
            });

            if (response.ok) {
                showToast('Deleted successfully');
                setTimeout(() => location.reload(), 1000);
            } else {
                const result = await response.json();
                showToast(result.detail || 'Deletion failed', 'error');
            }
        } catch (error) {
            showToast('Network error', 'error');
        }
    }

    // Server actions
    async function serverAction(serverId, action) {
        try {
            const response = await fetch('/api/servers/' + serverId + '/action', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action: action })
            });

            if (response.ok) {
                showToast('Action "' + action + '" executed');
                setTimeout(() => location.reload(), 1000);
            } else {
                const result = await response.json();
                showToast(result.detail || 'Action failed', 'error');
            }
        } catch (error) {
            showToast('Network error', 'error');
        }
    }

    // Auto-refresh every 30 seconds (only if no modal is open)
    setTimeout(function() {
        if (!document.querySelector('.modal.active')) {
            location.reload();
        }
    }, 30000);
</script>
"""


async def check_service_health(host: str, port: int) -> bool:
    """Check if a service is healthy by calling its health endpoint."""
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(f"http://{host}:{port}/health")
            return bool(response.status_code == 200)
    except Exception:
        return False


def get_status_class(status: str) -> str:
    """Get CSS class for a status value."""
    status_lower = status.lower()
    if status_lower in ("active", "available", "healthy", "up"):
        return "status-active"
    elif status_lower in ("build", "creating", "pending"):
        return "status-build"
    elif status_lower in ("error", "failed"):
        return "status-error"
    elif status_lower in ("down", "shutoff", "deleted"):
        return "status-down"
    return ""


def get_current_user(auth_token: str | None) -> dict | None:
    """Get current user from auth token."""
    if not auth_token:
        return None
    token = db.validate_token(auth_token)
    if not token:
        return None
    return {
        "id": token.user_id,
        "name": token.user_name,
        "project_id": token.project_id,
        "project_name": token.project_name,
    }


def render_servers_table(servers: list, authenticated: bool) -> str:
    """Render the servers table HTML."""
    if not servers:
        return '<div class="empty-state">No servers created yet</div>'

    rows = ""
    for server in servers:
        status = server.status.value if hasattr(server.status, "value") else str(server.status)
        status_class = get_status_class(status)
        created = getattr(server, "created", None)
        created_str = created.strftime("%Y-%m-%d %H:%M:%S") if created else "-"

        actions = ""
        if authenticated:
            actions = f"""
            <td class="action-btns">
                <button class="action-btn edit" onclick="serverAction('{server.id}', 'start')" title="Start">Start</button>
                <button class="action-btn edit" onclick="serverAction('{server.id}', 'stop')" title="Stop">Stop</button>
                <button class="action-btn delete" onclick="deleteResource('servers', '{server.id}', '{server.name}')" title="Delete">Delete</button>
            </td>
            """

        rows += f"""
        <tr>
            <td class="uuid">{server.id[:8]}...</td>
            <td>{server.name}</td>
            <td><span class="status-badge {status_class}">{status}</span></td>
            <td>{server.flavor_id}</td>
            <td>{created_str}</td>
            {actions}
        </tr>
        """

    action_header = "<th>Actions</th>" if authenticated else ""
    return f"""
    <table>
        <thead>
            <tr>
                <th>ID</th>
                <th>Name</th>
                <th>Status</th>
                <th>Flavor</th>
                <th>Created</th>
                {action_header}
            </tr>
        </thead>
        <tbody>{rows}</tbody>
    </table>
    """


def render_volumes_table(volumes: list, authenticated: bool) -> str:
    """Render the volumes table HTML."""
    if not volumes:
        return '<div class="empty-state">No volumes created yet</div>'

    rows = ""
    for volume in volumes:
        status = volume.status.value if hasattr(volume.status, "value") else str(volume.status)
        status_class = get_status_class(status)

        actions = ""
        if authenticated:
            actions = f"""
            <td class="action-btns">
                <button class="action-btn delete" onclick="deleteResource('volumes', '{volume.id}', '{volume.name or volume.id[:8]}')" title="Delete">Delete</button>
            </td>
            """

        rows += f"""
        <tr>
            <td class="uuid">{volume.id[:8]}...</td>
            <td>{volume.name or '-'}</td>
            <td><span class="status-badge {status_class}">{status}</span></td>
            <td>{volume.size} GB</td>
            <td>{volume.volume_type or 'default'}</td>
            {actions}
        </tr>
        """

    action_header = "<th>Actions</th>" if authenticated else ""
    return f"""
    <table>
        <thead>
            <tr>
                <th>ID</th>
                <th>Name</th>
                <th>Status</th>
                <th>Size</th>
                <th>Type</th>
                {action_header}
            </tr>
        </thead>
        <tbody>{rows}</tbody>
    </table>
    """


def render_images_table(images: list, authenticated: bool) -> str:
    """Render the images table HTML."""
    if not images:
        return '<div class="empty-state">No images available</div>'

    rows = ""
    for image in images:
        status = image.status.value if hasattr(image.status, "value") else str(image.status)
        status_class = get_status_class(status)
        visibility = (
            image.visibility.value if hasattr(image.visibility, "value") else str(image.visibility)
        )
        size_mb = (image.size or 0) // (1024 * 1024)

        actions = ""
        if authenticated:
            actions = f"""
            <td class="action-btns">
                <button class="action-btn delete" onclick="deleteResource('images', '{image.id}', '{image.name}')" title="Delete">Delete</button>
            </td>
            """

        rows += f"""
        <tr>
            <td class="uuid">{image.id[:8]}...</td>
            <td>{image.name}</td>
            <td><span class="status-badge {status_class}">{status}</span></td>
            <td>{visibility}</td>
            <td>{size_mb} MB</td>
            {actions}
        </tr>
        """

    action_header = "<th>Actions</th>" if authenticated else ""
    return f"""
    <table>
        <thead>
            <tr>
                <th>ID</th>
                <th>Name</th>
                <th>Status</th>
                <th>Visibility</th>
                <th>Size</th>
                {action_header}
            </tr>
        </thead>
        <tbody>{rows}</tbody>
    </table>
    """


def render_networks_table(networks: list, authenticated: bool) -> str:
    """Render the networks table HTML."""
    if not networks:
        return '<div class="empty-state">No networks created yet</div>'

    rows = ""
    for network in networks:
        status = network.status.value if hasattr(network.status, "value") else str(network.status)
        status_class = get_status_class(status)
        external = "Yes" if network.external else "No"

        actions = ""
        if authenticated:
            actions = f"""
            <td class="action-btns">
                <button class="action-btn delete" onclick="deleteResource('networks', '{network.id}', '{network.name}')" title="Delete">Delete</button>
            </td>
            """

        rows += f"""
        <tr>
            <td class="uuid">{network.id[:8]}...</td>
            <td>{network.name}</td>
            <td><span class="status-badge {status_class}">{status}</span></td>
            <td>{external}</td>
            <td>{'Yes' if network.shared else 'No'}</td>
            {actions}
        </tr>
        """

    action_header = "<th>Actions</th>" if authenticated else ""
    return f"""
    <table>
        <thead>
            <tr>
                <th>ID</th>
                <th>Name</th>
                <th>Status</th>
                <th>External</th>
                <th>Shared</th>
                {action_header}
            </tr>
        </thead>
        <tbody>{rows}</tbody>
    </table>
    """


def render_subnets_table(subnets: list, authenticated: bool) -> str:
    """Render the subnets table HTML."""
    if not subnets:
        return '<div class="empty-state">No subnets created yet</div>'

    rows = ""
    for subnet in subnets:
        actions = ""
        if authenticated:
            actions = f"""
            <td class="action-btns">
                <button class="action-btn delete" onclick="deleteResource('subnets', '{subnet.id}', '{subnet.name or subnet.id[:8]}')" title="Delete">Delete</button>
            </td>
            """

        rows += f"""
        <tr>
            <td class="uuid">{subnet.id[:8]}...</td>
            <td>{subnet.name or '-'}</td>
            <td>{subnet.cidr}</td>
            <td>{subnet.gateway_ip or '-'}</td>
            <td>{'Yes' if subnet.enable_dhcp else 'No'}</td>
            {actions}
        </tr>
        """

    action_header = "<th>Actions</th>" if authenticated else ""
    return f"""
    <table>
        <thead>
            <tr>
                <th>ID</th>
                <th>Name</th>
                <th>CIDR</th>
                <th>Gateway</th>
                <th>DHCP</th>
                {action_header}
            </tr>
        </thead>
        <tbody>{rows}</tbody>
    </table>
    """


def render_ports_table(ports: list, authenticated: bool) -> str:
    """Render the ports table HTML."""
    if not ports:
        return '<div class="empty-state">No ports created yet</div>'

    rows = ""
    for port in ports:
        status = port.status.value if hasattr(port.status, "value") else str(port.status)
        status_class = get_status_class(status)
        fixed_ips = ", ".join([ip.ip_address for ip in port.fixed_ips]) if port.fixed_ips else "-"

        actions = ""
        if authenticated:
            actions = f"""
            <td class="action-btns">
                <button class="action-btn delete" onclick="deleteResource('ports', '{port.id}', '{port.name or port.id[:8]}')" title="Delete">Delete</button>
            </td>
            """

        rows += f"""
        <tr>
            <td class="uuid">{port.id[:8]}...</td>
            <td>{port.name or '-'}</td>
            <td><span class="status-badge {status_class}">{status}</span></td>
            <td>{port.mac_address}</td>
            <td>{fixed_ips}</td>
            {actions}
        </tr>
        """

    action_header = "<th>Actions</th>" if authenticated else ""
    return f"""
    <table>
        <thead>
            <tr>
                <th>ID</th>
                <th>Name</th>
                <th>Status</th>
                <th>MAC Address</th>
                <th>Fixed IPs</th>
                {action_header}
            </tr>
        </thead>
        <tbody>{rows}</tbody>
    </table>
    """


def render_routers_table(routers: list, authenticated: bool) -> str:
    """Render the routers table HTML."""
    if not routers:
        return '<div class="empty-state">No routers created yet</div>'

    rows = ""
    for router in routers:
        status = router.status.value if hasattr(router.status, "value") else str(router.status)
        status_class = get_status_class(status)
        ext_gateway = "Yes" if router.external_gateway_info else "No"

        actions = ""
        if authenticated:
            actions = f"""
            <td class="action-btns">
                <button class="action-btn delete" onclick="deleteResource('routers', '{router.id}', '{router.name}')" title="Delete">Delete</button>
            </td>
            """

        rows += f"""
        <tr>
            <td class="uuid">{router.id[:8]}...</td>
            <td>{router.name}</td>
            <td><span class="status-badge {status_class}">{status}</span></td>
            <td>{'Yes' if router.admin_state_up else 'No'}</td>
            <td>{ext_gateway}</td>
            {actions}
        </tr>
        """

    action_header = "<th>Actions</th>" if authenticated else ""
    return f"""
    <table>
        <thead>
            <tr>
                <th>ID</th>
                <th>Name</th>
                <th>Status</th>
                <th>Admin State</th>
                <th>External Gateway</th>
                {action_header}
            </tr>
        </thead>
        <tbody>{rows}</tbody>
    </table>
    """


def render_floating_ips_table(floating_ips: list, authenticated: bool) -> str:
    """Render the floating IPs table HTML."""
    if not floating_ips:
        return '<div class="empty-state">No floating IPs allocated yet</div>'

    rows = ""
    for fip in floating_ips:
        status = fip.status.value if hasattr(fip.status, "value") else str(fip.status)
        status_class = get_status_class(status)

        actions = ""
        if authenticated:
            actions = f"""
            <td class="action-btns">
                <button class="action-btn delete" onclick="deleteResource('floating_ips', '{fip.id}', '{fip.floating_ip_address}')" title="Delete">Delete</button>
            </td>
            """

        rows += f"""
        <tr>
            <td class="uuid">{fip.id[:8]}...</td>
            <td>{fip.floating_ip_address}</td>
            <td><span class="status-badge {status_class}">{status}</span></td>
            <td>{fip.fixed_ip_address or '-'}</td>
            <td class="uuid">{fip.port_id[:8] + '...' if fip.port_id else '-'}</td>
            {actions}
        </tr>
        """

    action_header = "<th>Actions</th>" if authenticated else ""
    return f"""
    <table>
        <thead>
            <tr>
                <th>ID</th>
                <th>Floating IP</th>
                <th>Status</th>
                <th>Fixed IP</th>
                <th>Port</th>
                {action_header}
            </tr>
        </thead>
        <tbody>{rows}</tbody>
    </table>
    """


def render_security_groups_table(security_groups: list, authenticated: bool) -> str:
    """Render the security groups table HTML."""
    if not security_groups:
        return '<div class="empty-state">No security groups created yet</div>'

    rows = ""
    for sg in security_groups:
        rule_count = len(db.list_security_group_rules(security_group_id=sg.id))

        actions = ""
        if authenticated:
            actions = f"""
            <td class="action-btns">
                <button class="action-btn delete" onclick="deleteResource('security_groups', '{sg.id}', '{sg.name}')" title="Delete">Delete</button>
            </td>
            """

        rows += f"""
        <tr>
            <td class="uuid">{sg.id[:8]}...</td>
            <td>{sg.name}</td>
            <td>{sg.description or '-'}</td>
            <td>{rule_count}</td>
            {actions}
        </tr>
        """

    action_header = "<th>Actions</th>" if authenticated else ""
    return f"""
    <table>
        <thead>
            <tr>
                <th>ID</th>
                <th>Name</th>
                <th>Description</th>
                <th>Rules</th>
                {action_header}
            </tr>
        </thead>
        <tbody>{rows}</tbody>
    </table>
    """


def render_projects_table(projects: list, authenticated: bool) -> str:
    """Render the projects table HTML."""
    if not projects:
        return '<div class="empty-state">No projects created yet</div>'

    rows = ""
    for project in projects:
        actions = ""
        if authenticated:
            actions = f"""
            <td class="action-btns">
                <button class="action-btn delete" onclick="deleteResource('projects', '{project.id}', '{project.name}')" title="Delete">Delete</button>
            </td>
            """

        rows += f"""
        <tr>
            <td class="uuid">{project.id[:8]}...</td>
            <td>{project.name}</td>
            <td>{project.description or '-'}</td>
            <td>{'Yes' if project.enabled else 'No'}</td>
            {actions}
        </tr>
        """

    action_header = "<th>Actions</th>" if authenticated else ""
    return f"""
    <table>
        <thead>
            <tr>
                <th>ID</th>
                <th>Name</th>
                <th>Description</th>
                <th>Enabled</th>
                {action_header}
            </tr>
        </thead>
        <tbody>{rows}</tbody>
    </table>
    """


def render_users_table(users: list, authenticated: bool) -> str:
    """Render the users table HTML."""
    if not users:
        return '<div class="empty-state">No users created yet</div>'

    rows = ""
    for user in users:
        actions = ""
        if authenticated:
            actions = f"""
            <td class="action-btns">
                <button class="action-btn delete" onclick="deleteResource('users', '{user.id}', '{user.name}')" title="Delete">Delete</button>
            </td>
            """

        rows += f"""
        <tr>
            <td class="uuid">{user.id[:8]}...</td>
            <td>{user.name}</td>
            <td>{user.email or '-'}</td>
            <td>{'Yes' if user.enabled else 'No'}</td>
            {actions}
        </tr>
        """

    action_header = "<th>Actions</th>" if authenticated else ""
    return f"""
    <table>
        <thead>
            <tr>
                <th>ID</th>
                <th>Name</th>
                <th>Email</th>
                <th>Enabled</th>
                {action_header}
            </tr>
        </thead>
        <tbody>{rows}</tbody>
    </table>
    """


def render_flavors_table(flavors: list, authenticated: bool) -> str:
    """Render the flavors table HTML."""
    if not flavors:
        return '<div class="empty-state">No flavors available</div>'

    rows = ""
    for flavor in flavors:
        actions = ""
        if authenticated:
            actions = f"""
            <td class="action-btns">
                <button class="action-btn delete" onclick="deleteResource('flavors', '{flavor.id}', '{flavor.name}')" title="Delete">Delete</button>
            </td>
            """

        rows += f"""
        <tr>
            <td>{flavor.id}</td>
            <td>{flavor.name}</td>
            <td>{flavor.vcpus}</td>
            <td>{flavor.ram} MB</td>
            <td>{flavor.disk} GB</td>
            {actions}
        </tr>
        """

    action_header = "<th>Actions</th>" if authenticated else ""
    return f"""
    <table>
        <thead>
            <tr>
                <th>ID</th>
                <th>Name</th>
                <th>VCPUs</th>
                <th>RAM</th>
                <th>Disk</th>
                {action_header}
            </tr>
        </thead>
        <tbody>{rows}</tbody>
    </table>
    """


def render_keypairs_table(keypairs: list, authenticated: bool) -> str:
    """Render the keypairs table HTML."""
    if not keypairs:
        return '<div class="empty-state">No keypairs created yet</div>'

    rows = ""
    for keypair in keypairs:
        fingerprint = keypair.fingerprint[:20] + "..." if keypair.fingerprint else "-"

        actions = ""
        if authenticated:
            actions = f"""
            <td class="action-btns">
                <button class="action-btn delete" onclick="deleteResource('keypairs', '{keypair.name}', '{keypair.name}')" title="Delete">Delete</button>
            </td>
            """

        rows += f"""
        <tr>
            <td>{keypair.name}</td>
            <td>{keypair.type}</td>
            <td class="uuid">{fingerprint}</td>
            <td>{keypair.created_at[:19] if keypair.created_at else '-'}</td>
            {actions}
        </tr>
        """

    action_header = "<th>Actions</th>" if authenticated else ""
    return f"""
    <table>
        <thead>
            <tr>
                <th>Name</th>
                <th>Type</th>
                <th>Fingerprint</th>
                <th>Created</th>
                {action_header}
            </tr>
        </thead>
        <tbody>{rows}</tbody>
    </table>
    """


def render_snapshots_table(snapshots: list, authenticated: bool) -> str:
    """Render the snapshots table HTML."""
    if not snapshots:
        return '<div class="empty-state">No snapshots created yet</div>'

    rows = ""
    for snapshot in snapshots:
        status = (
            snapshot.status.value if hasattr(snapshot.status, "value") else str(snapshot.status)
        )
        status_class = get_status_class(status)

        actions = ""
        if authenticated:
            actions = f"""
            <td class="action-btns">
                <button class="action-btn delete" onclick="deleteResource('snapshots', '{snapshot.id}', '{snapshot.name or snapshot.id[:8]}')" title="Delete">Delete</button>
            </td>
            """

        rows += f"""
        <tr>
            <td class="uuid">{snapshot.id[:8]}...</td>
            <td>{snapshot.name or '-'}</td>
            <td><span class="status-badge {status_class}">{status}</span></td>
            <td>{snapshot.size} GB</td>
            <td class="uuid">{snapshot.volume_id[:8]}...</td>
            {actions}
        </tr>
        """

    action_header = "<th>Actions</th>" if authenticated else ""
    return f"""
    <table>
        <thead>
            <tr>
                <th>ID</th>
                <th>Name</th>
                <th>Status</th>
                <th>Size</th>
                <th>Volume ID</th>
                {action_header}
            </tr>
        </thead>
        <tbody>{rows}</tbody>
    </table>
    """


def render_create_modals(
    flavors: list,
    images: list,
    networks: list,
    volumes: list,
    volume_types: list,
) -> str:
    """Render all create modals for resources."""

    # Build flavor options
    flavor_options = "".join(
        [f'<option value="{f.id}">{f.name} ({f.vcpus} vCPU, {f.ram}MB RAM)</option>' for f in flavors]
    )

    # Build image options
    image_options = '<option value="">No image (boot from volume)</option>'
    image_options += "".join(
        [f'<option value="{i.id}">{i.name}</option>' for i in images]
    )

    # Build network options
    network_options = '<option value="">Auto-select</option>'
    network_options += "".join(
        [f'<option value="{n.id}">{n.name}</option>' for n in networks]
    )

    # Build volume options
    volume_options = "".join(
        [f'<option value="{v.id}">{v.name or v.id[:8]} ({v.size}GB)</option>' for v in volumes]
    )

    # Build volume type options
    vol_type_options = '<option value="">Default</option>'
    vol_type_options += "".join(
        [f'<option value="{vt.name}">{vt.name}</option>' for vt in volume_types]
    )

    # Build external network options for floating IPs
    external_networks = [n for n in networks if n.external]
    ext_net_options = "".join(
        [f'<option value="{n.id}">{n.name}</option>' for n in external_networks]
    )

    return f"""
    <!-- Login Modal -->
    <div id="login-modal" class="modal">
        <div class="modal-content">
            <div class="modal-header">
                <h3>Login to OpenStack Emulator</h3>
                <button class="modal-close" onclick="closeModal('login-modal')">&times;</button>
            </div>
            <div id="login-error" class="form-error" style="display: none;"></div>
            <form onsubmit="handleLogin(event)">
                <div class="form-group">
                    <label for="username">Username</label>
                    <input type="text" id="username" name="username" required placeholder="admin">
                </div>
                <div class="form-group">
                    <label for="password">Password</label>
                    <input type="password" id="password" name="password" required placeholder="password">
                </div>
                <div class="form-group">
                    <label for="project_name">Project (optional)</label>
                    <input type="text" id="project_name" name="project_name" placeholder="admin">
                </div>
                <div class="form-actions">
                    <button type="button" class="btn btn-secondary" onclick="closeModal('login-modal')">Cancel</button>
                    <button type="submit" class="btn btn-success">Login</button>
                </div>
            </form>
        </div>
    </div>

    <!-- Create Server Modal -->
    <div id="create-server-modal" class="modal">
        <div class="modal-content">
            <div class="modal-header">
                <h3>Create Server</h3>
                <button class="modal-close" onclick="closeModal('create-server-modal')">&times;</button>
            </div>
            <div class="form-error" style="display: none;"></div>
            <form id="create-server-form">
                <div class="form-group">
                    <label for="server-name">Name *</label>
                    <input type="text" id="server-name" name="name" required placeholder="my-server">
                </div>
                <div class="form-group">
                    <label for="server-flavor">Flavor *</label>
                    <select id="server-flavor" name="flavor_id" required>
                        {flavor_options}
                    </select>
                </div>
                <div class="form-group">
                    <label for="server-image">Image</label>
                    <select id="server-image" name="image_id">
                        {image_options}
                    </select>
                </div>
                <div class="form-group">
                    <label for="server-network">Network</label>
                    <select id="server-network" name="network_id">
                        {network_options}
                    </select>
                </div>
                <div class="form-actions">
                    <button type="button" class="btn btn-secondary" onclick="closeModal('create-server-modal')">Cancel</button>
                    <button type="button" class="btn btn-success" onclick="createResource('servers', 'create-server-form', 'create-server-modal')">Create</button>
                </div>
            </form>
        </div>
    </div>

    <!-- Create Volume Modal -->
    <div id="create-volume-modal" class="modal">
        <div class="modal-content">
            <div class="modal-header">
                <h3>Create Volume</h3>
                <button class="modal-close" onclick="closeModal('create-volume-modal')">&times;</button>
            </div>
            <div class="form-error" style="display: none;"></div>
            <form id="create-volume-form">
                <div class="form-group">
                    <label for="volume-name">Name *</label>
                    <input type="text" id="volume-name" name="name" required placeholder="my-volume">
                </div>
                <div class="form-group">
                    <label for="volume-size">Size (GB) *</label>
                    <input type="number" id="volume-size" name="size" required min="1" value="10">
                </div>
                <div class="form-group">
                    <label for="volume-description">Description</label>
                    <input type="text" id="volume-description" name="description" placeholder="Optional description">
                </div>
                <div class="form-group">
                    <label for="volume-type">Volume Type</label>
                    <select id="volume-type" name="volume_type">
                        {vol_type_options}
                    </select>
                </div>
                <div class="form-actions">
                    <button type="button" class="btn btn-secondary" onclick="closeModal('create-volume-modal')">Cancel</button>
                    <button type="button" class="btn btn-success" onclick="createResource('volumes', 'create-volume-form', 'create-volume-modal')">Create</button>
                </div>
            </form>
        </div>
    </div>

    <!-- Create Network Modal -->
    <div id="create-network-modal" class="modal">
        <div class="modal-content">
            <div class="modal-header">
                <h3>Create Network</h3>
                <button class="modal-close" onclick="closeModal('create-network-modal')">&times;</button>
            </div>
            <div class="form-error" style="display: none;"></div>
            <form id="create-network-form">
                <div class="form-group">
                    <label for="network-name">Name *</label>
                    <input type="text" id="network-name" name="name" required placeholder="my-network">
                </div>
                <div class="form-group">
                    <label class="checkbox-label">
                        <input type="checkbox" name="admin_state_up" checked>
                        Admin State Up
                    </label>
                </div>
                <div class="form-group">
                    <label class="checkbox-label">
                        <input type="checkbox" name="shared">
                        Shared
                    </label>
                </div>
                <div class="form-group">
                    <label class="checkbox-label">
                        <input type="checkbox" name="external">
                        External Network
                    </label>
                </div>
                <div class="form-actions">
                    <button type="button" class="btn btn-secondary" onclick="closeModal('create-network-modal')">Cancel</button>
                    <button type="button" class="btn btn-success" onclick="createResource('networks', 'create-network-form', 'create-network-modal')">Create</button>
                </div>
            </form>
        </div>
    </div>

    <!-- Create Subnet Modal -->
    <div id="create-subnet-modal" class="modal">
        <div class="modal-content">
            <div class="modal-header">
                <h3>Create Subnet</h3>
                <button class="modal-close" onclick="closeModal('create-subnet-modal')">&times;</button>
            </div>
            <div class="form-error" style="display: none;"></div>
            <form id="create-subnet-form">
                <div class="form-group">
                    <label for="subnet-name">Name</label>
                    <input type="text" id="subnet-name" name="name" placeholder="my-subnet">
                </div>
                <div class="form-group">
                    <label for="subnet-network">Network *</label>
                    <select id="subnet-network" name="network_id" required>
                        {network_options.replace('<option value="">Auto-select</option>', '')}
                    </select>
                </div>
                <div class="form-group">
                    <label for="subnet-cidr">CIDR *</label>
                    <input type="text" id="subnet-cidr" name="cidr" required placeholder="192.168.1.0/24">
                </div>
                <div class="form-group">
                    <label for="subnet-gateway">Gateway IP</label>
                    <input type="text" id="subnet-gateway" name="gateway_ip" placeholder="192.168.1.1">
                </div>
                <div class="form-group">
                    <label class="checkbox-label">
                        <input type="checkbox" name="enable_dhcp" checked>
                        Enable DHCP
                    </label>
                </div>
                <div class="form-actions">
                    <button type="button" class="btn btn-secondary" onclick="closeModal('create-subnet-modal')">Cancel</button>
                    <button type="button" class="btn btn-success" onclick="createResource('subnets', 'create-subnet-form', 'create-subnet-modal')">Create</button>
                </div>
            </form>
        </div>
    </div>

    <!-- Create Router Modal -->
    <div id="create-router-modal" class="modal">
        <div class="modal-content">
            <div class="modal-header">
                <h3>Create Router</h3>
                <button class="modal-close" onclick="closeModal('create-router-modal')">&times;</button>
            </div>
            <div class="form-error" style="display: none;"></div>
            <form id="create-router-form">
                <div class="form-group">
                    <label for="router-name">Name *</label>
                    <input type="text" id="router-name" name="name" required placeholder="my-router">
                </div>
                <div class="form-group">
                    <label for="router-ext-net">External Network</label>
                    <select id="router-ext-net" name="external_network_id">
                        <option value="">None</option>
                        {ext_net_options}
                    </select>
                </div>
                <div class="form-group">
                    <label class="checkbox-label">
                        <input type="checkbox" name="admin_state_up" checked>
                        Admin State Up
                    </label>
                </div>
                <div class="form-actions">
                    <button type="button" class="btn btn-secondary" onclick="closeModal('create-router-modal')">Cancel</button>
                    <button type="button" class="btn btn-success" onclick="createResource('routers', 'create-router-form', 'create-router-modal')">Create</button>
                </div>
            </form>
        </div>
    </div>

    <!-- Create Floating IP Modal -->
    <div id="create-floating-ip-modal" class="modal">
        <div class="modal-content">
            <div class="modal-header">
                <h3>Allocate Floating IP</h3>
                <button class="modal-close" onclick="closeModal('create-floating-ip-modal')">&times;</button>
            </div>
            <div class="form-error" style="display: none;"></div>
            <form id="create-floating-ip-form">
                <div class="form-group">
                    <label for="fip-network">External Network *</label>
                    <select id="fip-network" name="floating_network_id" required>
                        {ext_net_options}
                    </select>
                </div>
                <div class="form-actions">
                    <button type="button" class="btn btn-secondary" onclick="closeModal('create-floating-ip-modal')">Cancel</button>
                    <button type="button" class="btn btn-success" onclick="createResource('floating_ips', 'create-floating-ip-form', 'create-floating-ip-modal')">Allocate</button>
                </div>
            </form>
        </div>
    </div>

    <!-- Create Security Group Modal -->
    <div id="create-security-group-modal" class="modal">
        <div class="modal-content">
            <div class="modal-header">
                <h3>Create Security Group</h3>
                <button class="modal-close" onclick="closeModal('create-security-group-modal')">&times;</button>
            </div>
            <div class="form-error" style="display: none;"></div>
            <form id="create-security-group-form">
                <div class="form-group">
                    <label for="sg-name">Name *</label>
                    <input type="text" id="sg-name" name="name" required placeholder="my-security-group">
                </div>
                <div class="form-group">
                    <label for="sg-description">Description</label>
                    <input type="text" id="sg-description" name="description" placeholder="Security group description">
                </div>
                <div class="form-actions">
                    <button type="button" class="btn btn-secondary" onclick="closeModal('create-security-group-modal')">Cancel</button>
                    <button type="button" class="btn btn-success" onclick="createResource('security_groups', 'create-security-group-form', 'create-security-group-modal')">Create</button>
                </div>
            </form>
        </div>
    </div>

    <!-- Create Project Modal -->
    <div id="create-project-modal" class="modal">
        <div class="modal-content">
            <div class="modal-header">
                <h3>Create Project</h3>
                <button class="modal-close" onclick="closeModal('create-project-modal')">&times;</button>
            </div>
            <div class="form-error" style="display: none;"></div>
            <form id="create-project-form">
                <div class="form-group">
                    <label for="project-name">Name *</label>
                    <input type="text" id="project-name" name="name" required placeholder="my-project">
                </div>
                <div class="form-group">
                    <label for="project-description">Description</label>
                    <input type="text" id="project-description" name="description" placeholder="Project description">
                </div>
                <div class="form-group">
                    <label class="checkbox-label">
                        <input type="checkbox" name="enabled" checked>
                        Enabled
                    </label>
                </div>
                <div class="form-actions">
                    <button type="button" class="btn btn-secondary" onclick="closeModal('create-project-modal')">Cancel</button>
                    <button type="button" class="btn btn-success" onclick="createResource('projects', 'create-project-form', 'create-project-modal')">Create</button>
                </div>
            </form>
        </div>
    </div>

    <!-- Create User Modal -->
    <div id="create-user-modal" class="modal">
        <div class="modal-content">
            <div class="modal-header">
                <h3>Create User</h3>
                <button class="modal-close" onclick="closeModal('create-user-modal')">&times;</button>
            </div>
            <div class="form-error" style="display: none;"></div>
            <form id="create-user-form">
                <div class="form-group">
                    <label for="user-name">Username *</label>
                    <input type="text" id="user-name" name="name" required placeholder="newuser">
                </div>
                <div class="form-group">
                    <label for="user-password">Password *</label>
                    <input type="password" id="user-password" name="password" required placeholder="password">
                </div>
                <div class="form-group">
                    <label for="user-email">Email</label>
                    <input type="email" id="user-email" name="email" placeholder="user@example.com">
                </div>
                <div class="form-group">
                    <label class="checkbox-label">
                        <input type="checkbox" name="enabled" checked>
                        Enabled
                    </label>
                </div>
                <div class="form-actions">
                    <button type="button" class="btn btn-secondary" onclick="closeModal('create-user-modal')">Cancel</button>
                    <button type="button" class="btn btn-success" onclick="createResource('users', 'create-user-form', 'create-user-modal')">Create</button>
                </div>
            </form>
        </div>
    </div>

    <!-- Create Image Modal -->
    <div id="create-image-modal" class="modal">
        <div class="modal-content">
            <div class="modal-header">
                <h3>Create Image</h3>
                <button class="modal-close" onclick="closeModal('create-image-modal')">&times;</button>
            </div>
            <div class="form-error" style="display: none;"></div>
            <form id="create-image-form">
                <div class="form-group">
                    <label for="image-name">Name *</label>
                    <input type="text" id="image-name" name="name" required placeholder="my-image">
                </div>
                <div class="form-group">
                    <label for="image-disk-format">Disk Format</label>
                    <select id="image-disk-format" name="disk_format">
                        <option value="qcow2">qcow2</option>
                        <option value="raw">raw</option>
                        <option value="vmdk">vmdk</option>
                        <option value="vdi">vdi</option>
                        <option value="iso">iso</option>
                        <option value="ami">ami</option>
                    </select>
                </div>
                <div class="form-group">
                    <label for="image-container-format">Container Format</label>
                    <select id="image-container-format" name="container_format">
                        <option value="bare">bare</option>
                        <option value="ovf">ovf</option>
                        <option value="ova">ova</option>
                        <option value="aki">aki</option>
                        <option value="ari">ari</option>
                        <option value="ami">ami</option>
                    </select>
                </div>
                <div class="form-group">
                    <label for="image-visibility">Visibility</label>
                    <select id="image-visibility" name="visibility">
                        <option value="public">Public</option>
                        <option value="private">Private</option>
                        <option value="shared">Shared</option>
                        <option value="community">Community</option>
                    </select>
                </div>
                <div class="form-actions">
                    <button type="button" class="btn btn-secondary" onclick="closeModal('create-image-modal')">Cancel</button>
                    <button type="button" class="btn btn-success" onclick="createResource('images', 'create-image-form', 'create-image-modal')">Create</button>
                </div>
            </form>
        </div>
    </div>

    <!-- Create Snapshot Modal -->
    <div id="create-snapshot-modal" class="modal">
        <div class="modal-content">
            <div class="modal-header">
                <h3>Create Snapshot</h3>
                <button class="modal-close" onclick="closeModal('create-snapshot-modal')">&times;</button>
            </div>
            <div class="form-error" style="display: none;"></div>
            <form id="create-snapshot-form">
                <div class="form-group">
                    <label for="snapshot-name">Name *</label>
                    <input type="text" id="snapshot-name" name="name" required placeholder="my-snapshot">
                </div>
                <div class="form-group">
                    <label for="snapshot-volume">Volume *</label>
                    <select id="snapshot-volume" name="volume_id" required>
                        {volume_options}
                    </select>
                </div>
                <div class="form-group">
                    <label for="snapshot-description">Description</label>
                    <input type="text" id="snapshot-description" name="description" placeholder="Snapshot description">
                </div>
                <div class="form-actions">
                    <button type="button" class="btn btn-secondary" onclick="closeModal('create-snapshot-modal')">Cancel</button>
                    <button type="button" class="btn btn-success" onclick="createResource('snapshots', 'create-snapshot-form', 'create-snapshot-modal')">Create</button>
                </div>
            </form>
        </div>
    </div>
    """


@router.get("/", response_class=HTMLResponse)
async def status_page(
    request: Request,
    auth_token: str | None = Cookie(default=None),
) -> str:
    """Render the main status page."""
    # Determine the host from the request
    host = request.headers.get("host", "localhost:8000").split(":")[0]
    if host == "localhost" or host == "127.0.0.1":
        check_host = "localhost"
    else:
        check_host = host

    # Check authentication
    current_user = get_current_user(auth_token)
    authenticated = current_user is not None

    # Check service health
    service_status = {}
    for service, info in SERVICES.items():
        is_healthy = await check_service_health(check_host, info["port"])
        service_status[service] = {
            "name": info["name"],
            "port": info["port"],
            "healthy": is_healthy,
        }

    # Build service cards HTML
    service_cards = ""
    for service, status in service_status.items():
        status_class = "" if status["healthy"] else "offline"
        dot_class = "" if status["healthy"] else "offline"
        status_text = "Running" if status["healthy"] else "Offline"
        service_cards += f"""
        <div class="service-card {status_class}">
            <h3>
                <span class="status-dot {dot_class}"></span>
                {service.capitalize()} ({status['name']})
            </h3>
            <div class="service-info">
                <div>Port: {status['port']}</div>
                <div>Status: {status_text}</div>
            </div>
        </div>
        """

    # Get resource counts
    servers = db.list_servers()
    volumes = db.list_volumes()
    images = db.list_glance_images()
    networks = db.list_networks()
    subnets = db.list_subnets()
    ports = db.list_ports()
    routers = db.list_routers()
    floating_ips = db.list_floating_ips()
    security_groups = db.list_security_groups()
    projects = db.list_projects()
    users = db.list_users()
    flavors = db.list_flavors()
    keypairs = list(db._keypairs.values())
    snapshots = db.list_snapshots()
    volume_types = db.list_volume_types()

    # Build authentication section
    if authenticated:
        auth_section = f"""
        <div class="auth-section">
            <div class="user-info">
                <div class="user-icon">{current_user['name'][0].upper()}</div>
                <div>
                    <div>{current_user['name']}</div>
                    <div style="font-size: 0.8rem; opacity: 0.8;">{current_user['project_name'] or 'No project'}</div>
                </div>
            </div>
            <button class="logout-btn" onclick="handleLogout()">Logout</button>
        </div>
        """
    else:
        auth_section = """
        <div class="auth-section">
            <button class="login-btn" onclick="openModal('login-modal')">Login</button>
        </div>
        """

    # Build readonly notice for unauthenticated users
    readonly_notice = ""
    if not authenticated:
        readonly_notice = """
        <div class="readonly-notice">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="10"></circle>
                <line x1="12" y1="8" x2="12" y2="12"></line>
                <line x1="12" y1="16" x2="12.01" y2="16"></line>
            </svg>
            <span>You are viewing in read-only mode. <a href="#" onclick="openModal('login-modal'); return false;">Login</a> to create and manage resources.</span>
        </div>
        """

    # Build create buttons (only shown when authenticated)
    def create_btn(modal_id: str, label: str) -> str:
        if authenticated:
            return f'<button class="btn btn-sm btn-success" onclick="openModal(\'{modal_id}\')">{label}</button>'
        return ""

    # Build modals
    modals = render_create_modals(flavors, images, networks, volumes, volume_types)

    # Build the full HTML page
    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>OpenStack Emulator Status</title>
        {CSS_STYLES}
    </head>
    <body>
        <div id="toast-container" class="toast-container"></div>

        <header>
            <div class="container">
                <div class="header-actions">
                    <div>
                        <h1>OpenStack Emulator Status</h1>
                        <p>Real-time view of emulator services and resources</p>
                    </div>
                    <div style="display: flex; gap: 15px; align-items: center;">
                        <button class="refresh-btn" onclick="location.reload()">Refresh</button>
                        {auth_section}
                    </div>
                </div>
            </div>
        </header>

        <div class="container">
            {readonly_notice}

            <!-- Service Status Cards -->
            <div class="section">
                <h2>Services</h2>
                <div class="service-grid">
                    {service_cards}
                </div>
            </div>

            <!-- Tabbed Resources -->
            <div class="section">
                <h2>Resources</h2>

                <div class="tabs">
                    <button class="tab active" data-tab="compute" onclick="switchTab('compute')">Compute</button>
                    <button class="tab" data-tab="storage" onclick="switchTab('storage')">Storage</button>
                    <button class="tab" data-tab="network" onclick="switchTab('network')">Network</button>
                    <button class="tab" data-tab="identity" onclick="switchTab('identity')">Identity</button>
                </div>

                <!-- Compute Tab -->
                <div id="tab-compute" class="tab-content active">
                    <div class="resource-group">
                        <div class="resource-header">
                            <h3>Servers <span class="count-badge">{len(servers)}</span></h3>
                            {create_btn('create-server-modal', '+ Create Server')}
                        </div>
                        {render_servers_table(servers, authenticated)}
                    </div>
                    <div class="resource-group">
                        <div class="resource-header">
                            <h3>Flavors <span class="count-badge">{len(flavors)}</span></h3>
                        </div>
                        {render_flavors_table(flavors, authenticated)}
                    </div>
                    <div class="resource-group">
                        <div class="resource-header">
                            <h3>Keypairs <span class="count-badge">{len(keypairs)}</span></h3>
                        </div>
                        {render_keypairs_table(keypairs, authenticated)}
                    </div>
                </div>

                <!-- Storage Tab -->
                <div id="tab-storage" class="tab-content">
                    <div class="resource-group">
                        <div class="resource-header">
                            <h3>Images <span class="count-badge">{len(images)}</span></h3>
                            {create_btn('create-image-modal', '+ Create Image')}
                        </div>
                        {render_images_table(images, authenticated)}
                    </div>
                    <div class="resource-group">
                        <div class="resource-header">
                            <h3>Volumes <span class="count-badge">{len(volumes)}</span></h3>
                            {create_btn('create-volume-modal', '+ Create Volume')}
                        </div>
                        {render_volumes_table(volumes, authenticated)}
                    </div>
                    <div class="resource-group">
                        <div class="resource-header">
                            <h3>Snapshots <span class="count-badge">{len(snapshots)}</span></h3>
                            {create_btn('create-snapshot-modal', '+ Create Snapshot')}
                        </div>
                        {render_snapshots_table(snapshots, authenticated)}
                    </div>
                </div>

                <!-- Network Tab -->
                <div id="tab-network" class="tab-content">
                    <div class="resource-group">
                        <div class="resource-header">
                            <h3>Networks <span class="count-badge">{len(networks)}</span></h3>
                            {create_btn('create-network-modal', '+ Create Network')}
                        </div>
                        {render_networks_table(networks, authenticated)}
                    </div>
                    <div class="resource-group">
                        <div class="resource-header">
                            <h3>Subnets <span class="count-badge">{len(subnets)}</span></h3>
                            {create_btn('create-subnet-modal', '+ Create Subnet')}
                        </div>
                        {render_subnets_table(subnets, authenticated)}
                    </div>
                    <div class="resource-group">
                        <div class="resource-header">
                            <h3>Ports <span class="count-badge">{len(ports)}</span></h3>
                        </div>
                        {render_ports_table(ports, authenticated)}
                    </div>
                    <div class="resource-group">
                        <div class="resource-header">
                            <h3>Routers <span class="count-badge">{len(routers)}</span></h3>
                            {create_btn('create-router-modal', '+ Create Router')}
                        </div>
                        {render_routers_table(routers, authenticated)}
                    </div>
                    <div class="resource-group">
                        <div class="resource-header">
                            <h3>Floating IPs <span class="count-badge">{len(floating_ips)}</span></h3>
                            {create_btn('create-floating-ip-modal', '+ Allocate IP')}
                        </div>
                        {render_floating_ips_table(floating_ips, authenticated)}
                    </div>
                    <div class="resource-group">
                        <div class="resource-header">
                            <h3>Security Groups <span class="count-badge">{len(security_groups)}</span></h3>
                            {create_btn('create-security-group-modal', '+ Create Group')}
                        </div>
                        {render_security_groups_table(security_groups, authenticated)}
                    </div>
                </div>

                <!-- Identity Tab -->
                <div id="tab-identity" class="tab-content">
                    <div class="resource-group">
                        <div class="resource-header">
                            <h3>Projects <span class="count-badge">{len(projects)}</span></h3>
                            {create_btn('create-project-modal', '+ Create Project')}
                        </div>
                        {render_projects_table(projects, authenticated)}
                    </div>
                    <div class="resource-group">
                        <div class="resource-header">
                            <h3>Users <span class="count-badge">{len(users)}</span></h3>
                            {create_btn('create-user-modal', '+ Create User')}
                        </div>
                        {render_users_table(users, authenticated)}
                    </div>
                </div>
            </div>
        </div>

        {modals}
        {JS_SCRIPT}
    </body>
    </html>
    """

    return html


@router.get("/api/status")
async def api_status(request: Request) -> dict:
    """Return status as JSON for programmatic access."""
    host = request.headers.get("host", "localhost:8000").split(":")[0]
    if host == "localhost" or host == "127.0.0.1":
        check_host = "localhost"
    else:
        check_host = host

    # Check service health
    services = {}
    for service, info in SERVICES.items():
        is_healthy = await check_service_health(check_host, info["port"])
        services[service] = {
            "name": info["name"],
            "port": info["port"],
            "healthy": is_healthy,
        }

    # Get resource counts
    return {
        "services": services,
        "resources": {
            "servers": len(db.list_servers()),
            "volumes": len(db.list_volumes()),
            "images": len(db.list_glance_images()),
            "networks": len(db.list_networks()),
            "subnets": len(db.list_subnets()),
            "ports": len(db.list_ports()),
            "routers": len(db.list_routers()),
            "floating_ips": len(db.list_floating_ips()),
            "security_groups": len(db.list_security_groups()),
            "projects": len(db.list_projects()),
            "users": len(db.list_users()),
            "flavors": len(db.list_flavors()),
            "keypairs": len(db._keypairs),
            "snapshots": len(db.list_snapshots()),
        },
    }


# =============================================================================
# Authentication API
# =============================================================================


@router.post("/api/login")
async def api_login(request: LoginRequest) -> JSONResponse:
    """Login and create a session token."""
    # Find the user
    user = db.get_user_by_name(request.username)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    # Find the project (optional)
    project = None
    project_name = request.project_name or "admin"
    if request.project_name:
        project = db.get_project_by_name(request.project_name)
        if not project:
            raise HTTPException(status_code=401, detail="Project not found")
    else:
        project = db.get_project_by_name("admin")

    # Create a token using the database
    token = db.create_token(
        user_name=user.name,
        project_name=project.name if project else "admin",
        domain_id=user.domain_id,
    )

    response = JSONResponse(
        content={
            "token": token.id,
            "user": {"id": user.id, "name": user.name},
            "project": {"id": project.id, "name": project.name} if project else None,
        }
    )
    response.set_cookie(
        key="auth_token",
        value=token.id,
        httponly=True,
        max_age=86400,  # 24 hours
        samesite="lax",
    )
    return response


@router.post("/api/logout")
async def api_logout(auth_token: str | None = Cookie(default=None)) -> JSONResponse:
    """Logout and revoke the session token."""
    if auth_token:
        db.revoke_token(auth_token)

    response = JSONResponse(content={"message": "Logged out successfully"})
    response.delete_cookie(key="auth_token")
    return response


@router.get("/api/session")
async def api_session(auth_token: str | None = Cookie(default=None)) -> dict:
    """Get the current session information."""
    user = get_current_user(auth_token)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {"user": user}


def require_auth(auth_token: str | None) -> dict:
    """Helper to require authentication for API endpoints."""
    user = get_current_user(auth_token)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


# =============================================================================
# Management API - Servers
# =============================================================================


@router.post("/api/servers")
async def api_create_server(
    request: ServerCreateRequest,
    auth_token: str | None = Cookie(default=None),
) -> dict:
    """Create a new server."""
    user = require_auth(auth_token)

    # Validate flavor
    flavor = db.get_flavor(request.flavor_id)
    if not flavor:
        raise HTTPException(status_code=400, detail="Flavor not found")

    # Create the server using database method
    server = db.create_server(
        name=request.name,
        flavor_id=request.flavor_id,
        image_id=request.image_id or "",
        tenant_id=user["project_id"],
        user_id=user["id"],
    )

    return {"server": {"id": server.id, "name": server.name, "status": server.status.value}}


@router.delete("/api/servers/{server_id}")
async def api_delete_server(
    server_id: str,
    auth_token: str | None = Cookie(default=None),
) -> dict:
    """Delete a server."""
    require_auth(auth_token)

    if not db.delete_server(server_id):
        raise HTTPException(status_code=404, detail="Server not found")

    return {"message": "Server deleted"}


@router.post("/api/servers/{server_id}/action")
async def api_server_action(
    server_id: str,
    action: dict,
    auth_token: str | None = Cookie(default=None),
) -> dict:
    """Perform an action on a server."""
    require_auth(auth_token)

    server = db.get_server(server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    action_name = action.get("action", "")
    if action_name == "start":
        server.status = ServerStatus.ACTIVE
    elif action_name == "stop":
        server.status = ServerStatus.SHUTOFF
    elif action_name == "reboot":
        server.status = ServerStatus.ACTIVE
    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {action_name}")

    server.updated = datetime.now(timezone.utc)
    return {"message": f"Action '{action_name}' executed"}


# =============================================================================
# Management API - Volumes
# =============================================================================


@router.post("/api/volumes")
async def api_create_volume(
    request: VolumeCreateRequest,
    auth_token: str | None = Cookie(default=None),
) -> dict:
    """Create a new volume."""
    user = require_auth(auth_token)

    # Create volume using database method
    volume = db.create_volume(
        name=request.name,
        size=request.size,
        project_id=user["project_id"],
        user_id=user["id"],
        description=request.description or "",
        volume_type=request.volume_type,
    )

    return {"volume": {"id": volume.id, "name": volume.name, "status": volume.status.value}}


@router.delete("/api/volumes/{volume_id}")
async def api_delete_volume(
    volume_id: str,
    auth_token: str | None = Cookie(default=None),
) -> dict:
    """Delete a volume."""
    require_auth(auth_token)

    if not db.delete_volume(volume_id):
        raise HTTPException(status_code=404, detail="Volume not found")

    return {"message": "Volume deleted"}


# =============================================================================
# Management API - Networks
# =============================================================================


@router.post("/api/networks")
async def api_create_network(
    request: NetworkCreateRequest,
    auth_token: str | None = Cookie(default=None),
) -> dict:
    """Create a new network."""
    user = require_auth(auth_token)

    # Create network using database method
    network = db.create_network(
        name=request.name,
        project_id=user["project_id"],
        admin_state_up=request.admin_state_up,
        shared=request.shared,
        external=request.external,
    )

    return {"network": {"id": network.id, "name": network.name, "status": network.status.value}}


@router.delete("/api/networks/{network_id}")
async def api_delete_network(
    network_id: str,
    auth_token: str | None = Cookie(default=None),
) -> dict:
    """Delete a network."""
    require_auth(auth_token)

    if not db.delete_network(network_id):
        raise HTTPException(status_code=404, detail="Network not found")

    return {"message": "Network deleted"}


# =============================================================================
# Management API - Subnets
# =============================================================================


@router.post("/api/subnets")
async def api_create_subnet(
    request: SubnetCreateRequest,
    auth_token: str | None = Cookie(default=None),
) -> dict:
    """Create a new subnet."""
    user = require_auth(auth_token)

    # Validate network exists
    network = db.get_network(request.network_id)
    if not network:
        raise HTTPException(status_code=400, detail="Network not found")

    # Create subnet using database method
    subnet = db.create_subnet(
        network_id=request.network_id,
        cidr=request.cidr,
        project_id=user["project_id"],
        name=request.name or "",
        ip_version=request.ip_version,
        gateway_ip=request.gateway_ip,
        enable_dhcp=request.enable_dhcp,
    )

    return {"subnet": {"id": subnet.id, "name": subnet.name, "cidr": subnet.cidr}}


@router.delete("/api/subnets/{subnet_id}")
async def api_delete_subnet(
    subnet_id: str,
    auth_token: str | None = Cookie(default=None),
) -> dict:
    """Delete a subnet."""
    require_auth(auth_token)

    if not db.delete_subnet(subnet_id):
        raise HTTPException(status_code=404, detail="Subnet not found")

    return {"message": "Subnet deleted"}


# =============================================================================
# Management API - Ports
# =============================================================================


@router.delete("/api/ports/{port_id}")
async def api_delete_port(
    port_id: str,
    auth_token: str | None = Cookie(default=None),
) -> dict:
    """Delete a port."""
    require_auth(auth_token)

    if not db.delete_port(port_id):
        raise HTTPException(status_code=404, detail="Port not found")

    return {"message": "Port deleted"}


# =============================================================================
# Management API - Routers
# =============================================================================


@router.post("/api/routers")
async def api_create_router(
    request: RouterCreateRequest,
    auth_token: str | None = Cookie(default=None),
) -> dict:
    """Create a new router."""
    user = require_auth(auth_token)

    external_gateway_info = None
    if request.external_network_id:
        network = db.get_network(request.external_network_id)
        if not network or not network.external:
            raise HTTPException(status_code=400, detail="External network not found")
        external_gateway_info = {"network_id": request.external_network_id}

    # Create router using database method
    router_obj = db.create_router(
        name=request.name,
        project_id=user["project_id"],
        admin_state_up=request.admin_state_up,
        external_gateway_info=external_gateway_info,
    )

    return {"router": {"id": router_obj.id, "name": router_obj.name, "status": router_obj.status.value}}


@router.delete("/api/routers/{router_id}")
async def api_delete_router(
    router_id: str,
    auth_token: str | None = Cookie(default=None),
) -> dict:
    """Delete a router."""
    require_auth(auth_token)

    if not db.delete_router(router_id):
        raise HTTPException(status_code=404, detail="Router not found")

    return {"message": "Router deleted"}


# =============================================================================
# Management API - Floating IPs
# =============================================================================


@router.post("/api/floating_ips")
async def api_create_floating_ip(
    request: FloatingIPCreateRequest,
    auth_token: str | None = Cookie(default=None),
) -> dict:
    """Allocate a new floating IP."""
    user = require_auth(auth_token)

    # Validate external network
    network = db.get_network(request.floating_network_id)
    if not network or not network.external:
        raise HTTPException(status_code=400, detail="External network not found")

    # Create floating IP using database method
    floating_ip = db.create_floating_ip(
        floating_network_id=request.floating_network_id,
        project_id=user["project_id"],
        port_id=request.port_id,
    )

    if not floating_ip:
        raise HTTPException(status_code=400, detail="Failed to allocate floating IP")

    return {
        "floating_ip": {
            "id": floating_ip.id,
            "floating_ip_address": floating_ip.floating_ip_address,
            "status": floating_ip.status.value,
        }
    }


@router.delete("/api/floating_ips/{floating_ip_id}")
async def api_delete_floating_ip(
    floating_ip_id: str,
    auth_token: str | None = Cookie(default=None),
) -> dict:
    """Delete a floating IP."""
    require_auth(auth_token)

    if not db.delete_floating_ip(floating_ip_id):
        raise HTTPException(status_code=404, detail="Floating IP not found")

    return {"message": "Floating IP deleted"}


# =============================================================================
# Management API - Security Groups
# =============================================================================


@router.post("/api/security_groups")
async def api_create_security_group(
    request: SecurityGroupCreateRequest,
    auth_token: str | None = Cookie(default=None),
) -> dict:
    """Create a new security group."""
    user = require_auth(auth_token)

    # Create security group using database method
    security_group = db.create_security_group(
        name=request.name,
        project_id=user["project_id"],
        description=request.description or "",
    )

    return {
        "security_group": {
            "id": security_group.id,
            "name": security_group.name,
            "description": security_group.description,
        }
    }


@router.delete("/api/security_groups/{security_group_id}")
async def api_delete_security_group(
    security_group_id: str,
    auth_token: str | None = Cookie(default=None),
) -> dict:
    """Delete a security group."""
    require_auth(auth_token)

    sg = db.get_security_group(security_group_id)
    if not sg:
        raise HTTPException(status_code=404, detail="Security group not found")

    if sg.name == "default":
        raise HTTPException(status_code=400, detail="Cannot delete default security group")

    if not db.delete_security_group(security_group_id):
        raise HTTPException(status_code=404, detail="Security group not found")

    return {"message": "Security group deleted"}


# =============================================================================
# Management API - Projects
# =============================================================================


@router.post("/api/projects")
async def api_create_project(
    request: ProjectCreateRequest,
    auth_token: str | None = Cookie(default=None),
) -> dict:
    """Create a new project."""
    require_auth(auth_token)

    # Check if project name already exists
    existing = db.get_project_by_name(request.name)
    if existing:
        raise HTTPException(status_code=400, detail="Project name already exists")

    # Create project using database method
    project = db.create_project(
        name=request.name,
        description=request.description or "",
        enabled=request.enabled,
    )

    return {"project": {"id": project.id, "name": project.name, "enabled": project.enabled}}


@router.delete("/api/projects/{project_id}")
async def api_delete_project(
    project_id: str,
    auth_token: str | None = Cookie(default=None),
) -> dict:
    """Delete a project."""
    require_auth(auth_token)

    project = db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.name == "admin":
        raise HTTPException(status_code=400, detail="Cannot delete admin project")

    if not db.delete_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")

    return {"message": "Project deleted"}


# =============================================================================
# Management API - Users
# =============================================================================


@router.post("/api/users")
async def api_create_user(
    request: UserCreateRequest,
    auth_token: str | None = Cookie(default=None),
) -> dict:
    """Create a new user."""
    require_auth(auth_token)

    # Check if username already exists
    existing = db.get_user_by_name(request.name)
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists")

    # Create user using database method
    new_user = db.create_user(
        name=request.name,
        password=request.password,
        email=request.email or "",
        enabled=request.enabled,
    )

    return {"user": {"id": new_user.id, "name": new_user.name, "enabled": new_user.enabled}}


@router.delete("/api/users/{user_id}")
async def api_delete_user(
    user_id: str,
    auth_token: str | None = Cookie(default=None),
) -> dict:
    """Delete a user."""
    require_auth(auth_token)

    user = db.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.name == "admin":
        raise HTTPException(status_code=400, detail="Cannot delete admin user")

    if not db.delete_user(user_id):
        raise HTTPException(status_code=404, detail="User not found")

    return {"message": "User deleted"}


# =============================================================================
# Management API - Images
# =============================================================================


@router.post("/api/images")
async def api_create_image(
    request: ImageCreateRequest,
    auth_token: str | None = Cookie(default=None),
) -> dict:
    """Create a new image."""
    user = require_auth(auth_token)

    # Map string visibility to enum
    visibility_map = {
        "public": ImageVisibility.PUBLIC,
        "private": ImageVisibility.PRIVATE,
        "shared": ImageVisibility.SHARED,
        "community": ImageVisibility.COMMUNITY,
    }
    visibility = visibility_map.get(request.visibility, ImageVisibility.PUBLIC)

    # Create image using database method
    image = db.create_glance_image(
        name=request.name,
        owner=user["project_id"],
        visibility=visibility,
    )

    return {"image": {"id": image.id, "name": image.name, "status": image.status.value}}


@router.delete("/api/images/{image_id}")
async def api_delete_image(
    image_id: str,
    auth_token: str | None = Cookie(default=None),
) -> dict:
    """Delete an image."""
    require_auth(auth_token)

    if not db.delete_glance_image(image_id):
        raise HTTPException(status_code=404, detail="Image not found")

    return {"message": "Image deleted"}


# =============================================================================
# Management API - Flavors
# =============================================================================


@router.delete("/api/flavors/{flavor_id}")
async def api_delete_flavor(
    flavor_id: str,
    auth_token: str | None = Cookie(default=None),
) -> dict:
    """Delete a flavor."""
    require_auth(auth_token)

    if not db.delete_flavor(flavor_id):
        raise HTTPException(status_code=404, detail="Flavor not found")

    return {"message": "Flavor deleted"}


# =============================================================================
# Management API - Keypairs
# =============================================================================


@router.delete("/api/keypairs/{keypair_name}")
async def api_delete_keypair(
    keypair_name: str,
    auth_token: str | None = Cookie(default=None),
) -> dict:
    """Delete a keypair."""
    require_auth(auth_token)

    if keypair_name not in db._keypairs:
        raise HTTPException(status_code=404, detail="Keypair not found")

    del db._keypairs[keypair_name]
    return {"message": "Keypair deleted"}


# =============================================================================
# Management API - Snapshots
# =============================================================================


@router.post("/api/snapshots")
async def api_create_snapshot(
    request: SnapshotCreateRequest,
    auth_token: str | None = Cookie(default=None),
) -> dict:
    """Create a new snapshot."""
    user = require_auth(auth_token)

    # Validate volume exists
    volume = db.get_volume(request.volume_id)
    if not volume:
        raise HTTPException(status_code=400, detail="Volume not found")

    # Create snapshot using database method
    snapshot = db.create_snapshot(
        volume_id=request.volume_id,
        name=request.name,
        project_id=user["project_id"],
        user_id=user["id"],
        description=request.description or "",
    )

    if not snapshot:
        raise HTTPException(status_code=400, detail="Failed to create snapshot")

    return {"snapshot": {"id": snapshot.id, "name": snapshot.name, "status": snapshot.status.value}}


@router.delete("/api/snapshots/{snapshot_id}")
async def api_delete_snapshot(
    snapshot_id: str,
    auth_token: str | None = Cookie(default=None),
) -> dict:
    """Delete a snapshot."""
    require_auth(auth_token)

    if not db.delete_snapshot(snapshot_id):
        raise HTTPException(status_code=404, detail="Snapshot not found")

    return {"message": "Snapshot deleted"}
