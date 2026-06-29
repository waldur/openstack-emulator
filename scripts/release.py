#!/usr/bin/env python3
"""Release management script for OpenStack Emulator.

Manages releases by:
- Updating the version in both pyproject.toml and charts/openstack-emulator/Chart.yaml
- Running local pre-release checks (Python lint + type-check, Helm chart lint + unit tests)
- Creating and (optionally) pushing a git tag that triggers GitLab CI/CD

CI/CD picks up the pushed tag and:
- Publishes opennode/openstack-emulator:latest to Docker Hub (already does this on default-branch pushes)
- Publishes the packaged chart to the gh-pages branch of github.com/waldur/openstack-emulator
  (served at https://waldur.github.io/openstack-emulator/)
"""

import os
import re
import subprocess
import sys
from pathlib import Path

# Script metadata for inline dependencies
# /// script
# dependencies = ["click>=8.0.0"]
# ///
import click

REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = REPO_ROOT / "pyproject.toml"
CHART_YAML = REPO_ROOT / "charts" / "openstack-emulator" / "Chart.yaml"
CHANGELOG = REPO_ROOT / "CHANGELOG.md"
CHANGELOG_SCRIPT = REPO_ROOT / "scripts" / "changelog.sh"


def run_command(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    """Run a shell command and stream output.

    Strips VIRTUAL_ENV from the child environment so that nested `uv run`
    invocations resolve against the project venv (where ruff/mypy/pytest
    live) rather than the inline-script env that hosts this CLI.
    """
    print(f"Running: {' '.join(cmd)}")
    env = os.environ.copy()
    env.pop("VIRTUAL_ENV", None)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=check, env=env)
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        return result
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {e}")
        if e.stderr:
            print(f"Error output: {e.stderr}")
        if check:
            sys.exit(1)
        return e


def get_pyproject_version() -> str:
    """Read the version from pyproject.toml's [project] section."""
    if not PYPROJECT.exists():
        print(f"Error: {PYPROJECT} not found")
        sys.exit(1)
    content = PYPROJECT.read_text()
    match = re.search(r"\[project\].*?\nversion\s*=\s*\"([^\"]+)\"", content, re.DOTALL)
    if not match:
        print("Error: Could not find [project].version in pyproject.toml")
        sys.exit(1)
    return match.group(1)


def get_chart_version() -> str:
    """Read the version from charts/openstack-emulator/Chart.yaml."""
    if not CHART_YAML.exists():
        print(f"Error: {CHART_YAML} not found")
        sys.exit(1)
    for line in CHART_YAML.read_text().splitlines():
        if line.startswith("version:"):
            return line.split(":", 1)[1].strip().strip("\"'")
    print("Error: Could not find version: in Chart.yaml")
    sys.exit(1)


def update_pyproject_version(new_version: str) -> None:
    """Update pyproject.toml's [project] section version."""
    content = PYPROJECT.read_text()
    updated = re.sub(
        r"(\[project\].*?\nversion\s*=\s*)\"[^\"]+\"",
        f'\\1"{new_version}"',
        content,
        flags=re.DOTALL,
    )
    if updated == content:
        print("Error: Could not update version in pyproject.toml")
        sys.exit(1)
    PYPROJECT.write_text(updated)
    print(f'Updated pyproject.toml -> version = "{new_version}"')


def update_chart_version(new_version: str) -> None:
    """Update charts/openstack-emulator/Chart.yaml's version field.

    Leaves appVersion untouched: the emulator image is currently only published with
    the :latest tag, and bumping appVersion would make the chart try to pull a
    non-existent image tag.
    """
    lines = CHART_YAML.read_text().splitlines(keepends=True)
    updated_lines = []
    found = False
    for line in lines:
        if line.startswith("version:"):
            updated_lines.append(f"version: {new_version}\n")
            found = True
        else:
            updated_lines.append(line)
    if not found:
        print("Error: Could not find version: line in Chart.yaml")
        sys.exit(1)
    CHART_YAML.write_text("".join(updated_lines))
    print(f"Updated Chart.yaml -> version: {new_version}")


def validate_version(version: str) -> bool:
    """Validate semver (X.Y.Z with optional -prerelease and +build)."""
    pattern = r"^\d+\.\d+\.\d+(?:-[a-zA-Z0-9.-]+)?(?:\+[a-zA-Z0-9.-]+)?$"
    return bool(re.match(pattern, version))


def check_git_status() -> None:
    """Refuse to release with a dirty working tree unless explicitly confirmed."""
    result = run_command(["git", "status", "--porcelain"], check=False)
    if result.returncode != 0:
        print("Error: Not in a git repository")
        sys.exit(1)
    if result.stdout.strip():
        print("Warning: Git working directory is not clean:")
        print(result.stdout)
        if not click.confirm("Continue with uncommitted changes?"):
            sys.exit(1)


def run_pre_release_checks() -> None:
    """Local equivalents of the CI lint/type/chart jobs.

    Keep these fast — full tests run in CI. The point here is to catch the
    obvious-and-quick mistakes before pushing a tag.
    """
    print("Running local pre-release checks...")

    print("Python: ruff format --check ...")
    run_command(["uv", "run", "ruff", "format", "--check", "."])

    print("Python: ruff check ...")
    run_command(["uv", "run", "ruff", "check", "."])

    print("Python: mypy ...")
    run_command(["uv", "run", "mypy", "emulator", "--ignore-missing-imports"])

    print("Helm: lint chart ...")
    run_command(["helm", "lint", str(CHART_YAML.parent)])

    print("Helm: unittest chart ...")
    result = run_command(["helm", "unittest", str(CHART_YAML.parent)], check=False)
    if result.returncode != 0:
        print(
            "Note: `helm unittest` requires the helm-unittest plugin. Install with:\n"
            "  helm plugin install https://github.com/helm-unittest/helm-unittest.git --version v0.8.2"
        )
        if not click.confirm("Skip helm unittest and continue?"):
            sys.exit(1)

    print("All local pre-release checks passed.")
    print("Note: full pytest matrix runs in GitLab CI.")


def build_artifacts() -> None:
    """Build the Python sdist/wheel and package the chart locally.

    These are throwaway local builds — CI/CD does the canonical builds and
    publishes them. Useful for sanity-checking the artifact filenames.
    """
    print("Building Python package locally (uv build) ...")
    run_command(["uv", "build"])
    print("Packaging Helm chart locally (helm package) ...")
    out_dir = REPO_ROOT / "dist"
    out_dir.mkdir(exist_ok=True)
    run_command(["helm", "package", str(CHART_YAML.parent), "-d", str(out_dir)])
    print(f"Local artifacts written to {out_dir}/")


def generate_changelog(version: str) -> None:
    """Generate a CHANGELOG.md entry for the release via scripts/changelog.sh.

    The helper shells out to the `claude` CLI and is interactive (accept/edit/
    regenerate/quit), so this only makes sense for local releases — it is not
    wired into CI. If the helper is missing or fails, offer to continue the
    release without a changelog update rather than aborting outright.
    """
    if not CHANGELOG_SCRIPT.exists():
        print(f"Warning: {CHANGELOG_SCRIPT} not found, skipping changelog generation")
        return

    print(f"Generating changelog entry for {version}...")
    result = subprocess.run(["bash", str(CHANGELOG_SCRIPT), version], check=False)
    if result.returncode != 0:
        print("Warning: Changelog generation failed or was aborted")
        if not click.confirm("Continue release without changelog update?"):
            sys.exit(1)


def create_git_tag(version: str) -> None:
    """Commit the version bump and create the git tag.

    Tag scheme is X.Y.Z (no leading 'v') because the CI rules in
    .gitlab-ci.yml match on $CI_COMMIT_TAG and the publish job derives the
    chart filename from $CI_COMMIT_TAG directly.
    """
    tag_name = version

    to_add = [str(PYPROJECT), str(CHART_YAML)]
    if CHANGELOG.exists():
        to_add.append(str(CHANGELOG))
    run_command(["git", "add", *to_add])
    run_command(["git", "commit", "-m", f"Release version {version}"])
    run_command(["git", "tag", "-a", tag_name, "-m", f"Release {version}"])

    print(f"Created git tag: {tag_name}")
    print("Pushing the tag will trigger GitLab CI to:")
    print("  - Run linters + tests + Helm chart lint")
    print("  - Publish opennode/openstack-emulator:latest to Docker Hub")
    print("  - Push openstack-emulator-X.Y.Z.tgz + updated index.yaml to gh-pages on GitHub")

    if click.confirm("Push tag (and the bump commit) to origin?"):
        run_command(["git", "push"])
        run_command(["git", "push", "--tags"])
        print("Pushed. Watch the GitLab pipeline for the release jobs.")


@click.group()
def cli() -> None:
    """OpenStack Emulator release management."""


@cli.command()
def status() -> None:
    """Show current versions and recent tags."""
    py_v = get_pyproject_version()
    ch_v = get_chart_version()
    print(f"pyproject.toml      version: {py_v}")
    print(f"Chart.yaml          version: {ch_v}")
    if py_v != ch_v:
        print("WARN: pyproject.toml and Chart.yaml are out of sync.")
    result = run_command(["git", "tag", "--list", "--sort=-creatordate"], check=False)
    if result.returncode == 0 and result.stdout.strip():
        print("Recent tags:")
        for tag in result.stdout.strip().splitlines()[:10]:
            print(f"  {tag}")
    else:
        print("No tags found.")


@cli.command()
@click.argument("version")
@click.option("--skip-checks", is_flag=True, help="Skip local pre-release checks.")
@click.option("--skip-changelog", is_flag=True, help="Skip CHANGELOG.md generation.")
@click.option("--skip-tag", is_flag=True, help="Bump versions but do not commit/tag.")
def release(version: str, skip_checks: bool, skip_changelog: bool, skip_tag: bool) -> None:
    """Cut a new release: bump versions, optionally run checks, optionally tag and push."""
    current = get_pyproject_version()

    if not validate_version(version):
        print(f"Error: Invalid version format: {version}")
        print("Use semver: e.g. 0.1.0, 1.2.3-rc.1")
        sys.exit(1)

    if version == current:
        print(f"Error: New version {version} matches current version")
        sys.exit(1)

    print(f"Releasing {version} (current: {current})")
    check_git_status()
    update_pyproject_version(version)
    update_chart_version(version)

    if not skip_checks:
        run_pre_release_checks()

    if not skip_changelog:
        generate_changelog(version)

    if not skip_tag:
        create_git_tag(version)

    print(f"Done: {version}")


@cli.command()
@click.argument("version")
def version_update(version: str) -> None:
    """Just bump pyproject.toml + Chart.yaml. No tag, no commit."""
    if not validate_version(version):
        print(f"Error: Invalid version format: {version}")
        sys.exit(1)
    print(f"Bumping from {get_pyproject_version()} to {version}")
    update_pyproject_version(version)
    update_chart_version(version)


@cli.command()
def build() -> None:
    """Build the Python sdist/wheel + Helm chart .tgz locally (for sanity-checking)."""
    build_artifacts()


@cli.command()
def check() -> None:
    """Run the same pre-release checks `release` runs, without bumping anything."""
    run_pre_release_checks()


if __name__ == "__main__":
    cli()
