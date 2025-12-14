#!/usr/bin/env python3
"""
OpenAPI Specification Comparison Tool

Compares OpenStack reference specifications with emulator implementations
to generate detailed compliance reports.
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Set

import yaml


def load_spec(file_path: str) -> Dict[str, Any]:
    """Load OpenAPI specification from YAML or JSON file."""
    with open(file_path, "r") as f:
        if file_path.endswith((".yaml", ".yml")):
            return yaml.safe_load(f)
        else:
            return json.load(f)


def extract_endpoints(spec: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Extract endpoints with their methods from OpenAPI spec."""
    endpoints = {}
    paths = spec.get("paths", {})

    for path, methods in paths.items():
        for method, details in methods.items():
            if method in ["get", "post", "put", "patch", "delete", "head", "options"]:
                endpoint_key = f"{method.upper()} {path}"
                endpoints[endpoint_key] = {
                    "path": path,
                    "method": method.upper(),
                    "operation_id": details.get("operationId", ""),
                    "summary": details.get("summary", ""),
                    "description": details.get("description", ""),
                    "parameters": details.get("parameters", []),
                    "request_body": details.get("requestBody", {}),
                    "responses": details.get("responses", {}),
                    "tags": details.get("tags", []),
                }

    return endpoints


def analyze_parameters(ref_params: List[Dict], emu_params: List[Dict]) -> Dict[str, Any]:
    """Analyze parameter differences between reference and emulator."""
    ref_param_names = {p.get("name", "") for p in ref_params}
    emu_param_names = {p.get("name", "") for p in emu_params}

    return {
        "missing_parameters": list(ref_param_names - emu_param_names),
        "extra_parameters": list(emu_param_names - ref_param_names),
        "common_parameters": list(ref_param_names & emu_param_names),
        "total_reference_params": len(ref_param_names),
        "implemented_params": len(ref_param_names & emu_param_names),
    }


def analyze_responses(ref_responses: Dict, emu_responses: Dict) -> Dict[str, Any]:
    """Analyze response differences between reference and emulator."""
    ref_status_codes = set(ref_responses.keys())
    emu_status_codes = set(emu_responses.keys())

    return {
        "missing_status_codes": list(ref_status_codes - emu_status_codes),
        "extra_status_codes": list(emu_status_codes - ref_status_codes),
        "common_status_codes": list(ref_status_codes & emu_status_codes),
        "total_reference_codes": len(ref_status_codes),
        "implemented_codes": len(ref_status_codes & emu_status_codes),
    }


def compare_openapi_specs(
    reference_path: str, emulator_path: str, service_name: str
) -> Dict[str, Any]:
    """Compare OpenAPI specs and generate comprehensive compliance report."""

    # Load specifications
    try:
        reference_spec = load_spec(reference_path)
        emulator_spec = load_spec(emulator_path)
    except Exception as e:
        return {"service": service_name, "error": f"Failed to load specifications: {str(e)}"}

    # Extract endpoint information
    ref_endpoints = extract_endpoints(reference_spec)
    emu_endpoints = extract_endpoints(emulator_spec)

    ref_endpoint_keys = set(ref_endpoints.keys())
    emu_endpoint_keys = set(emu_endpoints.keys())

    missing_endpoints = ref_endpoint_keys - emu_endpoint_keys
    extra_endpoints = emu_endpoint_keys - ref_endpoint_keys
    common_endpoints = ref_endpoint_keys & emu_endpoint_keys

    # Detailed analysis for common endpoints
    endpoint_analysis = {}
    for endpoint_key in common_endpoints:
        ref_endpoint = ref_endpoints[endpoint_key]
        emu_endpoint = emu_endpoints[endpoint_key]

        param_analysis = analyze_parameters(
            ref_endpoint.get("parameters", []), emu_endpoint.get("parameters", [])
        )

        response_analysis = analyze_responses(
            ref_endpoint.get("responses", {}), emu_endpoint.get("responses", {})
        )

        endpoint_analysis[endpoint_key] = {
            "parameters": param_analysis,
            "responses": response_analysis,
            "has_request_body": bool(ref_endpoint.get("request_body")),
            "implements_request_body": bool(emu_endpoint.get("request_body")),
            "summary_match": ref_endpoint.get("summary") == emu_endpoint.get("summary"),
            "operation_id_match": ref_endpoint.get("operation_id")
            == emu_endpoint.get("operation_id"),
        }

    # Calculate coverage statistics
    total_endpoints = len(ref_endpoint_keys)
    implemented_endpoints = len(common_endpoints)
    coverage_percentage = (
        (implemented_endpoints / total_endpoints * 100) if total_endpoints > 0 else 0
    )

    # Group missing endpoints by category
    missing_by_path = {}
    for endpoint_key in missing_endpoints:
        endpoint = ref_endpoints[endpoint_key]
        path = endpoint["path"]
        if path not in missing_by_path:
            missing_by_path[path] = []
        missing_by_path[path].append(endpoint["method"])

    # Service information
    service_info = {
        "reference_title": reference_spec.get("info", {}).get("title", ""),
        "reference_version": reference_spec.get("info", {}).get("version", ""),
        "emulator_title": emulator_spec.get("info", {}).get("title", ""),
        "emulator_version": emulator_spec.get("info", {}).get("version", ""),
    }

    # Generate final report
    report = {
        "service": service_name,
        "generated_at": __import__("datetime").datetime.now().isoformat(),
        "service_info": service_info,
        "summary": {
            "total_reference_endpoints": total_endpoints,
            "implemented_endpoints": implemented_endpoints,
            "missing_endpoints_count": len(missing_endpoints),
            "extra_endpoints_count": len(extra_endpoints),
            "coverage_percentage": round(coverage_percentage, 1),
            "compliance_status": (
                "good"
                if coverage_percentage >= 80
                else "partial" if coverage_percentage >= 60 else "limited"
            ),
        },
        "missing_endpoints": {
            "total": len(missing_endpoints),
            "by_path": missing_by_path,
            "list": list(missing_endpoints),
        },
        "extra_endpoints": {"total": len(extra_endpoints), "list": list(extra_endpoints)},
        "endpoint_analysis": endpoint_analysis,
        "recommendations": generate_recommendations(
            missing_endpoints, ref_endpoints, coverage_percentage
        ),
    }

    return report


def generate_recommendations(
    missing_endpoints: Set[str], ref_endpoints: Dict, coverage_percentage: float
) -> List[str]:
    """Generate actionable recommendations based on analysis."""
    recommendations = []

    if coverage_percentage < 50:
        recommendations.append(
            "Low API coverage detected. Focus on implementing core CRUD operations first."
        )

    # Analyze missing endpoints for patterns
    server_endpoints = [ep for ep in missing_endpoints if "/servers" in ep]
    if len(server_endpoints) > 5:
        recommendations.append(
            "Multiple server management endpoints missing. Consider implementing server lifecycle operations."
        )

    volume_endpoints = [ep for ep in missing_endpoints if "volume" in ep.lower()]
    if volume_endpoints:
        recommendations.append(
            "Volume management endpoints missing. These are critical for storage operations."
        )

    metadata_endpoints = [ep for ep in missing_endpoints if "metadata" in ep]
    if metadata_endpoints:
        recommendations.append(
            "Metadata endpoints missing. Consider implementing for better resource management."
        )

    console_endpoints = [ep for ep in missing_endpoints if "console" in ep]
    if console_endpoints:
        recommendations.append(
            "Console access endpoints missing. Lower priority unless debugging features needed."
        )

    if coverage_percentage > 80:
        recommendations.append("Good API coverage! Focus on edge cases and advanced features.")

    return recommendations


def main():
    """Main function for command-line usage."""
    if len(sys.argv) != 4:
        print("Usage: python3 compare_apis.py <reference_spec> <emulator_spec> <service_name>")
        print("Example: python3 compare_apis.py .openstack-specs/openstack_types/data/compute/v2.100.yaml specs/emulator/nova.json nova")
        sys.exit(1)

    reference_path = sys.argv[1]
    emulator_path = sys.argv[2]
    service_name = sys.argv[3]

    # Validate input files
    if not Path(reference_path).exists():
        print(f"Error: Reference specification not found: {reference_path}")
        sys.exit(1)

    if not Path(emulator_path).exists():
        print(f"Error: Emulator specification not found: {emulator_path}")
        sys.exit(1)

    # Generate comparison report
    report = compare_openapi_specs(reference_path, emulator_path, service_name)

    # Output JSON report
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
