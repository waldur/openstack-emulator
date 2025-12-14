#!/bin/bash
set -e

echo "Testing API Compliance Workflow..."
echo "=================================="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Test 1: Check script permissions
echo "✓ Testing script permissions..."
if [[ -x "$SCRIPT_DIR/check-api-compliance.sh" ]]; then
    echo "  - check-api-compliance.sh is executable"
else
    echo "  ✗ check-api-compliance.sh is not executable"
    exit 1
fi

if [[ -x "$SCRIPT_DIR/compare_apis.py" ]]; then
    echo "  - compare_apis.py is executable"
else
    echo "  ✗ compare_apis.py is not executable"
    exit 1
fi

# Test 2: Check Python script functionality
echo "✓ Testing Python comparison tool..."
python3 "$SCRIPT_DIR/compare_apis.py" 2>/dev/null || {
    output=$(python3 "$SCRIPT_DIR/compare_apis.py" 2>&1 | head -1)
    if [[ "$output" == *"Usage:"* ]]; then
        echo "  - compare_apis.py shows correct usage message"
    else
        echo "  ✗ compare_apis.py unexpected output: $output"
        exit 1
    fi
}

# Test 3: Check report generator
echo "✓ Testing compliance report generator..."
mkdir -p "$PROJECT_ROOT/reports"
output=$(python3 "$SCRIPT_DIR/generate_compliance_report.py" "$PROJECT_ROOT/reports/" 2>&1)
if [[ "$output" == *"No compliance reports found"* ]]; then
    echo "  - generate_compliance_report.py handles empty directory correctly"
else
    echo "  ✗ Unexpected output from report generator"
    exit 1
fi

# Test 4: Check OpenStack specs cloning
echo "✓ Testing OpenStack specification cloning..."
SPECS_REPO="https://github.com/gtema/openstack"
SPECS_PATH="$PROJECT_ROOT/.openstack-specs-test"

# Test cloning (use a test directory)
if git clone --quiet --depth 1 "$SPECS_REPO" "$SPECS_PATH" 2>/dev/null; then
    echo "  - Successfully cloned OpenStack specs repository"
    
    # Check for key spec files
    ACTUAL_SPECS_PATH="$SPECS_PATH/openstack_types/data"
    services=("compute/v2.100.yaml" "identity/v3.14.yaml" "network/v2.27.yaml")
    for spec in "${services[@]}"; do
        if [[ -f "$ACTUAL_SPECS_PATH/$spec" ]]; then
            echo "  - Found: $spec"
        else
            echo "  ⚠ Missing: $spec"
        fi
    done
    
    # Cleanup test directory
    rm -rf "$SPECS_PATH"
else
    echo "  ⚠ Could not clone OpenStack specs repository"
    echo "    Network connection may be required for compliance checks"
fi

# Test 5: Check required dependencies
echo "✓ Checking dependencies..."

# Check for optional tools
if command -v openapi-diff &> /dev/null; then
    echo "  - openapi-diff: ✓ installed"
else
    echo "  - openapi-diff: ⚠ not installed (optional: npm install -g openapi-diff)"
fi

# Check Python modules
python3 -c "import yaml, json" 2>/dev/null && echo "  - Python YAML support: ✓" || echo "  - Python YAML: ⚠ not available (pip install pyyaml)"

# Test 6: Create sample test files for workflow validation  
echo "✓ Creating test files for workflow validation..."
cat > "$PROJECT_ROOT/specs/emulator/test.json" << 'EOF'
{
    "openapi": "3.1.0",
    "info": {
        "title": "Test Service Emulator",
        "version": "0.1.0"
    },
    "paths": {
        "/test": {
            "get": {
                "operationId": "test:get",
                "responses": {
                    "200": {"description": "OK"}
                }
            }
        }
    }
}
EOF

cat > "$PROJECT_ROOT/specs/reference-test.yaml" << 'EOF'
openapi: 3.1.0
info:
  title: Test Service Reference
  version: 1.0.0
paths:
  /test:
    get:
      operationId: test:get
      responses:
        200:
          description: OK
        404:
          description: Not Found
  /extra:
    post:
      operationId: extra:post
      responses:
        201:
          description: Created
EOF

# Run a test comparison
echo "✓ Testing comparison functionality..."
if python3 "$SCRIPT_DIR/compare_apis.py" \
    "$PROJECT_ROOT/specs/reference-test.yaml" \
    "$PROJECT_ROOT/specs/emulator/test.json" \
    "test" > "$PROJECT_ROOT/reports/test-coverage.json" 2>&1; then
    
    # Check if the output is valid JSON
    if python3 -m json.tool "$PROJECT_ROOT/reports/test-coverage.json" > /dev/null 2>&1; then
        echo "  - Comparison generated valid JSON report"
        coverage=$(python3 -c "import json; print(json.load(open('$PROJECT_ROOT/reports/test-coverage.json'))['summary']['coverage_percentage'])")
        echo "  - Test coverage calculated: ${coverage}%"
    else
        echo "  ✗ Comparison output is not valid JSON"
        exit 1
    fi
else
    echo "  ✗ Comparison failed"
    exit 1
fi

# Test report generation with the test data
echo "✓ Testing report generation with test data..."
if python3 "$SCRIPT_DIR/generate_compliance_report.py" "$PROJECT_ROOT/reports/" > "$PROJECT_ROOT/reports/test-summary.md" 2>&1; then
    if [[ -s "$PROJECT_ROOT/reports/test-summary.md" ]]; then
        echo "  - Summary report generated successfully"
        lines=$(wc -l < "$PROJECT_ROOT/reports/test-summary.md")
        echo "  - Report contains $lines lines"
    else
        echo "  ✗ Summary report is empty"
        exit 1
    fi
else
    echo "  ✗ Report generation failed"
    exit 1
fi

# Cleanup test files
echo "✓ Cleaning up test files..."
rm -f "$PROJECT_ROOT/specs/emulator/test.json"
rm -f "$PROJECT_ROOT/specs/reference-test.yaml"
rm -f "$PROJECT_ROOT/reports/test-coverage.json"
rm -f "$PROJECT_ROOT/reports/test-summary.md"

echo ""
echo "🎉 API Compliance Workflow Test PASSED!"
echo ""
echo "Next steps:"
echo "1. Start the emulator: openstack-emulator"
echo "2. Run compliance check: scripts/check-api-compliance.sh"
echo "3. Generate report: python3 scripts/generate_compliance_report.py reports/"
echo ""
echo "Optional optimizations:"
echo "- Install openapi-diff: npm install -g openapi-diff"
echo "- Install Python deps: pip install pyyaml deepdiff openapi-spec-validator"