#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
OPENSTACK_SPECS_PATH="/Users/ilja/workspace/openstack-openapi/specs"

echo "Starting API compliance check..."

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
        
        # Generate coverage report using Python script if available
        if [[ -f "$SCRIPT_DIR/compare_apis.py" ]]; then
            python3 "$SCRIPT_DIR/compare_apis.py" \
                "$reference_spec" \
                "$emulator_spec" \
                "$service" \
                > "$PROJECT_ROOT/reports/$service-coverage.json" 2>/dev/null || echo "  Warning: Coverage analysis failed for $service"
        fi
    else
        echo "  Warning: Missing spec files for $service"
        echo "    Reference: $reference_spec"
        echo "    Emulator:  $emulator_spec"
    fi
done

echo ""
echo "API compliance check completed!"
echo "Reports available in reports/"
echo ""
echo "Next steps:"
echo "1. Review compliance reports: ls -la reports/"
echo "2. Install missing tools:"
echo "   npm install -g openapi-diff"
echo "   pip install openapi-spec-validator swagger-diff deepdiff pyyaml"
echo "3. Generate summary: python3 scripts/generate_compliance_report.py reports/"