# Changelog Entry Generation Prompt

You are generating a changelog entry for the **openstack-emulator** project.

## Output format

Use this exact markdown structure:

```
## [X.Y.Z] - YYYY-MM-DD

### Added
- New features

### Changed
- Changes to existing features

### Fixed
- Bug fixes
```

## Rules

1. **Only use sections that have content** — omit empty sections entirely
2. **Use sentence case** for all entries (capitalize first word only)
3. **Start entries with a verb** (Add, Fix, Update, Remove, Improve, etc.)
4. **Be concise** — one line per change, no unnecessary detail
5. **Collapse revert pairs** — if a commit was reverted and redone, only mention the final state
6. **Exclude noise** — skip commits that are purely internal (linter fixes, CI tweaks, version bumps) unless they represent meaningful changes
7. **Do not invent changes** — only describe what the commits actually do
8. **Group related commits** — multiple commits for the same feature become one entry
9. **Use "Added" for new features**, "Changed" for modifications, "Fixed" for bug fixes, "Removed" for removed features

## Section mapping

- `features` category → **Added**
- `fixes` category → **Fixed**
- `refactor` category → **Changed**
- `chore` / `docs` / `other` → Use judgment: skip noise, include meaningful changes under appropriate section

## Context

openstack-emulator is a lightweight OpenStack API emulator for testing. It
provides simplified implementations of OpenStack services (Keystone, Nova,
Cinder, Glance, Neutron, Octavia, Placement) so OpenStack clients can be
developed and tested without a full OpenStack deployment. It ships a Helm
chart for Kubernetes deployment and supports failure-injection scenarios.
