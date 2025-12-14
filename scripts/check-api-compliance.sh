#!/bin/bash
set -e

# Handle help option
if [[ "$1" == "-h" || "$1" == "--help" ]]; then
    echo "OpenStack Emulator API Compliance Checker"
    echo "=========================================="
    echo ""
    echo "Usage: $0 [options]"
    echo ""
    echo "This script:"
    echo "1. Downloads/updates official OpenStack API specifications from GitHub"
    echo "2. Exports OpenAPI specs from running emulator services"
    echo "3. Compares emulator APIs with official OpenStack specifications"
    echo "4. Generates detailed compliance reports"
    echo ""
    echo "Prerequisites:"
    echo "- OpenStack emulator must be running (start with 'openstack-emulator')"
    echo "- Git must be available for downloading specifications"
    echo "- Internet connection for initial spec download"
    echo ""
    echo "Options:"
    echo "  -h, --help    Show this help message"
    echo ""
    echo "Output:"
    echo "  specs/emulator/     - Exported emulator OpenAPI specifications"
    echo "  reports/           - Compliance analysis reports"
    echo "  .openstack-specs/  - Downloaded OpenStack reference specifications"
    echo ""
    echo "Examples:"
    echo "  $0                             # Run full compliance check"
    echo "  python3 scripts/generate_compliance_report.py reports/  # Generate summary"
    echo ""
    echo "For more information, see docs/api-compliance.md"
    exit 0
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
OPENSTACK_SPECS_REPO="https://github.com/gtema/openstack"
OPENSTACK_SPECS_PATH="$PROJECT_ROOT/.openstack-specs"

echo "OpenStack Emulator API Compliance Check"
echo "======================================="
echo ""

# Clone or update OpenStack specs repository
if [[ -d "$OPENSTACK_SPECS_PATH" ]]; then
    echo "Updating OpenStack API specifications..."
    cd "$OPENSTACK_SPECS_PATH"
    git pull --quiet origin main 2>/dev/null || echo "Warning: Could not update specs repository"
    cd "$PROJECT_ROOT"
else
    echo "Cloning OpenStack API specifications..."
    git clone --quiet --depth 1 "$OPENSTACK_SPECS_REPO" "$OPENSTACK_SPECS_PATH" 2>/dev/null || {
        echo "Warning: Could not clone specs repository. Using fallback paths."
        mkdir -p "$OPENSTACK_SPECS_PATH"
    }
fi

# Update specs path to point to the data subdirectory
OPENSTACK_SPECS_PATH="$OPENSTACK_SPECS_PATH/openstack_types/data"

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

# Run comparisons
echo "Running API comparisons..."

# Define service mappings using a more portable approach
services="keystone nova cinder glance neutron octavia"
for service in $services; do
    case $service in
        keystone) reference_file="identity/v3.14.yaml" ;;
        nova) reference_file="compute/v2.100.yaml" ;;
        cinder) reference_file="block-storage/v3.71.yaml" ;;
        glance) reference_file="image/v2.16.yaml" ;;
        neutron) reference_file="network/v2.27.yaml" ;;
        octavia) reference_file="load-balancer/v2.27.yaml" ;;
        *) continue ;;
    esac
    
    reference_spec="$OPENSTACK_SPECS_PATH/$reference_file"
    emulator_spec="$PROJECT_ROOT/specs/emulator/$service.json"
    
    if [[ -f "$emulator_spec" ]]; then
        if [[ -f "$reference_spec" ]]; then
            echo "Comparing $service..."
            
            # Use openapi-diff if available
            if command -v openapi-diff &> /dev/null; then
                openapi-diff \
                    "$reference_spec" \
                    "$emulator_spec" \
                    --format markdown \
                    > "$PROJECT_ROOT/reports/$service-compliance.md" 2>/dev/null || echo "  Warning: Comparison failed for $service"
            else
                echo "  Info: openapi-diff not available. Install with: npm install -g openapi-diff"
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
            echo "  Warning: Reference spec not found for $service: $reference_spec"
            echo "  Info: This may be due to missing OpenStack specs repository"
            
            # Still generate basic endpoint count for emulator
            if [[ -f "$SCRIPT_DIR/compare_apis.py" ]]; then
                echo "  Generating basic endpoint analysis..."
                python3 -c "
import json
import sys
try:
    with open('$emulator_spec', 'r') as f:
        spec = json.load(f)
    paths = spec.get('paths', {})
    total_endpoints = sum(len([m for m in methods.keys() if m in ['get', 'post', 'put', 'patch', 'delete']]) 
                         for methods in paths.values() if isinstance(methods, dict))
    print(f'  {len(paths)} paths, {total_endpoints} endpoints implemented')
    
    # Create basic report
    basic_report = {
        'service': '$service',
        'summary': {
            'total_paths': len(paths),
            'implemented_endpoints': total_endpoints,
            'note': 'Reference spec not available for comparison'
        }
    }
    with open('$PROJECT_ROOT/reports/$service-coverage.json', 'w') as f:
        json.dump(basic_report, f, indent=2)
except Exception as e:
    print(f'  Error analyzing emulator spec: {e}')
" 2>/dev/null || echo "  Could not analyze emulator spec"
            fi
        fi
    else
        echo "  Error: Emulator spec not found: $emulator_spec"
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