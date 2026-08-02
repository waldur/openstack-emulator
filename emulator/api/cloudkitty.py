"""CloudKitty (rating) API endpoints for OpenStack emulator.

Rating is what turns emulated compute and storage into the time-integrated
consumption figures a billing client asks for. Rather than keep a separate
ledger, dataframes are derived from the servers and volumes that already exist,
so a scenario that provisions resources immediately shows up in a summary.

The summary response follows CloudKitty's v2 contract: ``table`` format returns
``columns`` plus row arrays, ``object`` format returns dicts, and the default
custom fields are ``SUM(qty) AS qty, SUM(price) AS rate``.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, Request

from emulator.core.database import db
from emulator.core.simple_auth import TokenInfo, validate_token_simple

logger = logging.getLogger(__name__)

router = APIRouter(tags=["rating"])

TABLE_RESPONSE_FORMAT = "table"
OBJECT_RESPONSE_FORMAT = "object"
ALL_RESPONSE_FORMATS = (TABLE_RESPONSE_FORMAT, OBJECT_RESPONSE_FORMAT)

#: Price per unit of each emulated metric, per collection period. Deterministic
#: so a test can assert an exact rate.
UNIT_PRICES: dict[str, float] = {
    "instance": 0.05,
    "volume.size": 0.01,
}

#: The field a project is identified by, mirroring CloudKitty's
#: ``[collect] scope_key``.
SCOPE_KEY = "project_id"


def get_token_or_raise(auth_token: str | None) -> TokenInfo:
    """Validate token using shared database."""
    return validate_token_simple(auth_token, "CloudKitty")


def _period() -> tuple[datetime, datetime]:
    """The default rating window: the current month."""
    now = datetime.now(timezone.utc)
    begin = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end = (begin + timedelta(days=32)).replace(day=1)
    return begin, end


def build_dataframes() -> list[dict[str, Any]]:
    """Derive rating points from the currently emulated resources.

    One point per server and per volume, carrying the fields a mapping or a
    groupby is likely to reference.
    """
    points: list[dict[str, Any]] = []

    for server in db.list_servers():
        flavor = db.get_flavor(server.flavor_id)
        qty = 1.0
        points.append(
            {
                "type": "instance",
                "id": server.id,
                "project_id": server.tenant_id,
                "flavor_id": server.flavor_id,
                "flavor_name": flavor.name if flavor else "",
                "vcpus": flavor.vcpus if flavor else 0,
                "memory": flavor.ram if flavor else 0,
                "qty": qty,
                "rate": qty * UNIT_PRICES["instance"],
            }
        )

    for volume in db.list_volumes():
        qty = float(volume.size)
        points.append(
            {
                "type": "volume.size",
                "id": volume.id,
                "project_id": volume.project_id,
                "volume_type": volume.volume_type,
                "qty": qty,
                "rate": qty * UNIT_PRICES["volume.size"],
            }
        )

    return points


def _parse_filters(raw: list[str]) -> dict[str, list[str]]:
    """Parse repeated ``key:value`` filter parameters.

    Values may also be comma-separated within one parameter, and a key repeated
    across parameters accumulates, as in CloudKitty's ``MultiDictQueryParam``.
    """
    parsed: dict[str, list[str]] = {}
    for element in raw:
        for token in element.split(","):
            if not token:
                continue
            try:
                key, value = token.split(":", 1)
            except ValueError as exc:
                raise HTTPException(
                    status_code=400,
                    detail=f"invalid key:value association {token}",
                ) from exc
            parsed.setdefault(key, []).append(value)
    return parsed


def _matches(point: dict[str, Any], filters: dict[str, list[str]]) -> bool:
    """Whether a rating point satisfies every filter."""
    for key, values in filters.items():
        if str(point.get(key, "")) not in values:
            return False
    return True


@router.get("/v2/summary")
async def get_summary(
    request: Request,
    response_format: str = Query(TABLE_RESPONSE_FORMAT),
    groupby: list[str] = Query(default=[]),
    filters: list[str] = Query(default=[]),
    begin: str | None = Query(None),
    end: str | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1),
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """Aggregate rating data over a period, grouped by the requested fields."""
    token = get_token_or_raise(x_auth_token)

    if response_format not in ALL_RESPONSE_FORMATS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid response format [{response_format}]. "
                f"Valid format are [{list(ALL_RESPONSE_FORMATS)}]."
            ),
        )

    parsed_filters = _parse_filters(filters)
    if not token.is_admin:
        # A non-admin only ever sees its own project, whatever it asked for.
        parsed_filters[SCOPE_KEY] = [token.project_id]

    metric_types = parsed_filters.pop("type", [])
    period_begin, period_end = _period()
    begin_str = begin or period_begin.isoformat()
    end_str = end or period_end.isoformat()

    grouped: dict[tuple[str, ...], dict[str, Any]] = {}
    for point in build_dataframes():
        if metric_types and point["type"] not in metric_types:
            continue
        if not _matches(point, parsed_filters):
            continue

        key = tuple(str(point.get(field, "")) for field in groupby)
        row = grouped.get(key)
        if row is None:
            row = {"begin": begin_str, "end": end_str}
            for field in groupby:
                row[field] = point.get(field, "")
            row["qty"] = 0.0
            row["rate"] = 0.0
            grouped[key] = row
        row["qty"] += point["qty"]
        row["rate"] += point["rate"]

    results = [grouped[key] for key in sorted(grouped)]
    page = results[offset : offset + limit]

    response: dict[str, Any] = {"total": len(results)}
    if response_format == TABLE_RESPONSE_FORMAT:
        response["columns"] = list(page[0].keys()) if page else []
        response["results"] = [list(row.values()) for row in page]
    else:
        response["results"] = page
    response["format"] = response_format
    return response


@router.get("/v2/dataframes")
async def get_dataframes(
    request: Request,
    filters: list[str] = Query(default=[]),
    begin: str | None = Query(None),
    end: str | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1),
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """List the individual rating points behind the summary."""
    token = get_token_or_raise(x_auth_token)

    parsed_filters = _parse_filters(filters)
    if not token.is_admin:
        parsed_filters[SCOPE_KEY] = [token.project_id]

    metric_types = parsed_filters.pop("type", [])
    period_begin, period_end = _period()
    begin_str = begin or period_begin.isoformat()
    end_str = end or period_end.isoformat()

    points = [
        point
        for point in build_dataframes()
        if (not metric_types or point["type"] in metric_types) and _matches(point, parsed_filters)
    ]

    by_scope: dict[str, list[dict[str, Any]]] = {}
    for point in points:
        by_scope.setdefault(str(point["project_id"]), []).append(point)

    frames = [
        {
            "begin": begin_str,
            "end": end_str,
            "tenant_id": scope,
            "resources": [
                {
                    "service": point["type"],
                    "volume": str(point["qty"]),
                    "rating": {"price": str(point["rate"])},
                    "desc": {
                        key: value
                        for key, value in point.items()
                        if key not in ("qty", "rate", "type")
                    },
                }
                for point in scope_points
            ],
        }
        for scope, scope_points in sorted(by_scope.items())
    ]

    return {"total": len(frames), "dataframes": frames[offset : offset + limit]}


@router.get("/v1/rating/modules")
async def list_rating_modules(
    x_auth_token: str | None = Header(None, alias="X-Auth-Token"),
) -> dict[str, Any]:
    """List the rating modules and whether they are enabled."""
    get_token_or_raise(x_auth_token)
    return {
        "modules": [
            {
                "module_id": "hashmap",
                "description": "Hashmap rating module",
                "enabled": True,
                "hot_config": True,
                "priority": 1,
            },
            {
                "module_id": "pyscripts",
                "description": "PyScripts rating module",
                "enabled": False,
                "hot_config": True,
                "priority": 1,
            },
            {
                "module_id": "noop",
                "description": "Dummy test module",
                "enabled": False,
                "hot_config": False,
                "priority": 1,
            },
        ]
    }
