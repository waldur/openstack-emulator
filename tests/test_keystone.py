"""Tests for Keystone Identity API v3 endpoints."""

import pytest
from fastapi.testclient import TestClient

from emulator.api.unified_app import create_all_service_apps
from emulator.core.database import db
from emulator.core.simple_auth import validate_token_simple


@pytest.fixture
def client():
    """Create a test client."""
    apps = create_all_service_apps()
    return TestClient(apps["keystone"])


@pytest.fixture
def auth_token(client):
    """Get an authentication token."""
    response = client.post(
        "/v3/auth/tokens",
        json={
            "auth": {
                "identity": {
                    "methods": ["password"],
                    "password": {
                        "user": {
                            "name": "admin",
                            "domain": {"id": "default"},
                            "password": "s4l4dus",
                        }
                    },
                },
                "scope": {"project": {"name": "admin", "domain": {"id": "default"}}},
            }
        },
    )
    return response.headers["X-Subject-Token"]


@pytest.fixture(autouse=True)
def reset_db():
    """Reset database before each test."""
    db.reset_keystone()
    yield


class TestVersions:
    """Tests for version endpoints."""

    def test_list_versions(self, client):
        """Test listing API versions."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "versions" in data
        assert "values" in data["versions"]
        assert len(data["versions"]["values"]) > 0

    def test_get_v3_version(self, client):
        """Test getting v3 version details."""
        response = client.get("/v3/")
        assert response.status_code == 200
        data = response.json()
        assert "version" in data
        assert data["version"]["id"] == "v3.14"
        assert data["version"]["status"] == "stable"


class TestTokens:
    """Tests for token authentication."""

    def test_create_token(self, client):
        """Test creating a token."""
        response = client.post(
            "/v3/auth/tokens",
            json={
                "auth": {
                    "identity": {
                        "methods": ["password"],
                        "password": {
                            "user": {
                                "name": "admin",
                                "domain": {"id": "default"},
                                "password": "s4l4dus",
                            }
                        },
                    },
                    "scope": {"project": {"name": "admin", "domain": {"id": "default"}}},
                }
            },
        )
        assert response.status_code == 200
        assert "X-Subject-Token" in response.headers
        data = response.json()
        assert "token" in data
        assert data["token"]["user"]["name"] == "admin"

    def test_validate_token(self, client, auth_token):
        """Test validating a token."""
        response = client.get(
            "/v3/auth/tokens",
            headers={"X-Auth-Token": auth_token, "X-Subject-Token": auth_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert "token" in data

    def test_check_token(self, client, auth_token):
        """Test checking if a token is valid."""
        response = client.head(
            "/v3/auth/tokens",
            headers={"X-Auth-Token": auth_token, "X-Subject-Token": auth_token},
        )
        assert response.status_code == 200

    def test_revoke_token(self, client, auth_token):
        """Test revoking a token."""
        response = client.delete(
            "/v3/auth/tokens",
            headers={"X-Auth-Token": auth_token, "X-Subject-Token": auth_token},
        )
        assert response.status_code == 204

    def test_get_catalog(self, client, auth_token):
        """Test getting service catalog."""
        response = client.get(
            "/v3/auth/catalog",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert "catalog" in data

    def test_catalog_contains_all_services(self, client, auth_token):
        """Test that the service catalog contains all expected services."""
        response = client.get(
            "/v3/auth/catalog",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200
        catalog = response.json()["catalog"]
        service_types = {entry["type"] for entry in catalog}
        expected = {
            "compute",
            "identity",
            "image",
            "volumev3",
            "network",
            "load-balancer",
            "placement",
            "object-store",
        }
        assert expected == service_types

    def test_catalog_octavia_endpoints(self, client, auth_token):
        """Test that Octavia entry has correct endpoints on port 9876."""
        response = client.get(
            "/v3/auth/catalog",
            headers={"X-Auth-Token": auth_token},
        )
        catalog = response.json()["catalog"]
        octavia = next(e for e in catalog if e["type"] == "load-balancer")
        assert octavia["name"] == "octavia"
        interfaces = {ep["interface"] for ep in octavia["endpoints"]}
        assert interfaces == {"public", "internal", "admin"}
        for ep in octavia["endpoints"]:
            assert ":9876" in ep["url"]


class TestDomains:
    """Tests for domain management."""

    def test_list_domains(self, client, auth_token):
        """Test listing domains."""
        response = client.get(
            "/v3/domains",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert "domains" in data
        # Should have default domain
        assert len(data["domains"]) >= 1

    def test_create_domain(self, client, auth_token):
        """Test creating a domain."""
        response = client.post(
            "/v3/domains",
            headers={"X-Auth-Token": auth_token},
            json={"domain": {"name": "test-domain", "description": "Test domain"}},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["domain"]["name"] == "test-domain"

    def test_get_domain(self, client, auth_token):
        """Test getting a domain."""
        response = client.get(
            "/v3/domains/default",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["domain"]["id"] == "default"

    def test_update_domain(self, client, auth_token):
        """Test updating a domain."""
        # Create a domain first
        create_response = client.post(
            "/v3/domains",
            headers={"X-Auth-Token": auth_token},
            json={"domain": {"name": "update-test"}},
        )
        domain_id = create_response.json()["domain"]["id"]

        response = client.patch(
            f"/v3/domains/{domain_id}",
            headers={"X-Auth-Token": auth_token},
            json={"domain": {"description": "Updated description"}},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["domain"]["description"] == "Updated description"

    def test_delete_domain(self, client, auth_token):
        """Test deleting a domain."""
        # Create a domain first
        create_response = client.post(
            "/v3/domains",
            headers={"X-Auth-Token": auth_token},
            json={"domain": {"name": "delete-test"}},
        )
        domain_id = create_response.json()["domain"]["id"]

        response = client.delete(
            f"/v3/domains/{domain_id}",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 204


class TestProjects:
    """Tests for project management."""

    def test_list_projects(self, client, auth_token):
        """Test listing projects."""
        response = client.get(
            "/v3/projects",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert "projects" in data
        # Should have admin and service projects
        assert len(data["projects"]) >= 2

    def test_create_project(self, client, auth_token):
        """Test creating a project."""
        response = client.post(
            "/v3/projects",
            headers={"X-Auth-Token": auth_token},
            json={"project": {"name": "test-project", "description": "Test project"}},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["project"]["name"] == "test-project"

    def test_get_project(self, client, auth_token):
        """Test getting a project."""
        # Get list to find a project ID
        list_response = client.get(
            "/v3/projects",
            headers={"X-Auth-Token": auth_token},
        )
        project_id = list_response.json()["projects"][0]["id"]

        response = client.get(
            f"/v3/projects/{project_id}",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["project"]["id"] == project_id

    def test_update_project(self, client, auth_token):
        """Test updating a project."""
        # Create a project first
        create_response = client.post(
            "/v3/projects",
            headers={"X-Auth-Token": auth_token},
            json={"project": {"name": "update-project-test"}},
        )
        project_id = create_response.json()["project"]["id"]

        response = client.patch(
            f"/v3/projects/{project_id}",
            headers={"X-Auth-Token": auth_token},
            json={"project": {"description": "Updated description"}},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["project"]["description"] == "Updated description"

    def test_delete_project(self, client, auth_token):
        """Test deleting a project."""
        # Create a project first
        create_response = client.post(
            "/v3/projects",
            headers={"X-Auth-Token": auth_token},
            json={"project": {"name": "delete-project-test"}},
        )
        project_id = create_response.json()["project"]["id"]

        response = client.delete(
            f"/v3/projects/{project_id}",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 204


class TestUsers:
    """Tests for user management."""

    def test_list_users(self, client, auth_token):
        """Test listing users."""
        response = client.get(
            "/v3/users",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert "users" in data
        # Should have admin user
        assert len(data["users"]) >= 1

    def test_create_user(self, client, auth_token):
        """Test creating a user."""
        response = client.post(
            "/v3/users",
            headers={"X-Auth-Token": auth_token},
            json={
                "user": {
                    "name": "test-user",
                    "email": "test@example.com",
                    "password": "secret123",
                }
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["user"]["name"] == "test-user"
        assert data["user"]["email"] == "test@example.com"

    def test_get_user(self, client, auth_token):
        """Test getting a user."""
        # Get list to find a user ID
        list_response = client.get(
            "/v3/users",
            headers={"X-Auth-Token": auth_token},
        )
        user_id = list_response.json()["users"][0]["id"]

        response = client.get(
            f"/v3/users/{user_id}",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["user"]["id"] == user_id

    def test_update_user(self, client, auth_token):
        """Test updating a user."""
        # Create a user first
        create_response = client.post(
            "/v3/users",
            headers={"X-Auth-Token": auth_token},
            json={"user": {"name": "update-user-test"}},
        )
        user_id = create_response.json()["user"]["id"]

        response = client.patch(
            f"/v3/users/{user_id}",
            headers={"X-Auth-Token": auth_token},
            json={"user": {"email": "updated@example.com"}},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["user"]["email"] == "updated@example.com"

    def test_delete_user(self, client, auth_token):
        """Test deleting a user."""
        # Create a user first
        create_response = client.post(
            "/v3/users",
            headers={"X-Auth-Token": auth_token},
            json={"user": {"name": "delete-user-test"}},
        )
        user_id = create_response.json()["user"]["id"]

        response = client.delete(
            f"/v3/users/{user_id}",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 204


class TestRoles:
    """Tests for role management."""

    def test_list_roles(self, client, auth_token):
        """Test listing roles."""
        response = client.get(
            "/v3/roles",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert "roles" in data
        # Should have default roles
        assert len(data["roles"]) >= 3

    def test_create_role(self, client, auth_token):
        """Test creating a role."""
        response = client.post(
            "/v3/roles",
            headers={"X-Auth-Token": auth_token},
            json={"role": {"name": "test-role", "description": "Test role"}},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["role"]["name"] == "test-role"

    def test_get_role(self, client, auth_token):
        """Test getting a role."""
        # Get list to find a role ID
        list_response = client.get(
            "/v3/roles",
            headers={"X-Auth-Token": auth_token},
        )
        role_id = list_response.json()["roles"][0]["id"]

        response = client.get(
            f"/v3/roles/{role_id}",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["role"]["id"] == role_id

    def test_delete_role(self, client, auth_token):
        """Test deleting a role."""
        # Create a role first
        create_response = client.post(
            "/v3/roles",
            headers={"X-Auth-Token": auth_token},
            json={"role": {"name": "delete-role-test"}},
        )
        role_id = create_response.json()["role"]["id"]

        response = client.delete(
            f"/v3/roles/{role_id}",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 204


class TestRoleAssignments:
    """Tests for role assignment management."""

    def test_assign_role_to_user_on_project(self, client, auth_token):
        """Test assigning a role to a user on a project."""
        # Get user, project, and role
        users = client.get("/v3/users", headers={"X-Auth-Token": auth_token}).json()["users"]
        projects = client.get("/v3/projects", headers={"X-Auth-Token": auth_token}).json()[
            "projects"
        ]
        roles = client.get("/v3/roles", headers={"X-Auth-Token": auth_token}).json()["roles"]

        user_id = users[0]["id"]
        project_id = projects[0]["id"]
        role_id = roles[0]["id"]

        response = client.put(
            f"/v3/projects/{project_id}/users/{user_id}/roles/{role_id}",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 204

    def test_list_role_assignments(self, client, auth_token):
        """Test listing role assignments."""
        response = client.get(
            "/v3/role_assignments",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert "role_assignments" in data

    def test_revoke_role_from_user_on_project(self, client, auth_token):
        """Test revoking a role from a user on a project."""
        # Get user, project, and role
        users = client.get("/v3/users", headers={"X-Auth-Token": auth_token}).json()["users"]
        projects = client.get("/v3/projects", headers={"X-Auth-Token": auth_token}).json()[
            "projects"
        ]
        roles = client.get("/v3/roles", headers={"X-Auth-Token": auth_token}).json()["roles"]

        user_id = users[0]["id"]
        project_id = projects[0]["id"]
        role_id = roles[0]["id"]

        # Assign first
        client.put(
            f"/v3/projects/{project_id}/users/{user_id}/roles/{role_id}",
            headers={"X-Auth-Token": auth_token},
        )

        # Then revoke
        response = client.delete(
            f"/v3/projects/{project_id}/users/{user_id}/roles/{role_id}",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 204


class TestGroups:
    """Tests for group management."""

    def test_list_groups(self, client, auth_token):
        """Test listing groups."""
        response = client.get(
            "/v3/groups",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert "groups" in data

    def test_create_group(self, client, auth_token):
        """Test creating a group."""
        response = client.post(
            "/v3/groups",
            headers={"X-Auth-Token": auth_token},
            json={"group": {"name": "test-group", "description": "Test group"}},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["group"]["name"] == "test-group"

    def test_get_group(self, client, auth_token):
        """Test getting a group."""
        # Create a group first
        create_response = client.post(
            "/v3/groups",
            headers={"X-Auth-Token": auth_token},
            json={"group": {"name": "get-group-test"}},
        )
        group_id = create_response.json()["group"]["id"]

        response = client.get(
            f"/v3/groups/{group_id}",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["group"]["id"] == group_id

    def test_add_user_to_group(self, client, auth_token):
        """Test adding a user to a group."""
        # Create a group
        group_response = client.post(
            "/v3/groups",
            headers={"X-Auth-Token": auth_token},
            json={"group": {"name": "membership-test"}},
        )
        group_id = group_response.json()["group"]["id"]

        # Get a user
        users = client.get("/v3/users", headers={"X-Auth-Token": auth_token}).json()["users"]
        user_id = users[0]["id"]

        response = client.put(
            f"/v3/groups/{group_id}/users/{user_id}",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 204

    def test_list_group_users(self, client, auth_token):
        """Test listing users in a group."""
        # Create a group
        group_response = client.post(
            "/v3/groups",
            headers={"X-Auth-Token": auth_token},
            json={"group": {"name": "list-users-test"}},
        )
        group_id = group_response.json()["group"]["id"]

        response = client.get(
            f"/v3/groups/{group_id}/users",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert "users" in data


class TestServices:
    """Tests for service management."""

    def test_list_services(self, client, auth_token):
        """Test listing services."""
        response = client.get(
            "/v3/services",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert "services" in data
        # Should have default services (keystone, nova, glance)
        assert len(data["services"]) >= 3

    def test_create_service(self, client, auth_token):
        """Test creating a service."""
        response = client.post(
            "/v3/services",
            headers={"X-Auth-Token": auth_token},
            json={
                "service": {
                    "name": "cinder",
                    "type": "volume",
                    "description": "Block Storage Service",
                }
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["service"]["name"] == "cinder"
        assert data["service"]["type"] == "volume"

    def test_get_service(self, client, auth_token):
        """Test getting a service."""
        # Get list to find a service ID
        list_response = client.get(
            "/v3/services",
            headers={"X-Auth-Token": auth_token},
        )
        service_id = list_response.json()["services"][0]["id"]

        response = client.get(
            f"/v3/services/{service_id}",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["service"]["id"] == service_id


class TestEndpoints:
    """Tests for endpoint management."""

    def test_list_endpoints(self, client, auth_token):
        """Test listing endpoints."""
        response = client.get(
            "/v3/endpoints",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert "endpoints" in data

    def test_create_endpoint(self, client, auth_token):
        """Test creating an endpoint."""
        # Get a service ID first
        services = client.get("/v3/services", headers={"X-Auth-Token": auth_token}).json()[
            "services"
        ]
        service_id = services[0]["id"]

        response = client.post(
            "/v3/endpoints",
            headers={"X-Auth-Token": auth_token},
            json={
                "endpoint": {
                    "service_id": service_id,
                    "interface": "public",
                    "url": "http://localhost:8774/v2.1",
                    "region_id": "RegionOne",
                }
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["endpoint"]["interface"] == "public"


class TestRegions:
    """Tests for region management."""

    def test_list_regions(self, client, auth_token):
        """Test listing regions."""
        response = client.get(
            "/v3/regions",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert "regions" in data
        # Should have RegionOne
        assert len(data["regions"]) >= 1

    def test_create_region(self, client, auth_token):
        """Test creating a region."""
        response = client.post(
            "/v3/regions",
            headers={"X-Auth-Token": auth_token},
            json={"region": {"id": "RegionTwo", "description": "Second region"}},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["region"]["id"] == "RegionTwo"

    def test_get_region(self, client, auth_token):
        """Test getting a region."""
        response = client.get(
            "/v3/regions/RegionOne",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["region"]["id"] == "RegionOne"


class TestCredentials:
    """Tests for credential management."""

    def test_list_credentials(self, client, auth_token):
        """Test listing credentials."""
        response = client.get(
            "/v3/credentials",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert "credentials" in data

    def test_create_credential(self, client, auth_token):
        """Test creating a credential."""
        # Get a user ID
        users = client.get("/v3/users", headers={"X-Auth-Token": auth_token}).json()["users"]
        user_id = users[0]["id"]

        response = client.post(
            "/v3/credentials",
            headers={"X-Auth-Token": auth_token},
            json={
                "credential": {
                    "user_id": user_id,
                    "type": "ec2",
                    "blob": '{"access": "AKIAIOSFODNN7", "secret": "wJalrXUtnFEMI"}',
                }
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["credential"]["type"] == "ec2"


class TestAuthFailures:
    """Tests for authentication failures."""

    def test_invalid_token(self, client):
        """Test with an invalid token."""
        response = client.get(
            "/v3/users",
            headers={"X-Auth-Token": "invalid-token"},
        )
        assert response.status_code == 401

    def test_expired_token(self, client, auth_token):
        """Test revoking and using an expired token."""
        # Revoke the token
        client.delete(
            "/v3/auth/tokens",
            headers={"X-Auth-Token": auth_token, "X-Subject-Token": auth_token},
        )

        # Try to use it
        response = client.get(
            "/v3/users",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 401


class TestScopePrivilege:
    """A token is privileged only when it is genuinely scoped to "admin".

    ``validate_token_simple`` derives ``is_admin`` from the token's project
    name. Scoping by project id used to default that name to "admin", so a
    session scoped to an id the emulator had never seen came back with
    cross-tenant access.
    """

    @staticmethod
    def _authenticate(client, scope):
        response = client.post(
            "/v3/auth/tokens",
            json={
                "auth": {
                    "identity": {
                        "methods": ["password"],
                        "password": {
                            "user": {
                                "name": "alice",
                                "domain": {"id": "default"},
                                "password": "pw",
                            }
                        },
                    },
                    "scope": scope,
                }
            },
        )
        assert response.status_code in (200, 201)
        return response.headers["X-Subject-Token"]

    def test_scope_by_name_admin_is_privileged(self, client):
        token = self._authenticate(
            client, {"project": {"name": "admin", "domain": {"id": "default"}}}
        )
        assert validate_token_simple(token).is_admin is True

    def test_unscoped_request_keeps_the_admin_default(self, client):
        token = self._authenticate(client, None)
        assert validate_token_simple(token).is_admin is True

    def test_scope_by_unknown_project_id_is_not_privileged(self, client):
        token = self._authenticate(
            client, {"project": {"id": "11111111-2222-3333-4444-555555555555"}}
        )

        info = validate_token_simple(token)
        assert info.is_admin is False
        assert info.project_id == "11111111-2222-3333-4444-555555555555"
        assert info.project_name != "admin"

    def test_scope_by_known_project_id_uses_the_real_name(self, client):
        project = db.create_project(name="tenant-a", domain_id="default")

        token = self._authenticate(client, {"project": {"id": project.id}})

        info = validate_token_simple(token)
        assert info.project_name == "tenant-a"
        assert info.is_admin is False

    def test_scope_by_known_admin_project_id_is_privileged(self, client):
        admin_project = db.get_project_by_name("admin", "default")

        token = self._authenticate(client, {"project": {"id": admin_project.id}})

        assert validate_token_simple(token).is_admin is True
