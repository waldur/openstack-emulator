"""Keystone federation attribute mapping engine.

Turns the claims an identity provider asserts about a user into a local Keystone
identity, following the same algorithm as ``keystone.federation.utils``:

* each rule's ``remote`` list is matched against the assertion; the first
  requirement whose attribute is missing makes the whole rule inapplicable;
* ``any_one_of`` / ``not_any_of`` requirements gate the rule but contribute
  nothing to the positional substitutions, while plain, ``whitelist`` and
  ``blacklist`` requirements do — which is what determines what ``{0}``,
  ``{1}`` … refer to;
* every matching rule contributes its ``local`` entries, with ``{N}``
  placeholders substituted, and the accumulated entries are folded into one
  user / groups / projects result.

The user's ``type`` decides how the identity is resolved: ``local`` requires a
Keystone user that already exists (this is how an agent pre-creating accounts
lines them up with a federated login), while ``ephemeral`` synthesizes one that
is never written to the identity store.
"""

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

ANY_ONE_OF = "any_one_of"
NOT_ANY_OF = "not_any_of"
BLACKLIST = "blacklist"
WHITELIST = "whitelist"


class MappingError(Exception):
    """Raised when an assertion cannot be mapped to any local identity."""


class DirectMaps:
    """The positional matches a rule's ``remote`` section produced.

    Each match is held as a list; a single-element list unwraps to its element
    on lookup, so ``"{0}"`` formats to the value rather than to ``['value']``.
    """

    def __init__(self) -> None:
        self._matches: list[Any] = []

    def add(self, values: Any) -> None:
        """Record one positional match."""
        self._matches.append(values)

    def __getitem__(self, index: int) -> Any:
        value = self._matches[index]
        if isinstance(value, list) and len(value) == 1:
            return value[0]
        return value

    def __len__(self) -> int:
        return len(self._matches)


def _as_list(value: Any) -> list[str]:
    """Normalize an assertion value to a list, for matching purposes only.

    Multi-valued attributes reach Keystone semicolon-delimited inside a single
    string, so they are split here before comparison. Keystone itself compares
    against the raw value, which for a string means a set of its characters —
    a quirk that makes ``any_one_of`` behave unpredictably on single-string
    attributes. Splitting first is a deliberate divergence: it is what the
    mapping author meant, and reproducing the quirk would make the emulator
    useless for validating a mapping.

    Only matching uses this; the value substituted into ``{N}`` keeps its
    original form so placeholders format exactly as they do in Keystone.
    """
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value]
    if isinstance(value, str):
        return value.split(";") if ";" in value else [value]
    return [str(value)]


def _evaluate(values: list[str], assertion_values: list[str], eval_type: str, regex: bool) -> Any:
    """Filter assertion values against a requirement, per evaluation type."""
    if regex:
        matches = [
            candidate
            for candidate in assertion_values
            if any(re.search(pattern, candidate) for pattern in values)
        ]
    else:
        matches = list(set(values).intersection(set(assertion_values)))

    if eval_type == ANY_ONE_OF:
        return bool(matches)
    if eval_type == NOT_ANY_OF:
        return not matches
    if eval_type == BLACKLIST:
        return list(set(assertion_values).difference(set(matches)))
    if eval_type == WHITELIST:
        return matches
    raise MappingError(f"Unknown evaluation type {eval_type}")


def verify_requirements(requirements: list[dict[str, Any]], assertion: dict[str, Any]) -> Any:
    """Match a rule's ``remote`` section against the assertion.

    Returns the positional matches, or None when the rule does not apply.
    """
    direct_maps = DirectMaps()

    for requirement in requirements:
        requirement_type = str(requirement.get("type", ""))
        raw_value = assertion.get(requirement_type)
        candidates = _as_list(raw_value)
        regex = bool(requirement.get("regex", False))

        if not candidates:
            return None

        any_one_values = requirement.get(ANY_ONE_OF)
        if any_one_values is not None:
            if _evaluate(any_one_values, candidates, ANY_ONE_OF, regex):
                # Gating requirements are deliberately not added to the
                # positional matches, which is why {0} skips over them.
                continue
            return None

        not_any_values = requirement.get(NOT_ANY_OF)
        if not_any_values is not None:
            if _evaluate(not_any_values, candidates, NOT_ANY_OF, regex):
                continue
            return None

        blacklisted = requirement.get(BLACKLIST)
        whitelisted = requirement.get(WHITELIST)
        if blacklisted is not None:
            direct_maps.add(_evaluate(blacklisted, candidates, BLACKLIST, regex))
        elif whitelisted is not None:
            direct_maps.add(_evaluate(whitelisted, candidates, WHITELIST, regex))
        else:
            # Unfiltered: keep the value as the provider sent it, so a
            # semicolon-delimited attribute substitutes as one string and is
            # split later by the "groups" transform, as in Keystone.
            direct_maps.add(raw_value)

    return direct_maps


def _substitute(local: Any, direct_maps: DirectMaps) -> Any:
    """Replace ``{N}`` placeholders in a ``local`` fragment, recursively."""
    if isinstance(local, dict):
        return {key: _substitute(value, direct_maps) for key, value in local.items()}
    if isinstance(local, list):
        return [_substitute(item, direct_maps) for item in local]
    if isinstance(local, str):
        try:
            return local.format(*[direct_maps[i] for i in range(len(direct_maps))])
        except (IndexError, KeyError) as exc:
            raise MappingError(
                f"Rule refers to a remote match that did not occur: {local!r}"
            ) from exc
    return local


def process_rules(rules: list[dict[str, Any]], assertion: dict[str, Any]) -> dict[str, Any]:
    """Run an attribute mapping over an assertion.

    Args:
        rules: The mapping's ``rules`` array.
        assertion: Claims asserted by the identity provider.

    Returns:
        ``{"user": {...}, "groups": [...], "projects": [...]}``.

    Raises:
        MappingError: When no rule matched, which Keystone treats as an
            authentication failure rather than an anonymous login.
    """
    identity_values: list[dict[str, Any]] = []

    for rule in rules:
        direct_maps = verify_requirements(rule.get("remote", []), assertion)
        if direct_maps is None:
            continue
        for local in rule.get("local", []):
            identity_values.append(_substitute(local, direct_maps))

    if not identity_values:
        raise MappingError("Could not map any federated user properties to identity values")

    user: dict[str, Any] = {}
    groups: list[dict[str, Any]] = []
    projects: list[dict[str, Any]] = []

    for entry in identity_values:
        if "user" in entry:
            # A mapping that yields more than one user keeps the last, as in
            # Keystone; the condition is logged rather than rejected.
            if user:
                logger.warning("Mapping produced more than one user; using the last")
            user = entry["user"]
        if "group" in entry:
            groups.append(entry["group"])
        if "groups" in entry:
            raw = entry["groups"]
            names = raw if isinstance(raw, list) else str(raw).split(";")
            domain = entry.get("domain")
            for name in names:
                if name:
                    groups.append({"name": name, **({"domain": domain} if domain else {})})
        if "projects" in entry:
            projects.extend(entry["projects"])

    return {"user": user, "groups": groups, "projects": projects}
