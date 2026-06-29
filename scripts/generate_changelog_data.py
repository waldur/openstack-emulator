#!/usr/bin/env python3
"""Generate structured changelog data from git history between two refs.

Collects commits between two git refs, categorizes them by type
(feature, fix, refactor, chore, docs, other), and outputs JSON
suitable for changelog generation.

Usage:
    python scripts/generate_changelog_data.py <new_ref> <old_ref>
    python scripts/generate_changelog_data.py 0.1.1 0.0.1
    python scripts/generate_changelog_data.py HEAD 0.1.1
"""

import json
import re
import subprocess
import sys
from datetime import datetime, timezone

CATEGORY_PATTERNS = {
    "features": [
        r"^feat[\(:]",
        r"^add\b",
        r"^implement\b",
        r"^extend\b",
        r"^support\b",
    ],
    "fixes": [
        r"^fix[\(:]",
        r"^fix\b",
        r"^bugfix\b",
        r"^hotfix\b",
    ],
    "refactor": [
        r"^refactor[\(:]",
        r"^refactor\b",
        r"^rename\b",
        r"^move\b",
        r"^restructure\b",
        r"^cleanup\b",
        r"^clean up\b",
    ],
    "chore": [
        r"^chore[\(:]",
        r"^chore\b",
        r"^ci[\(:]",
        r"^ci\b",
        r"^build[\(:]",
        r"^build\b",
        r"^release\b",
        r"^prepare\b",
        r"^bump\b",
    ],
    "docs": [
        r"^docs?[\(:]",
        r"^docs?\b",
        r"^readme\b",
        r"^changelog\b",
    ],
}


def run_git(args: list[str]) -> str:
    """Run a git command and return stdout."""
    result = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def get_commits(new_ref: str, old_ref: str) -> list[dict]:
    """Get commits between two refs."""
    log_format = "%H%n%h%n%an%n%aI%n%s%n---END---"
    output = run_git(
        [
            "log",
            f"{old_ref}..{new_ref}",
            f"--format={log_format}",
            "--no-merges",
        ]
    )

    if not output:
        return []

    commits = []
    entries = output.split("---END---")
    for entry in entries:
        entry = entry.strip()
        if not entry:
            continue
        lines = entry.split("\n")
        if len(lines) < 5:
            continue
        commits.append(
            {
                "hash": lines[0],
                "short_hash": lines[1],
                "author": lines[2],
                "date": lines[3],
                "subject": lines[4],
            }
        )

    return commits


def categorize_commit(subject: str) -> str:
    """Categorize a commit based on its subject line."""
    subject_lower = subject.lower()
    for category, patterns in CATEGORY_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, subject_lower):
                return category
    return "other"


def get_files_changed(new_ref: str, old_ref: str) -> dict:
    """Get summary of files changed between refs."""
    output = run_git(["diff", "--stat", f"{old_ref}..{new_ref}"])
    lines = output.strip().split("\n") if output else []

    # Parse the summary line (last line like "10 files changed, 200 insertions(+), 50 deletions(-)")
    summary = {"files_changed": 0, "insertions": 0, "deletions": 0}
    if lines:
        last_line = lines[-1]
        files_match = re.search(r"(\d+) files? changed", last_line)
        ins_match = re.search(r"(\d+) insertions?\(\+\)", last_line)
        del_match = re.search(r"(\d+) deletions?\(-\)", last_line)
        if files_match:
            summary["files_changed"] = int(files_match.group(1))
        if ins_match:
            summary["insertions"] = int(ins_match.group(1))
        if del_match:
            summary["deletions"] = int(del_match.group(1))

    return summary


def generate_changelog_data(new_ref: str, old_ref: str) -> dict:
    """Generate structured changelog data between two refs."""
    commits = get_commits(new_ref, old_ref)

    # Categorize commits
    categories = {}
    for commit in commits:
        category = categorize_commit(commit["subject"])
        commit["category"] = category
        categories.setdefault(category, []).append(commit)

    # Get diff stats
    summary_stats = get_files_changed(new_ref, old_ref)
    summary_stats["total_commits"] = len(commits)

    # Determine version and date
    version = new_ref if new_ref != "HEAD" else "unreleased"
    try:
        date = run_git(["log", "-1", "--format=%aI", new_ref])
    except subprocess.CalledProcessError:
        date = datetime.now(timezone.utc).isoformat()

    return {
        "version": version,
        "previous_version": old_ref,
        "date": date,
        "summary_stats": summary_stats,
        "commits": commits,
        "categories": {k: len(v) for k, v in categories.items()},
    }


def main():
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <new_ref> <old_ref>", file=sys.stderr)
        print(f"Example: {sys.argv[0]} 0.1.1 0.0.1", file=sys.stderr)
        sys.exit(1)

    new_ref = sys.argv[1]
    old_ref = sys.argv[2]

    data = generate_changelog_data(new_ref, old_ref)
    print(json.dumps(data, indent=2))


if __name__ == "__main__":
    main()
