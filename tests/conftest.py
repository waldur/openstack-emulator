"""Shared test helpers.

Keystone refuses to mint a scoped token for a user that holds no role on the
target scope (``TokenModel._validate_project_scope``), and the emulator
reproduces that. A test that wants a project-scoped token therefore has to grant
the role first, the same bootstrap an operator performs with
``openstack role add --project <p> --user <u> <role>``.
"""

from typing import Any

from emulator.core.database import db


def grant_scope(
    project_name: str | None = None,
    project_id: str | None = None,
    user_name: str = "admin",
    role_name: str = "member",
    domain_id: str = "default",
) -> Any:
    """Ensure a project, a user and a role assignment between them exist.

    Returns the project. Everything is created only if missing, so this is safe
    to call repeatedly and safe to call for the seeded admin project.

    The role defaults to member: granting admin would make the resulting
    token privileged, and most callers want an ordinary tenant token. Pass
    role_name="admin" where the test genuinely needs a privileged one.
    """
    project = None
    if project_id:
        project = db.get_project(project_id)
    if project is None and project_name:
        project = db.get_project_by_name(project_name, domain_id)
    if project is None:
        project = db.create_project(
            name=project_name or project_id or "project",
            domain_id=domain_id,
            project_id=project_id,
        )

    user = db.get_user_by_name(user_name, domain_id)
    if user is None:
        user = db.create_user(name=user_name, domain_id=domain_id)

    role = db.get_role_by_name(role_name)
    if role is None:
        role = db.create_role(name=role_name)

    db.assign_role_to_user_on_project(role.id, user.id, project.id)
    return project


def scoped_token(
    project_name: str | None = None,
    project_id: str | None = None,
    user_name: str = "admin",
    role_name: str = "member",
    domain_id: str = "default",
) -> Any:
    """Grant the scope, then return a token object scoped to it."""
    project = grant_scope(
        project_name=project_name,
        project_id=project_id,
        user_name=user_name,
        role_name=role_name,
        domain_id=domain_id,
    )
    return db.create_token(
        user_name=user_name,
        project_name=project.name,
        project_id=project.id,
        domain_id=domain_id,
    )
