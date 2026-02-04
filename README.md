# OpenStack Emulator

A lightweight OpenStack API emulator for testing purposes. This emulator provides simplified implementations of OpenStack services, allowing you to develop and test OpenStack clients without a full OpenStack deployment.

## Supported Services

| Service | Port | Description |
|---------|------|-------------|
| Keystone | 5000 | Identity service |
| Nova | 8774 | Compute service |
| Cinder | 8776 | Block Storage service |
| Glance | 9292 | Image service |
| Neutron | 9696 | Networking service |
| Octavia | 9876 | Load Balancer service |
| Status UI | 10000 | Web dashboard |
| Scenarios | 8999 | Failure injection API |

## Quick Start

### Installation

```bash
pip install -e .

# Or with uv
uv pip install -e .

# Development installation
pip install -e ".[dev]"
```

### Running

```bash
# Run all services
openstack-emulator

# Run a specific service
openstack-emulator --service=nova

# Run with persistence enabled
openstack-emulator --persist-db=emulator_data.json --auto-save
```

### Using with OpenStack CLI

```bash
export OS_AUTH_URL=http://localhost:5000/v3
export OS_PROJECT_NAME=admin
export OS_USERNAME=admin
export OS_PASSWORD=s4l4dus
export OS_USER_DOMAIN_NAME=Default
export OS_PROJECT_DOMAIN_NAME=Default
export OS_IDENTITY_API_VERSION=3

openstack server list
openstack network list
openstack volume list
```

### API Documentation

Once running, access Swagger UI at:
- Keystone: http://localhost:5000/docs
- Nova: http://localhost:8774/docs
- Cinder: http://localhost:8776/docs
- Glance: http://localhost:9292/docs
- Neutron: http://localhost:9696/docs
- Status UI: http://localhost:10000/

## Documentation

- [Usage Guide](docs/usage.md) - Detailed usage instructions
- [API Examples](docs/api-examples.md) - curl and SDK examples
- [Scenario Injection](docs/scenarios.md) - Failure testing guide
- [Architecture](docs/architecture/) - System design documentation
  - [Overview](docs/architecture/README.md) - Architecture overview
  - [Data Models](docs/architecture/data-models.md) - Model definitions
  - [Tenant Isolation](docs/architecture/tenant-isolation.md) - Multi-tenancy

## Project Structure

```
openstack-emulator/
├── emulator/
│   ├── api/           # REST API routes
│   └── core/          # Business logic and models
├── tests/             # Test suite
├── docs/              # Documentation
├── CLAUDE.md          # Development guide
└── README.md
```

## Running Tests

```bash
pytest
pytest --cov=emulator --cov-report=html
```

## Limitations

This is a testing emulator with several limitations:

- **No real virtualization**: Servers are simulated, not actual VMs
- **In-memory storage**: Data is lost on restart (unless persistence is enabled)
- **Limited API coverage**: Only essential endpoints implemented
- **Simulated resources**: Networks, volumes don't route real traffic

See [Architecture Overview](docs/architecture/README.md) for more details.

## Contributing

Contributions welcome! Please see the [Development Guide](docs/development.md) for guidelines.

## License

MIT License
