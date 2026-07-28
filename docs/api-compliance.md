# API Compliance Testing

This document describes the automated OpenAPI specification comparison process used to ensure the OpenStack Emulator APIs comply with official OpenStack API specifications.

## Overview

The OpenStack Emulator uses FastAPI which automatically generates OpenAPI 3.1 specifications from the code. We compare these generated specs with the official OpenStack OpenAPI specifications to identify gaps and ensure compliance.

## Process

### 1. Export Emulator OpenAPI Specs

The emulator automatically exposes OpenAPI specifications at `/openapi.json` for each service:

```bash
# Start the emulator (all services)
openstack-emulator

# Export specs from running services
curl http://localhost:5000/openapi.json > specs/emulator/keystone.json
curl http://localhost:8774/openapi.json > specs/emulator/nova.json  
curl http://localhost:8776/openapi.json > specs/emulator/cinder.json
curl http://localhost:9292/openapi.json > specs/emulator/glance.json
curl http://localhost:9696/openapi.json > specs/emulator/neutron.json
curl http://localhost:9876/openapi.json > specs/emulator/octavia.json
```

### 2. OpenStack Reference Specs

Official OpenStack OpenAPI specifications are automatically downloaded from:
- **Repository**: https://github.com/gtema/openstack
- **Local Cache**: `.openstack-specs/openstack_types/data/` (auto-managed)
- **Nova (Compute)**: `compute/v2.100.yaml`
- **Cinder (Block Storage)**: `block-storage/v3.71.yaml` 
- **Keystone (Identity)**: `identity/v3.14.yaml`
- **Neutron (Network)**: `network/v2.27.yaml`
- **Glance (Image)**: `image/v2.16.yaml`
- **Octavia (Load Balancing)**: `load-balancer/v2.27.yaml`

The compliance script automatically clones/updates this repository, so no manual setup is required.

### 3. Comparison Tools

#### Option A: openapi-diff (Node.js)

```bash
npm install -g openapi-diff

# Compare Nova implementation
openapi-diff \
  .openstack-specs/openstack_types/data/compute/v2.100.yaml \
  specs/emulator/nova.json \
  --format markdown \
  > reports/nova-compliance.md
```

#### Option B: Python Tools

```bash
pip install openapi-spec-validator swagger-diff

# Validate specs first
openapi-spec-validator specs/emulator/nova.json

# Generate comparison
swagger-diff \
  --url1 .openstack-specs/openstack_types/data/compute/v2.100.yaml \
  --url2 specs/emulator/nova.json \
  --output-format json \
  > reports/nova-diff.json
```

#### Option C: Custom Python Script

```python
# scripts/compare_apis.py
import json
import yaml
from openapi_spec_validator import validate_spec
from deepdiff import DeepDiff


def compare_openapi_specs(reference_path, emulator_path, service_name):
    """Compare OpenAPI specs and generate compliance report."""

    # Load specs
    with open(reference_path, "r") as f:
        if reference_path.endswith(".yaml"):
            reference_spec = yaml.safe_load(f)
        else:
            reference_spec = json.load(f)

    with open(emulator_path, "r") as f:
        emulator_spec = json.load(f)

    # Validate specs
    validate_spec(reference_spec)
    validate_spec(emulator_spec)

    # Compare endpoints
    ref_paths = set(reference_spec.get("paths", {}).keys())
    emu_paths = set(emulator_spec.get("paths", {}).keys())

    missing_paths = ref_paths - emu_paths
    extra_paths = emu_paths - ref_paths
    common_paths = ref_paths & emu_paths

    # Compare schemas for common paths
    schema_diffs = {}
    for path in common_paths:
        ref_path = reference_spec["paths"][path]
        emu_path = emulator_spec["paths"][path]
        diff = DeepDiff(ref_path, emu_path, ignore_order=True)
        if diff:
            schema_diffs[path] = diff

    # Generate report
    report = {
        "service": service_name,
        "coverage": {
            "total_reference_endpoints": len(ref_paths),
            "implemented_endpoints": len(common_paths),
            "coverage_percentage": (len(common_paths) / len(ref_paths)) * 100,
        },
        "missing_endpoints": list(missing_paths),
        "extra_endpoints": list(extra_paths),
        "schema_differences": schema_diffs,
    }

    return report
```

### 4. Automated Comparison Script

Create `scripts/check-api-compliance.sh`:

```bash
#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
OPENSTACK_SPECS_REPO="https://github.com/gtema/openstack"
OPENSTACK_SPECS_PATH="$PROJECT_ROOT/.openstack-specs/openstack_types/data"

echo "Starting API compliance check..."

# Clone or update OpenStack specs repository
if [[ -d "$PROJECT_ROOT/.openstack-specs" ]]; then
    echo "Updating OpenStack API specifications..."
    cd "$PROJECT_ROOT/.openstack-specs"
    git pull --quiet origin main 2>/dev/null || echo "Warning: Could not update specs"
    cd "$PROJECT_ROOT"
else
    echo "Cloning OpenStack API specifications..."
    git clone --quiet --depth 1 "$OPENSTACK_SPECS_REPO" "$PROJECT_ROOT/.openstack-specs" 2>/dev/null || {
        echo "Warning: Could not clone specs repository"
        exit 1
    }
fi

# Ensure emulator is running
if ! curl -s http://localhost:5000/health > /dev/null; then
    echo "Error: Emulator not running. Start with 'openstack-emulator'"
    exit 1
fi

# Create output directories
mkdir -p "$PROJECT_ROOT/specs/emulator"
mkdir -p "$PROJECT_ROOT/reports"

# Export emulator specs
echo "Exporting emulator OpenAPI specifications..."
curl -s http://localhost:5000/openapi.json > "$PROJECT_ROOT/specs/emulator/keystone.json"
curl -s http://localhost:8774/openapi.json > "$PROJECT_ROOT/specs/emulator/nova.json"
curl -s http://localhost:8776/openapi.json > "$PROJECT_ROOT/specs/emulator/cinder.json"
curl -s http://localhost:9292/openapi.json > "$PROJECT_ROOT/specs/emulator/glance.json"
curl -s http://localhost:9696/openapi.json > "$PROJECT_ROOT/specs/emulator/neutron.json"
curl -s http://localhost:9876/openapi.json > "$PROJECT_ROOT/specs/emulator/octavia.json"

# Define service mappings
declare -A SERVICES=(
    ["keystone"]="identity/v3.14.yaml"
    ["nova"]="compute/v2.96.yaml"
    ["cinder"]="block-storage/v3.70.yaml"
    ["glance"]="image/v2.16.yaml"
    ["neutron"]="network/v2.yaml"
    ["octavia"]="load-balancing/v2.yaml"
)

# Run comparisons
echo "Running API comparisons..."
for service in "${!SERVICES[@]}"; do
    reference_spec="$OPENSTACK_SPECS_PATH/${SERVICES[$service]}"
    emulator_spec="$PROJECT_ROOT/specs/emulator/$service.json"
    
    if [[ -f "$reference_spec" ]] && [[ -f "$emulator_spec" ]]; then
        echo "Comparing $service..."
        
        # Use openapi-diff if available
        if command -v openapi-diff &> /dev/null; then
            openapi-diff \
                "$reference_spec" \
                "$emulator_spec" \
                --format markdown \
                > "$PROJECT_ROOT/reports/$service-compliance.md" 2>/dev/null || echo "  Warning: Comparison failed for $service"
        else
            echo "  Warning: openapi-diff not found. Install with: npm install -g openapi-diff"
        fi
        
        # Generate coverage report
        python3 "$SCRIPT_DIR/compare_apis.py" \
            "$reference_spec" \
            "$emulator_spec" \
            "$service" \
            > "$PROJECT_ROOT/reports/$service-coverage.json" 2>/dev/null || echo "  Warning: Coverage analysis failed for $service"
    else
        echo "  Warning: Missing spec files for $service"
    fi
done

echo "API compliance check completed. Reports available in reports/"
```

## Report Generation

### Coverage Summary Report

Generate an overall compliance dashboard:

```bash
# Generate summary report
python3 scripts/generate_compliance_report.py reports/ > reports/compliance-summary.md
```

Example summary:

```markdown
# API Compliance Summary

| Service | Endpoints Implemented | Total Reference | Coverage | Status |
|---------|----------------------|-----------------|----------|---------|
| Nova    | 22/38               | 38              | 58%      | 🟡 Partial |
| Cinder  | 45/52               | 52              | 87%      | 🟢 Good |
| Keystone| 35/42               | 42              | 83%      | 🟢 Good |
| Neutron | 28/45               | 45              | 62%      | 🟡 Partial |
| Glance  | 18/25               | 25              | 72%      | 🟡 Partial |
| Octavia | 15/35               | 35              | 43%      | 🔴 Limited |

## Priority Gaps

### High Priority (Common Operations)
- Nova: Volume attachment endpoints
- Neutron: Router interface management
- Glance: Image sharing/membership

### Medium Priority (Advanced Features)
- Nova: Server diagnostics, console access
- Octavia: L7 policies and rules
- Neutron: QoS policies

### Low Priority (Admin/Advanced)
- Nova: Hypervisor management
- Neutron: Agent management
- Keystone: Federation support
```

## Integration with Development Workflow

### Pre-commit Hook

Add to `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: local
    hooks:
      - id: api-compliance-check
        name: API Compliance Check
        entry: scripts/check-api-compliance.sh
        language: script
        files: ^emulator/api/.*\.py$
        stages: [manual]
```

### CI/CD Integration

```yaml
# .github/workflows/api-compliance.yml
name: API Compliance Check
on:
  pull_request:
    paths:
      - 'emulator/api/**'

jobs:
  compliance:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          npm install -g openapi-diff
          pip install -r requirements.txt
      
      - name: Start emulator
        run: |
          openstack-emulator &
          sleep 10  # Wait for startup
      
      - name: Run compliance check
        run: scripts/check-api-compliance.sh
      
      - name: Upload reports
        uses: actions/upload-artifact@v3
        with:
          name: compliance-reports
          path: reports/
```

## Tools and Dependencies

### Required Tools

```bash
# Node.js tools
npm install -g openapi-diff

# Python tools  
pip install openapi-spec-validator swagger-diff deepdiff pyyaml

# Optional: Spectral for advanced linting
npm install -g @stoplight/spectral-cli
```

### Directory Structure

```
openstack-emulator/
├── scripts/
│   ├── check-api-compliance.sh
│   ├── compare_apis.py
│   └── generate_compliance_report.py
├── specs/
│   └── emulator/          # Generated emulator specs
│       ├── keystone.json
│       ├── nova.json
│       └── ...
├── reports/               # Compliance reports
│   ├── nova-compliance.md
│   ├── cinder-coverage.json
│   └── compliance-summary.md
└── docs/
    └── api-compliance.md  # This document
```

## Usage Examples

### Daily Development Workflow

```bash
# 1. Start development server
openstack-emulator

# 2. Make API changes
# ... edit emulator/api/nova.py ...

# 3. Check compliance impact
scripts/check-api-compliance.sh

# 4. Review generated reports
cat reports/nova-compliance.md
```

### Release Preparation

```bash
# Generate comprehensive compliance report for release notes
scripts/check-api-compliance.sh
python3 scripts/generate_compliance_report.py reports/ > COMPLIANCE.md
```

## Benefits

1. **Objective Measurement**: Data-driven API compliance tracking
2. **Automated Detection**: Catch API regressions automatically  
3. **Prioritized Development**: Focus on high-impact missing endpoints
4. **Documentation**: Auto-generated compliance status for users
5. **Quality Assurance**: Ensure OpenStack compatibility before releases

## Related Documentation

- [Development Guide](./development.md) - Adding new API endpoints
- [Architecture Overview](./architecture/README.md) - System design
- [API Examples](./api-examples.md) - Usage examples