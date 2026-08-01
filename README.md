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
| Placement | 8778 | Resource Provider service |
| Swift | 8080 | Object Storage service |
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

### Run on Kubernetes (via Helm)

A published Helm chart deploys the emulator as a single-replica `Deployment` + `ClusterIP` Service that exposes all nine ports. Consumers in the same cluster reach Keystone at `http://<release>-openstack-emulator.<ns>.svc.cluster.local:5000/v3` with the admin/`s4l4dus`/`Default` credentials.

```bash
helm repo add openstack-emulator https://waldur.github.io/openstack-emulator/
helm install ose openstack-emulator/openstack-emulator \
  --namespace ose --create-namespace --version 0.0.1
helm test ose -n ose      # curls /health on the five main service ports
```

See [`docs/kubernetes.md`](docs/kubernetes.md) for the full operator guide (presets, persistence, Ingress, Gateway API, troubleshooting). The chart source lives at [`charts/openstack-emulator/`](charts/openstack-emulator) — also installable from disk via `helm install ose ./charts/openstack-emulator`.

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
- [Kubernetes Deployment Guide](docs/kubernetes.md) - Helm chart install + cross-namespace use + Ingress/Gateway API
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
│   ├── core/          # Business logic and models
│   └── presets/       # Built-in preset YAMLs (development, production, …)
├── charts/
│   └── openstack-emulator/  # Helm chart published to GitHub Pages
├── scripts/
│   ├── release.py     # Tag-driven release helper (status / check / release X.Y.Z)
│   └── check-api-compliance.sh  # OpenStack API compliance comparison
├── tests/             # Python test suite
├── docs/              # User-facing documentation
├── .gitlab-ci.yml     # CI: linters, tests, helm lint, chart publish, docker publish
├── CLAUDE.md          # Development guide for AI assistants
└── README.md
```

## Running Tests

```bash
uv run pytest
uv run pytest --cov=emulator --cov-report=html
```

## Releasing

Releases are tag-driven. Pushing a `X.Y.Z` tag triggers GitLab CI to:

- Run the full Python test matrix (3.10–3.13), linters, type checks, and `helm lint` + `helm unittest`
- Package the chart and push `charts/openstack-emulator-X.Y.Z.tgz` + an updated `index.yaml` to the `gh-pages` branch of the GitHub mirror at [github.com/waldur/openstack-emulator](https://github.com/waldur/openstack-emulator)
- GitHub Pages serves the branch at <https://waldur.github.io/openstack-emulator/>, where `helm repo add` consumers pick up the new version

The [`scripts/release.py`](scripts/release.py) helper bundles the version bump + checks + tag + push:

```bash
uv run scripts/release.py status                   # show current versions + recent tags
uv run scripts/release.py check                    # run the same gates CI runs (fast subset)
uv run scripts/release.py version-update 0.2.0     # bump pyproject.toml + Chart.yaml only
uv run scripts/release.py release 0.2.0            # bump → check → commit → tag → (confirm) push
```

The release script keeps `pyproject.toml`'s `[project].version` and `charts/openstack-emulator/Chart.yaml`'s `version:` in lockstep. `appVersion:` is intentionally left at `"latest"` until the Docker image starts being tag-versioned.

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
