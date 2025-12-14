"""Test Keystone extension endpoints."""

import pytest
from fastapi.testclient import TestClient

from emulator.api.unified_app import create_all_service_apps
from emulator.core.database import db

# Create Keystone app for testing
service_apps = create_all_service_apps()
keystone_app = service_apps["keystone"]
client = TestClient(keystone_app)


@pytest.fixture(autouse=True)
def reset_database():
    """Reset database before each test."""
    db._application_credentials.clear()
    db._policy_documents.clear()
    db._identity_providers.clear()
    db._federation_mappings.clear()
    db._registered_limits.clear()
    db.reset_keystone()
    db._init_keystone_extensions()
    yield


@pytest.fixture
def auth_token():
    """Get a valid auth token for testing."""
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


@pytest.fixture
def admin_user_id():
    """Get the admin user ID."""
    users = db.list_users()
    admin_user = next((u for u in users if u.name == "admin"), None)
    return admin_user.id if admin_user else "admin-user-id"


class TestApplicationCredentials:
    """Test application credentials endpoints."""

    def test_list_application_credentials_empty(self, auth_token, admin_user_id):
        """Test listing application credentials when none exist."""
        response = client.get(
            f"/v3/users/{admin_user_id}/application_credentials",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200

        data = response.json()
        assert "application_credentials" in data
        assert data["application_credentials"] == []

    def test_create_application_credential(self, auth_token, admin_user_id):
        """Test creating an application credential."""
        response = client.post(
            f"/v3/users/{admin_user_id}/application_credentials",
            json={
                "application_credential": {
                    "name": "test-app-cred",
                    "description": "Test application credential",
                    "roles": [{"name": "admin"}],
                }
            },
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 201

        data = response.json()
        assert "application_credential" in data
        assert data["application_credential"]["name"] == "test-app-cred"
        assert data["application_credential"]["description"] == "Test application credential"
        assert "secret" in data["application_credential"]  # Should include secret on creation

    def test_get_application_credential(self, auth_token, admin_user_id):
        """Test getting an application credential."""
        # Create a credential first
        create_response = client.post(
            f"/v3/users/{admin_user_id}/application_credentials",
            json={"application_credential": {"name": "get-test-cred"}},
            headers={"X-Auth-Token": auth_token},
        )
        cred_id = create_response.json()["application_credential"]["id"]

        # Get the credential
        response = client.get(
            f"/v3/users/{admin_user_id}/application_credentials/{cred_id}",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200

        data = response.json()
        assert data["application_credential"]["id"] == cred_id
        assert data["application_credential"]["name"] == "get-test-cred"
        assert "secret" not in data["application_credential"]  # Should NOT include secret on get

    def test_delete_application_credential(self, auth_token, admin_user_id):
        """Test deleting an application credential."""
        # Create a credential first
        create_response = client.post(
            f"/v3/users/{admin_user_id}/application_credentials",
            json={"application_credential": {"name": "delete-test-cred"}},
            headers={"X-Auth-Token": auth_token},
        )
        cred_id = create_response.json()["application_credential"]["id"]

        # Delete the credential
        response = client.delete(
            f"/v3/users/{admin_user_id}/application_credentials/{cred_id}",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 204

        # Verify it's deleted
        response = client.get(
            f"/v3/users/{admin_user_id}/application_credentials/{cred_id}",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 404


class TestPolicyManagement:
    """Test policy management endpoints."""

    def test_list_policies_empty(self, auth_token):
        """Test listing policies when none exist."""
        response = client.get("/v3/policies", headers={"X-Auth-Token": auth_token})
        assert response.status_code == 200

        data = response.json()
        assert "policies" in data
        assert data["policies"] == []

    def test_create_policy(self, auth_token):
        """Test creating a policy."""
        policy_blob = '{"default": {"identity:get_user": "rule:admin_required"}}'

        response = client.post(
            "/v3/policies",
            json={
                "policy": {
                    "blob": policy_blob,
                    "type": "application/json",
                }
            },
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 201

        data = response.json()
        assert "policy" in data
        assert data["policy"]["blob"] == policy_blob
        assert data["policy"]["type"] == "application/json"

    def test_get_policy(self, auth_token):
        """Test getting a policy."""
        # Create a policy first
        create_response = client.post(
            "/v3/policies",
            json={"policy": {"blob": '{"test": "rule"}', "type": "application/json"}},
            headers={"X-Auth-Token": auth_token},
        )
        policy_id = create_response.json()["policy"]["id"]

        # Get the policy
        response = client.get(f"/v3/policies/{policy_id}", headers={"X-Auth-Token": auth_token})
        assert response.status_code == 200

        data = response.json()
        assert data["policy"]["id"] == policy_id
        assert data["policy"]["blob"] == '{"test": "rule"}'

    def test_update_policy(self, auth_token):
        """Test updating a policy."""
        # Create a policy first
        create_response = client.post(
            "/v3/policies",
            json={"policy": {"blob": '{"original": "rule"}'}},
            headers={"X-Auth-Token": auth_token},
        )
        policy_id = create_response.json()["policy"]["id"]

        # Update the policy
        response = client.patch(
            f"/v3/policies/{policy_id}",
            json={"policy": {"blob": '{"updated": "rule"}'}},
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200

        data = response.json()
        assert data["policy"]["blob"] == '{"updated": "rule"}'

    def test_delete_policy(self, auth_token):
        """Test deleting a policy."""
        # Create a policy first
        create_response = client.post(
            "/v3/policies",
            json={"policy": {"blob": '{"delete": "rule"}'}},
            headers={"X-Auth-Token": auth_token},
        )
        policy_id = create_response.json()["policy"]["id"]

        # Delete the policy
        response = client.delete(f"/v3/policies/{policy_id}", headers={"X-Auth-Token": auth_token})
        assert response.status_code == 204

        # Verify it's deleted
        response = client.get(f"/v3/policies/{policy_id}", headers={"X-Auth-Token": auth_token})
        assert response.status_code == 404


class TestFederation:
    """Test federation endpoints."""

    def test_list_identity_providers_empty(self, auth_token):
        """Test listing identity providers when none exist."""
        response = client.get(
            "/v3/OS-FEDERATION/identity_providers", headers={"X-Auth-Token": auth_token}
        )
        assert response.status_code == 200

        data = response.json()
        assert "identity_providers" in data
        assert data["identity_providers"] == []

    def test_create_identity_provider(self, auth_token):
        """Test creating an identity provider."""
        response = client.put(
            "/v3/OS-FEDERATION/identity_providers/test-idp",
            json={
                "identity_provider": {
                    "description": "Test identity provider",
                    "enabled": True,
                    "remote_ids": ["https://test-idp.example.com"],
                }
            },
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 201

        data = response.json()
        assert "identity_provider" in data
        assert data["identity_provider"]["id"] == "test-idp"
        assert data["identity_provider"]["description"] == "Test identity provider"
        assert data["identity_provider"]["enabled"] is True

    def test_list_federation_mappings_empty(self, auth_token):
        """Test listing federation mappings when none exist."""
        response = client.get("/v3/OS-FEDERATION/mappings", headers={"X-Auth-Token": auth_token})
        assert response.status_code == 200

        data = response.json()
        assert "mappings" in data
        assert data["mappings"] == []

    def test_create_federation_mapping(self, auth_token):
        """Test creating a federation mapping."""
        mapping_rules = [
            {
                "local": [
                    {"user": {"name": "{0}"}},
                    {"group": {"id": "federated_users"}},
                ],
                "remote": [
                    {"type": "UserName"},
                ],
            }
        ]

        response = client.put(
            "/v3/OS-FEDERATION/mappings/test-mapping",
            json={"mapping": {"rules": mapping_rules}},
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 201

        data = response.json()
        assert "mapping" in data
        assert data["mapping"]["id"] == "test-mapping"
        assert data["mapping"]["rules"] == mapping_rules


class TestRegisteredLimits:
    """Test registered limits endpoints."""

    def test_list_registered_limits_default(self, auth_token):
        """Test listing default registered limits."""
        response = client.get("/v3/registered_limits", headers={"X-Auth-Token": auth_token})
        assert response.status_code == 200

        data = response.json()
        assert "registered_limits" in data
        assert len(data["registered_limits"]) > 0  # Should have default limits

        # Check for expected limits
        limit_resources = [limit["resource_name"] for limit in data["registered_limits"]]
        assert "instances" in limit_resources
        assert "volumes" in limit_resources
        assert "networks" in limit_resources

    def test_create_registered_limit(self, auth_token):
        """Test creating a registered limit."""
        response = client.post(
            "/v3/registered_limits",
            json={
                "registered_limit": {
                    "service_id": "glance",
                    "resource_name": "images",
                    "default_limit": 100,
                    "description": "Default image limit per project",
                }
            },
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 201

        data = response.json()
        assert "registered_limit" in data
        assert data["registered_limit"]["service_id"] == "glance"
        assert data["registered_limit"]["resource_name"] == "images"
        assert data["registered_limit"]["default_limit"] == 100

    def test_get_registered_limit(self, auth_token):
        """Test getting a registered limit."""
        # Get default limits first to get an ID
        list_response = client.get("/v3/registered_limits", headers={"X-Auth-Token": auth_token})
        limits = list_response.json()["registered_limits"]
        limit_id = limits[0]["id"]

        # Get the specific limit
        response = client.get(
            f"/v3/registered_limits/{limit_id}", headers={"X-Auth-Token": auth_token}
        )
        assert response.status_code == 200

        data = response.json()
        assert "registered_limit" in data
        assert data["registered_limit"]["id"] == limit_id

    def test_filter_registered_limits_by_service(self, auth_token):
        """Test filtering registered limits by service."""
        response = client.get(
            "/v3/registered_limits?service_id=nova",
            headers={"X-Auth-Token": auth_token},
        )
        assert response.status_code == 200

        data = response.json()
        assert "registered_limits" in data

        # All returned limits should be for nova service
        for limit in data["registered_limits"]:
            assert limit["service_id"] == "nova"
