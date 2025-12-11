"""Status UI routes for displaying emulator state.

Provides a web interface to view the status of all services and objects
in the OpenStack emulator.
"""

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from emulator.core.database import db

router = APIRouter()

# Service configuration (must match emulator/__init__.py)
SERVICES = {
    "keystone": {"port": 5000, "name": "Identity"},
    "nova": {"port": 8774, "name": "Compute"},
    "cinder": {"port": 8776, "name": "Block Storage"},
    "glance": {"port": 9292, "name": "Image"},
    "neutron": {"port": 9696, "name": "Networking"},
}

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
    .refresh-btn {
        background: #667eea;
        color: white;
        border: none;
        padding: 10px 20px;
        border-radius: 8px;
        cursor: pointer;
        font-size: 0.9rem;
    }
    .refresh-btn:hover {
        background: #5a67d8;
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
</style>
"""

# JavaScript for interactivity
JS_SCRIPT = """
<script>
    function switchTab(tabName) {
        // Hide all tab contents
        document.querySelectorAll('.tab-content').forEach(el => {
            el.classList.remove('active');
        });
        // Remove active from all tabs
        document.querySelectorAll('.tab').forEach(el => {
            el.classList.remove('active');
        });
        // Show selected tab content
        document.getElementById('tab-' + tabName).classList.add('active');
        // Mark selected tab as active
        document.querySelector('[data-tab="' + tabName + '"]').classList.add('active');
    }

    // Auto-refresh every 30 seconds
    setTimeout(function() {
        location.reload();
    }, 30000);
</script>
"""


async def check_service_health(host: str, port: int) -> bool:
    """Check if a service is healthy by calling its health endpoint."""
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(f"http://{host}:{port}/health")
            return response.status_code == 200
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


def render_servers_table(servers: list) -> str:
    """Render the servers table HTML."""
    if not servers:
        return '<div class="empty-state">No servers created yet</div>'

    rows = ""
    for server in servers:
        status = server.status.value if hasattr(server.status, "value") else str(server.status)
        status_class = get_status_class(status)
        created = getattr(server, "created", None)
        created_str = created.strftime("%Y-%m-%d %H:%M:%S") if created else "-"
        rows += f"""
        <tr>
            <td class="uuid">{server.id[:8]}...</td>
            <td>{server.name}</td>
            <td><span class="status-badge {status_class}">{status}</span></td>
            <td>{server.flavor_id}</td>
            <td>{created_str}</td>
        </tr>
        """

    return f"""
    <table>
        <thead>
            <tr>
                <th>ID</th>
                <th>Name</th>
                <th>Status</th>
                <th>Flavor</th>
                <th>Created</th>
            </tr>
        </thead>
        <tbody>{rows}</tbody>
    </table>
    """


def render_volumes_table(volumes: list) -> str:
    """Render the volumes table HTML."""
    if not volumes:
        return '<div class="empty-state">No volumes created yet</div>'

    rows = ""
    for volume in volumes:
        status = volume.status.value if hasattr(volume.status, "value") else str(volume.status)
        status_class = get_status_class(status)
        rows += f"""
        <tr>
            <td class="uuid">{volume.id[:8]}...</td>
            <td>{volume.name or '-'}</td>
            <td><span class="status-badge {status_class}">{status}</span></td>
            <td>{volume.size} GB</td>
            <td>{volume.volume_type or 'default'}</td>
        </tr>
        """

    return f"""
    <table>
        <thead>
            <tr>
                <th>ID</th>
                <th>Name</th>
                <th>Status</th>
                <th>Size</th>
                <th>Type</th>
            </tr>
        </thead>
        <tbody>{rows}</tbody>
    </table>
    """


def render_images_table(images: list) -> str:
    """Render the images table HTML."""
    if not images:
        return '<div class="empty-state">No images available</div>'

    rows = ""
    for image in images:
        status = image.status.value if hasattr(image.status, "value") else str(image.status)
        status_class = get_status_class(status)
        visibility = image.visibility.value if hasattr(image.visibility, "value") else str(image.visibility)
        size_mb = (image.size or 0) // (1024 * 1024)
        rows += f"""
        <tr>
            <td class="uuid">{image.id[:8]}...</td>
            <td>{image.name}</td>
            <td><span class="status-badge {status_class}">{status}</span></td>
            <td>{visibility}</td>
            <td>{size_mb} MB</td>
        </tr>
        """

    return f"""
    <table>
        <thead>
            <tr>
                <th>ID</th>
                <th>Name</th>
                <th>Status</th>
                <th>Visibility</th>
                <th>Size</th>
            </tr>
        </thead>
        <tbody>{rows}</tbody>
    </table>
    """


def render_networks_table(networks: list) -> str:
    """Render the networks table HTML."""
    if not networks:
        return '<div class="empty-state">No networks created yet</div>'

    rows = ""
    for network in networks:
        status = network.status.value if hasattr(network.status, "value") else str(network.status)
        status_class = get_status_class(status)
        external = "Yes" if network.external else "No"
        rows += f"""
        <tr>
            <td class="uuid">{network.id[:8]}...</td>
            <td>{network.name}</td>
            <td><span class="status-badge {status_class}">{status}</span></td>
            <td>{external}</td>
            <td>{'Yes' if network.shared else 'No'}</td>
        </tr>
        """

    return f"""
    <table>
        <thead>
            <tr>
                <th>ID</th>
                <th>Name</th>
                <th>Status</th>
                <th>External</th>
                <th>Shared</th>
            </tr>
        </thead>
        <tbody>{rows}</tbody>
    </table>
    """


def render_subnets_table(subnets: list) -> str:
    """Render the subnets table HTML."""
    if not subnets:
        return '<div class="empty-state">No subnets created yet</div>'

    rows = ""
    for subnet in subnets:
        rows += f"""
        <tr>
            <td class="uuid">{subnet.id[:8]}...</td>
            <td>{subnet.name or '-'}</td>
            <td>{subnet.cidr}</td>
            <td>{subnet.gateway_ip or '-'}</td>
            <td>{'Yes' if subnet.enable_dhcp else 'No'}</td>
        </tr>
        """

    return f"""
    <table>
        <thead>
            <tr>
                <th>ID</th>
                <th>Name</th>
                <th>CIDR</th>
                <th>Gateway</th>
                <th>DHCP</th>
            </tr>
        </thead>
        <tbody>{rows}</tbody>
    </table>
    """


def render_ports_table(ports: list) -> str:
    """Render the ports table HTML."""
    if not ports:
        return '<div class="empty-state">No ports created yet</div>'

    rows = ""
    for port in ports:
        status = port.status.value if hasattr(port.status, "value") else str(port.status)
        status_class = get_status_class(status)
        fixed_ips = ", ".join([ip.ip_address for ip in port.fixed_ips]) if port.fixed_ips else "-"
        rows += f"""
        <tr>
            <td class="uuid">{port.id[:8]}...</td>
            <td>{port.name or '-'}</td>
            <td><span class="status-badge {status_class}">{status}</span></td>
            <td>{port.mac_address}</td>
            <td>{fixed_ips}</td>
        </tr>
        """

    return f"""
    <table>
        <thead>
            <tr>
                <th>ID</th>
                <th>Name</th>
                <th>Status</th>
                <th>MAC Address</th>
                <th>Fixed IPs</th>
            </tr>
        </thead>
        <tbody>{rows}</tbody>
    </table>
    """


def render_routers_table(routers: list) -> str:
    """Render the routers table HTML."""
    if not routers:
        return '<div class="empty-state">No routers created yet</div>'

    rows = ""
    for router in routers:
        status = router.status.value if hasattr(router.status, "value") else str(router.status)
        status_class = get_status_class(status)
        ext_gateway = "Yes" if router.external_gateway_info else "No"
        rows += f"""
        <tr>
            <td class="uuid">{router.id[:8]}...</td>
            <td>{router.name}</td>
            <td><span class="status-badge {status_class}">{status}</span></td>
            <td>{'Yes' if router.admin_state_up else 'No'}</td>
            <td>{ext_gateway}</td>
        </tr>
        """

    return f"""
    <table>
        <thead>
            <tr>
                <th>ID</th>
                <th>Name</th>
                <th>Status</th>
                <th>Admin State</th>
                <th>External Gateway</th>
            </tr>
        </thead>
        <tbody>{rows}</tbody>
    </table>
    """


def render_floating_ips_table(floating_ips: list) -> str:
    """Render the floating IPs table HTML."""
    if not floating_ips:
        return '<div class="empty-state">No floating IPs allocated yet</div>'

    rows = ""
    for fip in floating_ips:
        status = fip.status.value if hasattr(fip.status, "value") else str(fip.status)
        status_class = get_status_class(status)
        rows += f"""
        <tr>
            <td class="uuid">{fip.id[:8]}...</td>
            <td>{fip.floating_ip_address}</td>
            <td><span class="status-badge {status_class}">{status}</span></td>
            <td>{fip.fixed_ip_address or '-'}</td>
            <td class="uuid">{fip.port_id[:8] + '...' if fip.port_id else '-'}</td>
        </tr>
        """

    return f"""
    <table>
        <thead>
            <tr>
                <th>ID</th>
                <th>Floating IP</th>
                <th>Status</th>
                <th>Fixed IP</th>
                <th>Port</th>
            </tr>
        </thead>
        <tbody>{rows}</tbody>
    </table>
    """


def render_security_groups_table(security_groups: list) -> str:
    """Render the security groups table HTML."""
    if not security_groups:
        return '<div class="empty-state">No security groups created yet</div>'

    rows = ""
    for sg in security_groups:
        rule_count = len(db.list_security_group_rules(security_group_id=sg.id))
        rows += f"""
        <tr>
            <td class="uuid">{sg.id[:8]}...</td>
            <td>{sg.name}</td>
            <td>{sg.description or '-'}</td>
            <td>{rule_count}</td>
        </tr>
        """

    return f"""
    <table>
        <thead>
            <tr>
                <th>ID</th>
                <th>Name</th>
                <th>Description</th>
                <th>Rules</th>
            </tr>
        </thead>
        <tbody>{rows}</tbody>
    </table>
    """


def render_projects_table(projects: list) -> str:
    """Render the projects table HTML."""
    if not projects:
        return '<div class="empty-state">No projects created yet</div>'

    rows = ""
    for project in projects:
        rows += f"""
        <tr>
            <td class="uuid">{project.id[:8]}...</td>
            <td>{project.name}</td>
            <td>{project.description or '-'}</td>
            <td>{'Yes' if project.enabled else 'No'}</td>
        </tr>
        """

    return f"""
    <table>
        <thead>
            <tr>
                <th>ID</th>
                <th>Name</th>
                <th>Description</th>
                <th>Enabled</th>
            </tr>
        </thead>
        <tbody>{rows}</tbody>
    </table>
    """


def render_users_table(users: list) -> str:
    """Render the users table HTML."""
    if not users:
        return '<div class="empty-state">No users created yet</div>'

    rows = ""
    for user in users:
        rows += f"""
        <tr>
            <td class="uuid">{user.id[:8]}...</td>
            <td>{user.name}</td>
            <td>{user.email or '-'}</td>
            <td>{'Yes' if user.enabled else 'No'}</td>
        </tr>
        """

    return f"""
    <table>
        <thead>
            <tr>
                <th>ID</th>
                <th>Name</th>
                <th>Email</th>
                <th>Enabled</th>
            </tr>
        </thead>
        <tbody>{rows}</tbody>
    </table>
    """


def render_flavors_table(flavors: list) -> str:
    """Render the flavors table HTML."""
    if not flavors:
        return '<div class="empty-state">No flavors available</div>'

    rows = ""
    for flavor in flavors:
        rows += f"""
        <tr>
            <td>{flavor.id}</td>
            <td>{flavor.name}</td>
            <td>{flavor.vcpus}</td>
            <td>{flavor.ram} MB</td>
            <td>{flavor.disk} GB</td>
        </tr>
        """

    return f"""
    <table>
        <thead>
            <tr>
                <th>ID</th>
                <th>Name</th>
                <th>VCPUs</th>
                <th>RAM</th>
                <th>Disk</th>
            </tr>
        </thead>
        <tbody>{rows}</tbody>
    </table>
    """


def render_keypairs_table(keypairs: list) -> str:
    """Render the keypairs table HTML."""
    if not keypairs:
        return '<div class="empty-state">No keypairs created yet</div>'

    rows = ""
    for keypair in keypairs:
        fingerprint = keypair.fingerprint[:20] + "..." if keypair.fingerprint else "-"
        rows += f"""
        <tr>
            <td>{keypair.name}</td>
            <td>{keypair.type}</td>
            <td class="uuid">{fingerprint}</td>
            <td>{keypair.created_at[:19] if keypair.created_at else '-'}</td>
        </tr>
        """

    return f"""
    <table>
        <thead>
            <tr>
                <th>Name</th>
                <th>Type</th>
                <th>Fingerprint</th>
                <th>Created</th>
            </tr>
        </thead>
        <tbody>{rows}</tbody>
    </table>
    """


def render_snapshots_table(snapshots: list) -> str:
    """Render the snapshots table HTML."""
    if not snapshots:
        return '<div class="empty-state">No snapshots created yet</div>'

    rows = ""
    for snapshot in snapshots:
        status = snapshot.status.value if hasattr(snapshot.status, "value") else str(snapshot.status)
        status_class = get_status_class(status)
        rows += f"""
        <tr>
            <td class="uuid">{snapshot.id[:8]}...</td>
            <td>{snapshot.name or '-'}</td>
            <td><span class="status-badge {status_class}">{status}</span></td>
            <td>{snapshot.size} GB</td>
            <td class="uuid">{snapshot.volume_id[:8]}...</td>
        </tr>
        """

    return f"""
    <table>
        <thead>
            <tr>
                <th>ID</th>
                <th>Name</th>
                <th>Status</th>
                <th>Size</th>
                <th>Volume ID</th>
            </tr>
        </thead>
        <tbody>{rows}</tbody>
    </table>
    """


@router.get("/", response_class=HTMLResponse)
async def status_page(request: Request) -> str:
    """Render the main status page."""
    # Determine the host from the request
    host = request.headers.get("host", "localhost:8000").split(":")[0]
    if host == "localhost" or host == "127.0.0.1":
        check_host = "localhost"
    else:
        check_host = host

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
        <header>
            <div class="container">
                <div class="header-actions">
                    <div>
                        <h1>OpenStack Emulator Status</h1>
                        <p>Real-time view of emulator services and resources</p>
                    </div>
                    <button class="refresh-btn" onclick="location.reload()">Refresh</button>
                </div>
            </div>
        </header>

        <div class="container">
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
                        <h3>Servers <span class="count-badge">{len(servers)}</span></h3>
                        {render_servers_table(servers)}
                    </div>
                    <div class="resource-group">
                        <h3>Flavors <span class="count-badge">{len(flavors)}</span></h3>
                        {render_flavors_table(flavors)}
                    </div>
                    <div class="resource-group">
                        <h3>Keypairs <span class="count-badge">{len(keypairs)}</span></h3>
                        {render_keypairs_table(keypairs)}
                    </div>
                </div>

                <!-- Storage Tab -->
                <div id="tab-storage" class="tab-content">
                    <div class="resource-group">
                        <h3>Images <span class="count-badge">{len(images)}</span></h3>
                        {render_images_table(images)}
                    </div>
                    <div class="resource-group">
                        <h3>Volumes <span class="count-badge">{len(volumes)}</span></h3>
                        {render_volumes_table(volumes)}
                    </div>
                    <div class="resource-group">
                        <h3>Snapshots <span class="count-badge">{len(snapshots)}</span></h3>
                        {render_snapshots_table(snapshots)}
                    </div>
                </div>

                <!-- Network Tab -->
                <div id="tab-network" class="tab-content">
                    <div class="resource-group">
                        <h3>Networks <span class="count-badge">{len(networks)}</span></h3>
                        {render_networks_table(networks)}
                    </div>
                    <div class="resource-group">
                        <h3>Subnets <span class="count-badge">{len(subnets)}</span></h3>
                        {render_subnets_table(subnets)}
                    </div>
                    <div class="resource-group">
                        <h3>Ports <span class="count-badge">{len(ports)}</span></h3>
                        {render_ports_table(ports)}
                    </div>
                    <div class="resource-group">
                        <h3>Routers <span class="count-badge">{len(routers)}</span></h3>
                        {render_routers_table(routers)}
                    </div>
                    <div class="resource-group">
                        <h3>Floating IPs <span class="count-badge">{len(floating_ips)}</span></h3>
                        {render_floating_ips_table(floating_ips)}
                    </div>
                    <div class="resource-group">
                        <h3>Security Groups <span class="count-badge">{len(security_groups)}</span></h3>
                        {render_security_groups_table(security_groups)}
                    </div>
                </div>

                <!-- Identity Tab -->
                <div id="tab-identity" class="tab-content">
                    <div class="resource-group">
                        <h3>Projects <span class="count-badge">{len(projects)}</span></h3>
                        {render_projects_table(projects)}
                    </div>
                    <div class="resource-group">
                        <h3>Users <span class="count-badge">{len(users)}</span></h3>
                        {render_users_table(users)}
                    </div>
                </div>
            </div>
        </div>

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
