#!/usr/bin/env bash
#
# Generate a changelog entry for a new release using AI.
#
# Usage:
#   ./scripts/changelog.sh <version>
#   ./scripts/changelog.sh 0.2.0
#
# Steps:
#   1. Collect commit data between <version> tag and previous tag
#   2. Generate changelog entry with `claude --print`
#   3. Insert entry into CHANGELOG.md
#
# Prerequisites:
#   - claude CLI must be installed and available in PATH
#   - Git repository with tags
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CHANGELOG_FILE="$PROJECT_ROOT/CHANGELOG.md"
PROMPT_TEMPLATE="$SCRIPT_DIR/prompts/changelog-prompt.md"

# Temp files
TMPDIR="${TMPDIR:-/tmp}"
COMMIT_DATA_FILE="$TMPDIR/openstack-emulator-changelog-commits.json"
CHANGELOG_ENTRY_FILE="$TMPDIR/openstack-emulator-changelog-entry.md"

usage() {
    echo "Usage: $0 <version>"
    echo ""
    echo "Generate a changelog entry for the given version."
    echo "The version should match a git tag or be the version being released."
    echo ""
    echo "Example:"
    echo "  $0 0.2.0"
    exit 1
}

cleanup() {
    rm -f "$COMMIT_DATA_FILE" "$CHANGELOG_ENTRY_FILE"
}

trap cleanup EXIT

get_previous_tag() {
    local version="$1"
    # Get the tag before this version
    git tag --sort=-version:refname | while read -r tag; do
        if [ "$tag" != "$version" ]; then
            echo "$tag"
            return
        fi
    done
}

# Step 1: Collect commit data
collect_commit_data() {
    local version="$1"
    local previous_tag="$2"

    echo "Collecting commits between $previous_tag and HEAD..."
    python3 "$SCRIPT_DIR/generate_changelog_data.py" HEAD "$previous_tag" > "$COMMIT_DATA_FILE"

    local commit_count
    commit_count=$(python3 -c "import json; d=json.load(open('$COMMIT_DATA_FILE')); print(d['summary_stats']['total_commits'])")
    echo "Found $commit_count commits"
}

# Step 2: Generate changelog entry with claude
generate_entry() {
    local version="$1"

    if ! command -v claude &> /dev/null; then
        echo "Error: 'claude' CLI not found. Install it or write the changelog entry manually."
        exit 1
    fi

    echo "Generating changelog entry with claude..."

    local prompt
    prompt=$(cat "$PROMPT_TEMPLATE")
    local commit_data
    commit_data=$(cat "$COMMIT_DATA_FILE")

    # Build prompt in a temp file to avoid bash 3.2 heredoc parsing issues
    local prompt_file="$TMPDIR/openstack-emulator-changelog-prompt.txt"
    {
        printf '%s\n' "$prompt"
        echo ""
        echo "## Version being released: $version"
        echo ""
        echo "## Commit data (JSON):"
        echo '```json'
        printf '%s\n' "$commit_data"
        echo '```'
        echo ""
        echo "Generate the changelog entry now. Output ONLY the markdown content for this version entry (starting with ## heading), nothing else."
    } > "$prompt_file"

    claude --print -p "$(cat "$prompt_file")" > "$CHANGELOG_ENTRY_FILE"
    rm -f "$prompt_file"

    echo ""
    echo "--- Generated entry ---"
    cat "$CHANGELOG_ENTRY_FILE"
    echo "--- End of entry ---"
    echo ""
}

# Remove an existing "## [Unreleased]" section, if any.
# The new release entry supersedes it, so it should not linger above the new entry.
strip_unreleased() {
    if [ ! -f "$CHANGELOG_FILE" ]; then
        return
    fi
    if ! grep -q "^## \[Unreleased\]" "$CHANGELOG_FILE"; then
        return
    fi
    local tmp="$CHANGELOG_FILE.tmp"
    awk '
        /^## \[Unreleased\]/ { skip = 1; next }
        skip && /^## / { skip = 0 }
        !skip { print }
    ' "$CHANGELOG_FILE" > "$tmp"
    mv "$tmp" "$CHANGELOG_FILE"
    echo "Removed existing [Unreleased] section from $CHANGELOG_FILE"
}

# Step 3: Insert entry into CHANGELOG.md
insert_entry() {
    local entry
    entry=$(cat "$CHANGELOG_ENTRY_FILE")

    strip_unreleased

    if [ ! -f "$CHANGELOG_FILE" ]; then
        # Create new changelog
        cat > "$CHANGELOG_FILE" <<EOF
# Changelog

All notable changes to openstack-emulator will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/).

$entry
EOF
        echo "Created $CHANGELOG_FILE"
    else
        # Insert after the header (after the first blank line following "# Changelog")
        # `|| true`: grep exits non-zero when there is no match, which would
        # abort the script under `set -euo pipefail`.
        local header_end
        header_end=$(grep -n "^$" "$CHANGELOG_FILE" | head -1 | cut -d: -f1 || true)

        if [ -z "$header_end" ]; then
            # No blank line found, append to end
            echo "" >> "$CHANGELOG_FILE"
            echo "$entry" >> "$CHANGELOG_FILE"
        else
            # Insert after the header section (find the line before the first ## entry).
            # `|| true`: a changelog with no entries yet has no `## ` line, and grep's
            # non-zero exit would otherwise abort the script under `set -euo pipefail`.
            local first_entry_line
            first_entry_line=$(grep -n "^## " "$CHANGELOG_FILE" | head -1 | cut -d: -f1 || true)

            if [ -z "$first_entry_line" ]; then
                # No existing entries, append
                echo "" >> "$CHANGELOG_FILE"
                echo "$entry" >> "$CHANGELOG_FILE"
            else
                # Insert before the first entry
                local before after
                before=$(head -n $((first_entry_line - 1)) "$CHANGELOG_FILE")
                after=$(tail -n +"$first_entry_line" "$CHANGELOG_FILE")
                # Ensure blank line between header and new entry, and between entries
                {
                    printf '%s\n' "$before"
                    echo ""
                    printf '%s\n' "$entry"
                    echo ""
                    printf '%s\n' "$after"
                } > "$CHANGELOG_FILE"
            fi
        fi
        echo "Updated $CHANGELOG_FILE"
    fi
}

# Main flow
main() {
    if [ $# -lt 1 ]; then
        usage
    fi

    local version="$1"
    local previous_tag

    previous_tag=$(get_previous_tag "$version")
    if [ -z "$previous_tag" ]; then
        echo "Error: Could not determine previous tag. Is '$version' a valid version?"
        exit 1
    fi

    echo "Generating changelog for $version (since $previous_tag)"
    echo ""

    # Step 1: Collect data
    collect_commit_data "$version" "$previous_tag"

    # Interactive loop
    while true; do
        # Step 2: Generate entry
        generate_entry "$version"

        echo "What would you like to do?"
        echo "  [a] Accept and insert into CHANGELOG.md"
        echo "  [e] Edit manually (opens in \$EDITOR)"
        echo "  [r] Regenerate"
        echo "  [q] Quit without saving"
        echo ""
        read -r -p "Choice [a/e/r/q]: " choice

        case "$choice" in
            a|A)
                insert_entry
                echo "Changelog entry added successfully."
                break
                ;;
            e|E)
                ${EDITOR:-vi} "$CHANGELOG_ENTRY_FILE"
                echo ""
                echo "--- Edited entry ---"
                cat "$CHANGELOG_ENTRY_FILE"
                echo "--- End of entry ---"
                echo ""
                read -r -p "Insert this entry? [y/n]: " confirm
                if [ "$confirm" = "y" ] || [ "$confirm" = "Y" ]; then
                    insert_entry
                    echo "Changelog entry added successfully."
                    break
                fi
                ;;
            r|R)
                echo "Regenerating..."
                continue
                ;;
            q|Q)
                echo "Aborted."
                exit 0
                ;;
            *)
                echo "Invalid choice."
                ;;
        esac
    done
}

main "$@"
