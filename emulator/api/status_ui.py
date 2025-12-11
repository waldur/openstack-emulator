"""Status UI routes for displaying emulator state with authentication and management.

Provides a web interface to view the status of all services and objects
in the OpenStack emulator, with authentication support and CRUD operations.
"""

from datetime import datetime, timezone
from typing import TypedDict

import httpx
from fastapi import APIRouter, Cookie, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from emulator.core.database import db
from emulator.core.models import (
    ImageVisibility,
    ServerStatus,
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


# CSS styles for the status page - Terminal/Geek aesthetic with Tailwind
CSS_STYLES = """
<script src="https://cdn.tailwindcss.com"></script>
<script>
tailwind.config = {
    theme: {
        extend: {
            colors: {
                terminal: {
                    bg: '#0a0a0f',
                    panel: '#0d1117',
                    border: '#1e3a5f',
                    green: '#00ff41',
                    cyan: '#00d4ff',
                    amber: '#ffb000',
                    red: '#ff3366',
                    purple: '#a855f7',
                    dim: '#4a5568',
                },
            },
            fontFamily: {
                mono: ['JetBrains Mono', 'Fira Code', 'Consolas', 'Monaco', 'monospace'],
            },
            animation: {
                'pulse-glow': 'pulse-glow 2s ease-in-out infinite',
                'scan': 'scan 8s linear infinite',
                'flicker': 'flicker 0.15s infinite',
                'typing': 'typing 3.5s steps(40, end)',
            },
            keyframes: {
                'pulse-glow': {
                    '0%, 100%': { opacity: '1', filter: 'brightness(1)' },
                    '50%': { opacity: '0.8', filter: 'brightness(1.2)' },
                },
                'scan': {
                    '0%': { transform: 'translateY(-100%)' },
                    '100%': { transform: 'translateY(100vh)' },
                },
                'flicker': {
                    '0%, 100%': { opacity: '1' },
                    '50%': { opacity: '0.98' },
                },
            },
        },
    },
}
</script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
    * {
        box-sizing: border-box;
        margin: 0;
        padding: 0;
    }
    body {
        font-family: 'JetBrains Mono', monospace;
        background: #0a0a0f;
        color: #e2e8f0;
        line-height: 1.6;
        position: relative;
        min-height: 100vh;
    }
    /* CRT Scanline effect */
    body::before {
        content: '';
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: repeating-linear-gradient(
            0deg,
            rgba(0, 0, 0, 0.15),
            rgba(0, 0, 0, 0.15) 1px,
            transparent 1px,
            transparent 2px
        );
        pointer-events: none;
        z-index: 9999;
    }
    /* Glow effects */
    .glow-green { text-shadow: 0 0 10px #00ff41, 0 0 20px #00ff41, 0 0 30px #00ff41; }
    .glow-cyan { text-shadow: 0 0 10px #00d4ff, 0 0 20px #00d4ff; }
    .glow-amber { text-shadow: 0 0 10px #ffb000, 0 0 20px #ffb000; }
    .glow-red { text-shadow: 0 0 10px #ff3366, 0 0 20px #ff3366; }
    .box-glow-green { box-shadow: 0 0 15px rgba(0, 255, 65, 0.3), inset 0 0 15px rgba(0, 255, 65, 0.1); }
    .box-glow-cyan { box-shadow: 0 0 15px rgba(0, 212, 255, 0.3), inset 0 0 15px rgba(0, 212, 255, 0.1); }
    .box-glow-red { box-shadow: 0 0 15px rgba(255, 51, 102, 0.3), inset 0 0 15px rgba(255, 51, 102, 0.1); }
    /* Terminal decorations */
    .terminal-border {
        border: 1px solid #1e3a5f;
        position: relative;
    }
    .terminal-border::before {
        content: '';
        position: absolute;
        top: -1px;
        left: 10px;
        right: 10px;
        height: 1px;
        background: linear-gradient(90deg, transparent, #00ff41, transparent);
    }
    /* ASCII-style corners */
    .corner-decoration {
        position: relative;
    }
    .corner-decoration::before,
    .corner-decoration::after {
        position: absolute;
        color: #1e3a5f;
        font-size: 12px;
    }
    .corner-decoration::before {
        content: '╔';
        top: -8px;
        left: -8px;
    }
    .corner-decoration::after {
        content: '╝';
        bottom: -8px;
        right: -8px;
    }
    /* Table styles */
    table {
        width: 100%;
        border-collapse: collapse;
        font-size: 0.85rem;
    }
    th, td {
        text-align: left;
        padding: 12px 16px;
        border-bottom: 1px solid #1e3a5f;
    }
    th {
        background: rgba(0, 212, 255, 0.1);
        color: #00d4ff;
        font-weight: 600;
        text-transform: uppercase;
        font-size: 0.75rem;
        letter-spacing: 0.05em;
    }
    tr:hover {
        background: rgba(0, 255, 65, 0.05);
    }
    /* Status badges */
    .status-badge {
        padding: 4px 12px;
        border-radius: 4px;
        font-size: 0.75rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    .status-active, .status-available, .status-healthy {
        background: rgba(0, 255, 65, 0.2);
        color: #00ff41;
        border: 1px solid #00ff41;
    }
    .status-build, .status-creating {
        background: rgba(255, 176, 0, 0.2);
        color: #ffb000;
        border: 1px solid #ffb000;
    }
    .status-error, .status-failed {
        background: rgba(255, 51, 102, 0.2);
        color: #ff3366;
        border: 1px solid #ff3366;
    }
    .status-down, .status-shutoff {
        background: rgba(74, 85, 104, 0.3);
        color: #718096;
        border: 1px solid #4a5568;
    }
    /* Tabs */
    .tabs {
        display: flex;
        gap: 4px;
        margin-bottom: 20px;
        border-bottom: 1px solid #1e3a5f;
        padding-bottom: 0;
    }
    .tab {
        padding: 12px 24px;
        border: none;
        background: transparent;
        cursor: pointer;
        font-size: 0.85rem;
        color: #4a5568;
        font-family: 'JetBrains Mono', monospace;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        border-bottom: 2px solid transparent;
        transition: all 0.2s;
    }
    .tab:hover {
        color: #00d4ff;
        background: rgba(0, 212, 255, 0.1);
    }
    .tab.active {
        color: #00ff41;
        border-bottom-color: #00ff41;
        background: rgba(0, 255, 65, 0.1);
    }
    .tab-content {
        display: none;
    }
    .tab-content.active {
        display: block;
    }
    /* Buttons */
    .btn {
        font-family: 'JetBrains Mono', monospace;
        padding: 10px 20px;
        border: 1px solid;
        cursor: pointer;
        font-size: 0.85rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        transition: all 0.2s;
        background: transparent;
    }
    .btn-primary {
        color: #00d4ff;
        border-color: #00d4ff;
    }
    .btn-primary:hover {
        background: rgba(0, 212, 255, 0.2);
        box-shadow: 0 0 15px rgba(0, 212, 255, 0.4);
    }
    .btn-success {
        color: #00ff41;
        border-color: #00ff41;
    }
    .btn-success:hover {
        background: rgba(0, 255, 65, 0.2);
        box-shadow: 0 0 15px rgba(0, 255, 65, 0.4);
    }
    .btn-danger {
        color: #ff3366;
        border-color: #ff3366;
    }
    .btn-danger:hover {
        background: rgba(255, 51, 102, 0.2);
        box-shadow: 0 0 15px rgba(255, 51, 102, 0.4);
    }
    .btn-secondary {
        color: #718096;
        border-color: #4a5568;
    }
    .btn-secondary:hover {
        background: rgba(74, 85, 104, 0.3);
    }
    .btn-sm {
        padding: 6px 12px;
        font-size: 0.75rem;
    }
    /* Action buttons */
    .action-btns {
        display: flex;
        gap: 6px;
    }
    .action-btn {
        padding: 4px 10px;
        font-size: 0.7rem;
        cursor: pointer;
        border: 1px solid;
        background: transparent;
        font-family: 'JetBrains Mono', monospace;
        text-transform: uppercase;
        transition: all 0.2s;
    }
    .action-btn.edit {
        color: #00d4ff;
        border-color: #00d4ff;
    }
    .action-btn.edit:hover {
        background: rgba(0, 212, 255, 0.2);
    }
    .action-btn.delete {
        color: #ff3366;
        border-color: #ff3366;
    }
    .action-btn.delete:hover {
        background: rgba(255, 51, 102, 0.2);
    }
    /* Modal styles */
    .modal {
        display: none;
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0, 0, 0, 0.85);
        z-index: 1000;
        align-items: center;
        justify-content: center;
        backdrop-filter: blur(4px);
    }
    .modal.active {
        display: flex;
    }
    .modal-content {
        background: #0d1117;
        border: 1px solid #00d4ff;
        padding: 30px;
        width: 90%;
        max-width: 500px;
        max-height: 90vh;
        overflow-y: auto;
        box-shadow: 0 0 30px rgba(0, 212, 255, 0.3), inset 0 0 30px rgba(0, 212, 255, 0.05);
        position: relative;
    }
    .modal-content::before {
        content: '[ TERMINAL INPUT ]';
        position: absolute;
        top: -12px;
        left: 20px;
        background: #0d1117;
        padding: 0 10px;
        color: #00d4ff;
        font-size: 0.7rem;
        letter-spacing: 0.1em;
    }
    .modal-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 20px;
        padding-bottom: 15px;
        border-bottom: 1px solid #1e3a5f;
    }
    .modal-header h3 {
        font-size: 1rem;
        color: #00ff41;
        text-transform: uppercase;
        letter-spacing: 0.1em;
    }
    .modal-close {
        background: none;
        border: 1px solid #ff3366;
        font-size: 1.2rem;
        cursor: pointer;
        color: #ff3366;
        padding: 2px 8px;
        line-height: 1;
        transition: all 0.2s;
    }
    .modal-close:hover {
        background: rgba(255, 51, 102, 0.2);
        box-shadow: 0 0 10px rgba(255, 51, 102, 0.4);
    }
    /* Form styles */
    .form-group {
        margin-bottom: 20px;
    }
    .form-group label {
        display: block;
        margin-bottom: 8px;
        color: #00d4ff;
        font-size: 0.8rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    .form-group input, .form-group select, .form-group textarea {
        width: 100%;
        padding: 12px 14px;
        background: rgba(0, 0, 0, 0.5);
        border: 1px solid #1e3a5f;
        color: #e2e8f0;
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.9rem;
        transition: all 0.2s;
    }
    .form-group input:focus, .form-group select:focus, .form-group textarea:focus {
        outline: none;
        border-color: #00ff41;
        box-shadow: 0 0 10px rgba(0, 255, 65, 0.3);
    }
    .form-group input::placeholder {
        color: #4a5568;
    }
    .form-group input[type="checkbox"] {
        width: auto;
        margin-right: 10px;
        accent-color: #00ff41;
    }
    .form-group .checkbox-label {
        display: flex;
        align-items: center;
        cursor: pointer;
        color: #e2e8f0;
    }
    .form-group select {
        cursor: pointer;
    }
    .form-group select option {
        background: #0d1117;
        color: #e2e8f0;
    }
    .form-actions {
        display: flex;
        gap: 12px;
        justify-content: flex-end;
        margin-top: 25px;
        padding-top: 20px;
        border-top: 1px solid #1e3a5f;
    }
    .form-error {
        background: rgba(255, 51, 102, 0.2);
        color: #ff3366;
        padding: 12px 15px;
        border: 1px solid #ff3366;
        margin-bottom: 15px;
        font-size: 0.85rem;
    }
    .form-success {
        background: rgba(0, 255, 65, 0.2);
        color: #00ff41;
        padding: 12px 15px;
        border: 1px solid #00ff41;
        margin-bottom: 15px;
        font-size: 0.85rem;
    }
    /* Toast notifications */
    .toast-container {
        position: fixed;
        top: 20px;
        right: 20px;
        z-index: 2000;
    }
    .toast {
        background: #0d1117;
        color: #e2e8f0;
        padding: 15px 20px;
        border: 1px solid #1e3a5f;
        margin-bottom: 10px;
        font-size: 0.85rem;
        animation: slideIn 0.3s ease;
    }
    .toast.success {
        border-color: #00ff41;
        color: #00ff41;
        box-shadow: 0 0 15px rgba(0, 255, 65, 0.3);
    }
    .toast.error {
        border-color: #ff3366;
        color: #ff3366;
        box-shadow: 0 0 15px rgba(255, 51, 102, 0.3);
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
    /* Scrollbar */
    ::-webkit-scrollbar {
        width: 8px;
        height: 8px;
    }
    ::-webkit-scrollbar-track {
        background: #0a0a0f;
    }
    ::-webkit-scrollbar-thumb {
        background: #1e3a5f;
        border-radius: 4px;
    }
    ::-webkit-scrollbar-thumb:hover {
        background: #00d4ff;
    }
    /* Utility classes for terminal elements */
    .terminal-prompt::before {
        content: '>';
        color: #00ff41;
        margin-right: 8px;
    }
    .blinking-cursor::after {
        content: '_';
        animation: blink 1s step-end infinite;
    }
    @keyframes blink {
        50% { opacity: 0; }
    }
    /* UUID styling with tooltip */
    .uuid {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.8rem;
        color: #a855f7;
        cursor: pointer;
        position: relative;
    }
    .uuid:hover {
        color: #c084fc;
    }
    .uuid-value {
        position: relative;
        display: inline-block;
    }
    .uuid-value::after {
        content: attr(data-full);
        position: absolute;
        bottom: 100%;
        left: 0;
        background: #0d1117;
        border: 1px solid #00d4ff;
        color: #00ff41;
        padding: 8px 12px;
        font-size: 0.75rem;
        white-space: nowrap;
        opacity: 0;
        visibility: hidden;
        transition: opacity 0.2s, visibility 0.2s;
        z-index: 1000;
        box-shadow: 0 0 15px rgba(0, 212, 255, 0.3);
        margin-bottom: 5px;
    }
    .uuid-value:hover::after {
        opacity: 1;
        visibility: visible;
    }
    /* Click to copy feedback */
    .uuid-value.copied::after {
        content: 'Copied!';
        background: #00ff41;
        color: #0a0a0f;
        border-color: #00ff41;
    }
    /* Clickable service cards */
    .service-card-link {
        cursor: pointer;
        transition: transform 0.2s;
    }
    .service-card-link:hover {
        transform: translateY(-2px);
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

    // Copy UUID to clipboard
    function copyUuid(element) {
        const uuid = element.getAttribute('data-full');
        navigator.clipboard.writeText(uuid).then(() => {
            element.classList.add('copied');
            showToast('UUID copied to clipboard', 'success');
            setTimeout(() => {
                element.classList.remove('copied');
            }, 1500);
        }).catch(err => {
            // Fallback for older browsers
            const textArea = document.createElement('textarea');
            textArea.value = uuid;
            document.body.appendChild(textArea);
            textArea.select();
            document.execCommand('copy');
            document.body.removeChild(textArea);
            element.classList.add('copied');
            showToast('UUID copied to clipboard', 'success');
            setTimeout(() => {
                element.classList.remove('copied');
            }, 1500);
        });
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
        return '<div class="text-center py-8 text-[#4a5568]">[ NO SERVERS FOUND ]</div>'

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
            <td class="uuid"><span class="uuid-value" data-full="{server.id}" onclick="copyUuid(this)">{server.id[:13]}...</span></td>
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
        return '<div class="text-center py-8 text-[#4a5568]">[ NO VOLUMES FOUND ]</div>'

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
            <td class="uuid"><span class="uuid-value" data-full="{volume.id}" onclick="copyUuid(this)">{volume.id[:13]}...</span></td>
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
        return '<div class="text-center py-8 text-[#4a5568]">[ NO IMAGES FOUND ]</div>'

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
            <td class="uuid"><span class="uuid-value" data-full="{image.id}" onclick="copyUuid(this)">{image.id[:13]}...</span></td>
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
        return '<div class="text-center py-8 text-[#4a5568]">[ NO NETWORKS FOUND ]</div>'

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
            <td class="uuid"><span class="uuid-value" data-full="{network.id}" onclick="copyUuid(this)">{network.id[:13]}...</span></td>
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
        return '<div class="text-center py-8 text-[#4a5568]">[ NO SUBNETS FOUND ]</div>'

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
            <td class="uuid"><span class="uuid-value" data-full="{subnet.id}" onclick="copyUuid(this)">{subnet.id[:13]}...</span></td>
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
        return '<div class="text-center py-8 text-[#4a5568]">[ NO PORTS FOUND ]</div>'

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
            <td class="uuid"><span class="uuid-value" data-full="{port.id}" onclick="copyUuid(this)">{port.id[:13]}...</span></td>
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
        return '<div class="text-center py-8 text-[#4a5568]">[ NO ROUTERS FOUND ]</div>'

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
            <td class="uuid"><span class="uuid-value" data-full="{router.id}" onclick="copyUuid(this)">{router.id[:13]}...</span></td>
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
        return '<div class="text-center py-8 text-[#4a5568]">[ NO FLOATING IPS ALLOCATED ]</div>'

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
            <td class="uuid"><span class="uuid-value" data-full="{fip.id}" onclick="copyUuid(this)">{fip.id[:13]}...</span></td>
            <td>{fip.floating_ip_address}</td>
            <td><span class="status-badge {status_class}">{status}</span></td>
            <td>{fip.fixed_ip_address or '-'}</td>
            <td class="uuid">{f'<span class="uuid-value" data-full="{fip.port_id}" onclick="copyUuid(this)">{fip.port_id[:13]}...</span>' if fip.port_id else '-'}</td>
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
        return '<div class="text-center py-8 text-[#4a5568]">[ NO SECURITY GROUPS FOUND ]</div>'

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
            <td class="uuid"><span class="uuid-value" data-full="{sg.id}" onclick="copyUuid(this)">{sg.id[:13]}...</span></td>
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
        return '<div class="text-center py-8 text-[#4a5568]">[ NO PROJECTS FOUND ]</div>'

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
            <td class="uuid"><span class="uuid-value" data-full="{project.id}" onclick="copyUuid(this)">{project.id[:13]}...</span></td>
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
        return '<div class="text-center py-8 text-[#4a5568]">[ NO USERS FOUND ]</div>'

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
            <td class="uuid"><span class="uuid-value" data-full="{user.id}" onclick="copyUuid(this)">{user.id[:13]}...</span></td>
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
        return '<div class="text-center py-8 text-[#4a5568]">[ NO FLAVORS FOUND ]</div>'

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
        return '<div class="text-center py-8 text-[#4a5568]">[ NO KEYPAIRS FOUND ]</div>'

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
        return '<div class="text-center py-8 text-[#4a5568]">[ NO SNAPSHOTS FOUND ]</div>'

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
            <td class="uuid"><span class="uuid-value" data-full="{snapshot.id}" onclick="copyUuid(this)">{snapshot.id[:13]}...</span></td>
            <td>{snapshot.name or '-'}</td>
            <td><span class="status-badge {status_class}">{status}</span></td>
            <td>{snapshot.size} GB</td>
            <td class="uuid"><span class="uuid-value" data-full="{snapshot.volume_id}" onclick="copyUuid(this)">{snapshot.volume_id[:13]}...</span></td>
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
    # Map services to resource tabs
    service_to_tab = {
        "keystone": "identity",
        "nova": "compute",
        "cinder": "storage",
        "glance": "storage",
        "neutron": "network",
    }
    service_cards = ""
    for service, status in service_status.items():
        if status["healthy"]:
            glow_class = "box-glow-green"
            border_color = "border-[#00ff41]"
            status_color = "text-[#00ff41]"
            status_text = "ONLINE"
            indicator = "animate-pulse"
        else:
            glow_class = "box-glow-red"
            border_color = "border-[#ff3366]"
            status_color = "text-[#ff3366]"
            status_text = "OFFLINE"
            indicator = ""
        target_tab = service_to_tab.get(service, "compute")
        service_cards += f"""
        <div class="bg-[#0d1117] border {border_color} p-5 {glow_class} relative service-card-link" onclick="switchTab('{target_tab}')" title="Click to view {target_tab} resources">
            <div class="absolute top-2 right-2 w-2 h-2 rounded-full bg-current {status_color} {indicator}"></div>
            <div class="text-[#00d4ff] text-xs uppercase tracking-wider mb-1">{status['name']}</div>
            <div class="text-lg font-semibold text-[#e2e8f0] mb-3">{service.upper()}</div>
            <div class="text-xs text-[#4a5568] space-y-1">
                <div>PORT: <span class="text-[#ffb000]">{status['port']}</span></div>
                <div>STATUS: <span class="{status_color}">{status_text}</span></div>
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
    if authenticated and current_user:
        auth_section = f"""
        <div class="flex items-center gap-4">
            <div class="flex items-center gap-3">
                <div class="w-9 h-9 bg-[#00ff41] bg-opacity-20 border border-[#00ff41] flex items-center justify-center text-[#00ff41] font-bold text-sm">{current_user['name'][0].upper()}</div>
                <div>
                    <div class="text-[#00ff41] text-sm">{current_user['name']}</div>
                    <div class="text-[#4a5568] text-xs">{current_user['project_name'] or 'No project'}</div>
                </div>
            </div>
            <button class="btn btn-danger btn-sm" onclick="handleLogout()">LOGOUT</button>
        </div>
        """
    else:
        auth_section = """
        <div class="flex items-center">
            <button class="btn btn-success" onclick="openModal('login-modal')">LOGIN</button>
        </div>
        """

    # Build readonly notice for unauthenticated users
    readonly_notice = ""
    if not authenticated:
        readonly_notice = """
        <div class="bg-[#ffb000] bg-opacity-10 border border-[#ffb000] text-[#ffb000] px-5 py-3 mb-6 flex items-center gap-3 text-sm">
            <span class="text-lg">!</span>
            <span>READ-ONLY MODE // <a href="#" onclick="openModal('login-modal'); return false;" class="underline hover:text-white">AUTHENTICATE</a> to access system controls</span>
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
        <title>OPENSTACK EMULATOR // SYSTEM STATUS</title>
        {CSS_STYLES}
    </head>
    <body class="min-h-screen">
        <div id="toast-container" class="toast-container"></div>

        <!-- Header -->
        <header class="bg-[#0d1117] border-b border-[#1e3a5f] py-6 mb-8">
            <div class="max-w-7xl mx-auto px-6">
                <div class="flex justify-between items-center">
                    <div>
                        <div class="text-[#4a5568] text-xs uppercase tracking-widest mb-1">// SYSTEM INTERFACE v1.0</div>
                        <h1 class="text-2xl font-bold text-[#00ff41] glow-green tracking-wide">OPENSTACK EMULATOR</h1>
                        <p class="text-[#00d4ff] text-sm mt-1">Real-time monitoring &amp; resource management</p>
                    </div>
                    <div class="flex items-center gap-4">
                        <button class="btn btn-primary" onclick="location.reload()">
                            <span class="mr-2">↻</span> REFRESH
                        </button>
                        {auth_section}
                    </div>
                </div>
            </div>
        </header>

        <div class="max-w-7xl mx-auto px-6 pb-12">
            {readonly_notice}

            <!-- Service Status Cards -->
            <div class="mb-8">
                <div class="flex items-center gap-3 mb-4">
                    <span class="text-[#00d4ff] text-lg">■</span>
                    <h2 class="text-lg font-semibold text-[#00d4ff] uppercase tracking-wider">Service Status</h2>
                    <div class="flex-1 h-px bg-gradient-to-r from-[#1e3a5f] to-transparent"></div>
                </div>
                <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-4">
                    {service_cards}
                </div>
            </div>

            <!-- Tabbed Resources -->
            <div class="bg-[#0d1117] border border-[#1e3a5f] p-6">
                <div class="flex items-center gap-3 mb-6">
                    <span class="text-[#00ff41] text-lg">■</span>
                    <h2 class="text-lg font-semibold text-[#00ff41] uppercase tracking-wider">Resources</h2>
                    <div class="flex-1 h-px bg-gradient-to-r from-[#1e3a5f] to-transparent"></div>
                </div>

                <div class="tabs">
                    <button class="tab active" data-tab="compute" onclick="switchTab('compute')">[ COMPUTE ]</button>
                    <button class="tab" data-tab="storage" onclick="switchTab('storage')">[ STORAGE ]</button>
                    <button class="tab" data-tab="network" onclick="switchTab('network')">[ NETWORK ]</button>
                    <button class="tab" data-tab="identity" onclick="switchTab('identity')">[ IDENTITY ]</button>
                </div>

                <!-- Compute Tab -->
                <div id="tab-compute" class="tab-content active">
                    <div class="mb-8">
                        <div class="flex justify-between items-center mb-4">
                            <h3 class="text-[#00d4ff] uppercase tracking-wider flex items-center gap-2">
                                <span class="text-[#ffb000]">&gt;</span> Servers
                                <span class="bg-[#00d4ff] bg-opacity-20 text-[#00d4ff] px-2 py-0.5 text-xs border border-[#00d4ff]">{len(servers)}</span>
                            </h3>
                            {create_btn('create-server-modal', '+ NEW')}
                        </div>
                        {render_servers_table(servers, authenticated)}
                    </div>
                    <div class="mb-8">
                        <div class="flex justify-between items-center mb-4">
                            <h3 class="text-[#00d4ff] uppercase tracking-wider flex items-center gap-2">
                                <span class="text-[#ffb000]">&gt;</span> Flavors
                                <span class="bg-[#00d4ff] bg-opacity-20 text-[#00d4ff] px-2 py-0.5 text-xs border border-[#00d4ff]">{len(flavors)}</span>
                            </h3>
                        </div>
                        {render_flavors_table(flavors, authenticated)}
                    </div>
                    <div class="mb-8">
                        <div class="flex justify-between items-center mb-4">
                            <h3 class="text-[#00d4ff] uppercase tracking-wider flex items-center gap-2">
                                <span class="text-[#ffb000]">&gt;</span> Keypairs
                                <span class="bg-[#00d4ff] bg-opacity-20 text-[#00d4ff] px-2 py-0.5 text-xs border border-[#00d4ff]">{len(keypairs)}</span>
                            </h3>
                        </div>
                        {render_keypairs_table(keypairs, authenticated)}
                    </div>
                </div>

                <!-- Storage Tab -->
                <div id="tab-storage" class="tab-content">
                    <div class="mb-8">
                        <div class="flex justify-between items-center mb-4">
                            <h3 class="text-[#00d4ff] uppercase tracking-wider flex items-center gap-2">
                                <span class="text-[#ffb000]">&gt;</span> Images
                                <span class="bg-[#00d4ff] bg-opacity-20 text-[#00d4ff] px-2 py-0.5 text-xs border border-[#00d4ff]">{len(images)}</span>
                            </h3>
                            {create_btn('create-image-modal', '+ NEW')}
                        </div>
                        {render_images_table(images, authenticated)}
                    </div>
                    <div class="mb-8">
                        <div class="flex justify-between items-center mb-4">
                            <h3 class="text-[#00d4ff] uppercase tracking-wider flex items-center gap-2">
                                <span class="text-[#ffb000]">&gt;</span> Volumes
                                <span class="bg-[#00d4ff] bg-opacity-20 text-[#00d4ff] px-2 py-0.5 text-xs border border-[#00d4ff]">{len(volumes)}</span>
                            </h3>
                            {create_btn('create-volume-modal', '+ NEW')}
                        </div>
                        {render_volumes_table(volumes, authenticated)}
                    </div>
                    <div class="mb-8">
                        <div class="flex justify-between items-center mb-4">
                            <h3 class="text-[#00d4ff] uppercase tracking-wider flex items-center gap-2">
                                <span class="text-[#ffb000]">&gt;</span> Snapshots
                                <span class="bg-[#00d4ff] bg-opacity-20 text-[#00d4ff] px-2 py-0.5 text-xs border border-[#00d4ff]">{len(snapshots)}</span>
                            </h3>
                            {create_btn('create-snapshot-modal', '+ NEW')}
                        </div>
                        {render_snapshots_table(snapshots, authenticated)}
                    </div>
                </div>

                <!-- Network Tab -->
                <div id="tab-network" class="tab-content">
                    <div class="mb-8">
                        <div class="flex justify-between items-center mb-4">
                            <h3 class="text-[#00d4ff] uppercase tracking-wider flex items-center gap-2">
                                <span class="text-[#ffb000]">&gt;</span> Networks
                                <span class="bg-[#00d4ff] bg-opacity-20 text-[#00d4ff] px-2 py-0.5 text-xs border border-[#00d4ff]">{len(networks)}</span>
                            </h3>
                            {create_btn('create-network-modal', '+ NEW')}
                        </div>
                        {render_networks_table(networks, authenticated)}
                    </div>
                    <div class="mb-8">
                        <div class="flex justify-between items-center mb-4">
                            <h3 class="text-[#00d4ff] uppercase tracking-wider flex items-center gap-2">
                                <span class="text-[#ffb000]">&gt;</span> Subnets
                                <span class="bg-[#00d4ff] bg-opacity-20 text-[#00d4ff] px-2 py-0.5 text-xs border border-[#00d4ff]">{len(subnets)}</span>
                            </h3>
                            {create_btn('create-subnet-modal', '+ NEW')}
                        </div>
                        {render_subnets_table(subnets, authenticated)}
                    </div>
                    <div class="mb-8">
                        <div class="flex justify-between items-center mb-4">
                            <h3 class="text-[#00d4ff] uppercase tracking-wider flex items-center gap-2">
                                <span class="text-[#ffb000]">&gt;</span> Ports
                                <span class="bg-[#00d4ff] bg-opacity-20 text-[#00d4ff] px-2 py-0.5 text-xs border border-[#00d4ff]">{len(ports)}</span>
                            </h3>
                        </div>
                        {render_ports_table(ports, authenticated)}
                    </div>
                    <div class="mb-8">
                        <div class="flex justify-between items-center mb-4">
                            <h3 class="text-[#00d4ff] uppercase tracking-wider flex items-center gap-2">
                                <span class="text-[#ffb000]">&gt;</span> Routers
                                <span class="bg-[#00d4ff] bg-opacity-20 text-[#00d4ff] px-2 py-0.5 text-xs border border-[#00d4ff]">{len(routers)}</span>
                            </h3>
                            {create_btn('create-router-modal', '+ NEW')}
                        </div>
                        {render_routers_table(routers, authenticated)}
                    </div>
                    <div class="mb-8">
                        <div class="flex justify-between items-center mb-4">
                            <h3 class="text-[#00d4ff] uppercase tracking-wider flex items-center gap-2">
                                <span class="text-[#ffb000]">&gt;</span> Floating IPs
                                <span class="bg-[#00d4ff] bg-opacity-20 text-[#00d4ff] px-2 py-0.5 text-xs border border-[#00d4ff]">{len(floating_ips)}</span>
                            </h3>
                            {create_btn('create-floating-ip-modal', '+ ALLOCATE')}
                        </div>
                        {render_floating_ips_table(floating_ips, authenticated)}
                    </div>
                    <div class="mb-8">
                        <div class="flex justify-between items-center mb-4">
                            <h3 class="text-[#00d4ff] uppercase tracking-wider flex items-center gap-2">
                                <span class="text-[#ffb000]">&gt;</span> Security Groups
                                <span class="bg-[#00d4ff] bg-opacity-20 text-[#00d4ff] px-2 py-0.5 text-xs border border-[#00d4ff]">{len(security_groups)}</span>
                            </h3>
                            {create_btn('create-security-group-modal', '+ NEW')}
                        </div>
                        {render_security_groups_table(security_groups, authenticated)}
                    </div>
                </div>

                <!-- Identity Tab -->
                <div id="tab-identity" class="tab-content">
                    <div class="mb-8">
                        <div class="flex justify-between items-center mb-4">
                            <h3 class="text-[#00d4ff] uppercase tracking-wider flex items-center gap-2">
                                <span class="text-[#ffb000]">&gt;</span> Projects
                                <span class="bg-[#00d4ff] bg-opacity-20 text-[#00d4ff] px-2 py-0.5 text-xs border border-[#00d4ff]">{len(projects)}</span>
                            </h3>
                            {create_btn('create-project-modal', '+ NEW')}
                        </div>
                        {render_projects_table(projects, authenticated)}
                    </div>
                    <div class="mb-8">
                        <div class="flex justify-between items-center mb-4">
                            <h3 class="text-[#00d4ff] uppercase tracking-wider flex items-center gap-2">
                                <span class="text-[#ffb000]">&gt;</span> Users
                                <span class="bg-[#00d4ff] bg-opacity-20 text-[#00d4ff] px-2 py-0.5 text-xs border border-[#00d4ff]">{len(users)}</span>
                            </h3>
                            {create_btn('create-user-modal', '+ NEW')}
                        </div>
                        {render_users_table(users, authenticated)}
                    </div>
                </div>
            </div>

            <!-- Footer -->
            <div class="mt-8 text-center text-[#4a5568] text-xs">
                <div class="mb-2">═══════════════════════════════════════════════════════════════</div>
                <div>OPENSTACK EMULATOR // DEVELOPMENT &amp; TESTING ENVIRONMENT</div>
                <div class="text-[#1e3a5f] mt-1">Auto-refresh in 30 seconds</div>
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

    if not subnet:
        raise HTTPException(status_code=500, detail="Failed to create subnet")

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
