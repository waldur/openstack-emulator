#!/usr/bin/env python3
"""
API Compliance Summary Report Generator

Processes individual service compliance reports to generate a comprehensive
summary dashboard showing overall OpenStack API compliance status.
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Any


def load_compliance_reports(reports_dir: str) -> Dict[str, Dict]:
    """Load all compliance JSON reports from the reports directory."""
    reports = {}
    reports_path = Path(reports_dir)
    
    if not reports_path.exists():
        print(f"Error: Reports directory not found: {reports_dir}")
        return reports
    
    for report_file in reports_path.glob("*-coverage.json"):
        service_name = report_file.stem.replace('-coverage', '')
        try:
            with open(report_file, 'r') as f:
                reports[service_name] = json.load(f)
        except Exception as e:
            print(f"Warning: Failed to load {report_file}: {e}")
    
    return reports


def get_status_emoji(coverage: float) -> str:
    """Get status emoji based on coverage percentage."""
    if coverage >= 80:
        return "🟢"
    elif coverage >= 60:
        return "🟡"
    else:
        return "🔴"


def get_status_text(coverage: float) -> str:
    """Get status text based on coverage percentage."""
    if coverage >= 80:
        return "Good"
    elif coverage >= 60:
        return "Partial"
    else:
        return "Limited"


def generate_summary_table(reports: Dict[str, Dict]) -> str:
    """Generate the main compliance summary table."""
    if not reports:
        return "No compliance reports found."
    
    table_rows = []
    total_endpoints = 0
    total_implemented = 0
    
    # Sort services by coverage percentage (descending)
    sorted_services = sorted(
        reports.items(),
        key=lambda x: x[1].get('summary', {}).get('coverage_percentage', 0),
        reverse=True
    )
    
    for service_name, report in sorted_services:
        if 'error' in report:
            continue
            
        summary = report.get('summary', {})
        coverage = summary.get('coverage_percentage', 0)
        implemented = summary.get('implemented_endpoints', 0)
        total_ref = summary.get('total_reference_endpoints', 0)
        
        total_endpoints += total_ref
        total_implemented += implemented
        
        status_emoji = get_status_emoji(coverage)
        status_text = get_status_text(coverage)
        
        table_rows.append(
            f"| {service_name.title()} | {implemented}/{total_ref} | {total_ref} | {coverage:.1f}% | {status_emoji} {status_text} |"
        )
    
    # Calculate overall coverage
    overall_coverage = (total_implemented / total_endpoints * 100) if total_endpoints > 0 else 0
    overall_status = get_status_emoji(overall_coverage)
    
    table_header = """| Service | Endpoints Implemented | Total Reference | Coverage | Status |
|---------|----------------------|-----------------|----------|---------|"""
    
    table = "\n".join([table_header] + table_rows)
    
    # Add overall summary
    table += f"\n| **OVERALL** | **{total_implemented}/{total_endpoints}** | **{total_endpoints}** | **{overall_coverage:.1f}%** | **{overall_status} {get_status_text(overall_coverage)}** |"
    
    return table


def analyze_priority_gaps(reports: Dict[str, Dict]) -> Dict[str, List[str]]:
    """Analyze missing endpoints and categorize by priority."""
    high_priority = []
    medium_priority = []
    low_priority = []
    
    # Keywords for categorizing endpoints
    high_priority_keywords = [
        'volume', 'attachment', 'server', 'instance', 'network', 'port', 'router',
        'security-group', 'keypair', 'flavor', 'image'
    ]
    
    medium_priority_keywords = [
        'metadata', 'console', 'interface', 'diagnostics', 'migration',
        'action', 'quota', 'limit'
    ]
    
    for service_name, report in reports.items():
        if 'error' in report:
            continue
            
        missing_endpoints = report.get('missing_endpoints', {}).get('list', [])
        
        for endpoint in missing_endpoints:
            endpoint_lower = endpoint.lower()
            
            # Check for high priority keywords
            if any(keyword in endpoint_lower for keyword in high_priority_keywords):
                high_priority.append(f"{service_name.title()}: {endpoint}")
            # Check for medium priority keywords
            elif any(keyword in endpoint_lower for keyword in medium_priority_keywords):
                medium_priority.append(f"{service_name.title()}: {endpoint}")
            # Everything else is low priority
            else:
                low_priority.append(f"{service_name.title()}: {endpoint}")
    
    return {
        'high': high_priority[:10],  # Limit to top 10 for readability
        'medium': medium_priority[:10],
        'low': low_priority[:5]
    }


def generate_recommendations(reports: Dict[str, Dict]) -> List[str]:
    """Generate actionable recommendations based on compliance analysis."""
    recommendations = []
    
    # Calculate average coverage
    coverages = [
        report.get('summary', {}).get('coverage_percentage', 0)
        for report in reports.values()
        if 'error' not in report
    ]
    
    if not coverages:
        return ["No valid compliance data available for analysis."]
    
    avg_coverage = sum(coverages) / len(coverages)
    
    if avg_coverage < 50:
        recommendations.append("🔴 **Critical**: Overall API coverage is low. Focus on implementing core CRUD operations across all services.")
    elif avg_coverage < 70:
        recommendations.append("🟡 **Important**: API coverage is moderate. Prioritize missing high-traffic endpoints.")
    else:
        recommendations.append("🟢 **Good**: API coverage is solid. Focus on advanced features and edge cases.")
    
    # Service-specific recommendations
    for service_name, report in reports.items():
        if 'error' in report:
            continue
            
        coverage = report.get('summary', {}).get('coverage_percentage', 0)
        missing_count = report.get('summary', {}).get('missing_endpoints_count', 0)
        
        if coverage < 50 and missing_count > 10:
            recommendations.append(f"📋 **{service_name.title()}**: Low coverage ({coverage:.1f}%) with {missing_count} missing endpoints. Needs significant work.")
        elif coverage >= 80:
            recommendations.append(f"✅ **{service_name.title()}**: Excellent coverage ({coverage:.1f}%). Consider advanced features.")
    
    # Add development workflow recommendations
    if avg_coverage > 60:
        recommendations.append("🔧 **Workflow**: Set up automated compliance testing in CI/CD to maintain quality.")
        recommendations.append("📊 **Monitoring**: Track compliance metrics over time to measure progress.")
    
    return recommendations


def generate_compliance_report(reports_dir: str) -> str:
    """Generate the complete compliance summary report."""
    reports = load_compliance_reports(reports_dir)
    
    if not reports:
        return "# API Compliance Summary\n\nNo compliance reports found. Run `scripts/check-api-compliance.sh` first."
    
    # Count services with errors
    error_services = [name for name, report in reports.items() if 'error' in report]
    
    report_sections = [
        "# OpenStack Emulator API Compliance Summary",
        "",
        f"Generated: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## Overview",
        "",
        generate_summary_table(reports),
        "",
    ]
    
    # Add error section if needed
    if error_services:
        report_sections.extend([
            "## ⚠️ Analysis Errors",
            "",
            "The following services had errors during analysis:",
            "",
        ])
        for service in error_services:
            error_msg = reports[service].get('error', 'Unknown error')
            report_sections.append(f"- **{service.title()}**: {error_msg}")
        report_sections.append("")
    
    # Priority gaps analysis
    priority_gaps = analyze_priority_gaps(reports)
    
    if any(priority_gaps.values()):
        report_sections.extend([
            "## 🎯 Priority Gaps",
            "",
        ])
        
        if priority_gaps['high']:
            report_sections.extend([
                "### 🔴 High Priority (Core Operations)",
                "",
            ])
            for gap in priority_gaps['high']:
                report_sections.append(f"- {gap}")
            report_sections.append("")
        
        if priority_gaps['medium']:
            report_sections.extend([
                "### 🟡 Medium Priority (Advanced Features)",
                "",
            ])
            for gap in priority_gaps['medium']:
                report_sections.append(f"- {gap}")
            report_sections.append("")
        
        if priority_gaps['low']:
            report_sections.extend([
                "### 🟢 Low Priority (Admin/Specialized)",
                "",
            ])
            for gap in priority_gaps['low']:
                report_sections.append(f"- {gap}")
            report_sections.append("")
    
    # Recommendations
    recommendations = generate_recommendations(reports)
    if recommendations:
        report_sections.extend([
            "## 📋 Recommendations",
            "",
        ])
        for rec in recommendations:
            report_sections.append(f"- {rec}")
        report_sections.append("")
    
    # Additional sections
    report_sections.extend([
        "## 📊 Detailed Reports",
        "",
        "For detailed endpoint-by-endpoint analysis, see individual service reports:",
        "",
    ])
    
    for service_name in sorted(reports.keys()):
        if 'error' not in reports[service_name]:
            coverage = reports[service_name].get('summary', {}).get('coverage_percentage', 0)
            status = get_status_emoji(coverage)
            report_sections.append(f"- {status} **{service_name.title()}**: `reports/{service_name}-coverage.json` ({coverage:.1f}% coverage)")
    
    report_sections.extend([
        "",
        "## 🛠️ Next Steps",
        "",
        "1. **Review priority gaps** and select endpoints to implement",
        "2. **Update API implementations** following [Development Guide](./docs/development.md)",
        "3. **Run compliance check** again: `scripts/check-api-compliance.sh`",
        "4. **Set up automated monitoring** in CI/CD pipeline",
        "",
        "## Related Documentation",
        "",
        "- [API Compliance Testing](./docs/api-compliance.md) - Detailed testing process",
        "- [Development Guide](./docs/development.md) - Adding new endpoints",
        "- [Architecture Overview](./docs/architecture/README.md) - System design",
    ])
    
    return "\n".join(report_sections)


def main():
    """Main function for command-line usage."""
    if len(sys.argv) < 2:
        print("Usage: python3 generate_compliance_report.py <reports_directory>")
        print("Example: python3 generate_compliance_report.py reports/")
        sys.exit(1)
    
    reports_dir = sys.argv[1]
    
    report = generate_compliance_report(reports_dir)
    print(report)


if __name__ == "__main__":
    main()