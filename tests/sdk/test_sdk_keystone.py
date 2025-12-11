"""SDK tests for Keystone Identity service."""

from openstack.connection import Connection


class TestKeystoneAuthentication:
    """Test Keystone authentication via SDK."""

    def test_connection_authorized(self, openstack_connection: Connection) -> None:
        """Test that SDK connection is properly authenticated."""
        # Simply getting the project ID verifies auth worked
        assert openstack_connection.current_project_id is not None

    def test_get_token(self, openstack_connection: Connection) -> None:
        """Test that we can get an authentication token."""
        # The auth_token property returns the current token
        token = openstack_connection.auth_token
        assert token is not None
        assert len(token) > 0


class TestKeystoneProjects:
    """Test Keystone project operations via SDK."""

    def test_list_projects(self, openstack_connection: Connection) -> None:
        """Test listing projects."""
        projects = list(openstack_connection.identity.projects())
        assert len(projects) > 0

        # Admin project should exist
        project_names = [p.name for p in projects]
        assert "admin" in project_names

    def test_get_project(self, openstack_connection: Connection) -> None:
        """Test getting a specific project."""
        # First list to get a project
        projects = list(openstack_connection.identity.projects())
        assert len(projects) > 0

        # Get project by ID
        project = openstack_connection.identity.get_project(projects[0].id)
        assert project is not None
        assert project.id == projects[0].id

    def test_create_project(self, openstack_connection: Connection) -> None:
        """Test creating a new project."""
        project = openstack_connection.identity.create_project(
            name="test-sdk-project",
            description="Test project created via SDK",
        )
        assert project is not None
        assert project.name == "test-sdk-project"
        assert project.description == "Test project created via SDK"

    def test_update_project(self, openstack_connection: Connection) -> None:
        """Test updating a project."""
        # Create a project first
        project = openstack_connection.identity.create_project(
            name="update-test-project",
        )

        # Update it
        updated = openstack_connection.identity.update_project(
            project.id,
            description="Updated description",
        )
        assert updated.description == "Updated description"

    def test_delete_project(self, openstack_connection: Connection) -> None:
        """Test deleting a project."""
        # Create a project first
        project = openstack_connection.identity.create_project(
            name="delete-test-project",
        )

        # Delete it
        result = openstack_connection.identity.delete_project(project.id)
        assert result is None  # delete returns None on success

        # Verify it's gone
        projects = list(openstack_connection.identity.projects())
        project_ids = [p.id for p in projects]
        assert project.id not in project_ids


class TestKeystoneUsers:
    """Test Keystone user operations via SDK."""

    def test_list_users(self, openstack_connection: Connection) -> None:
        """Test listing users."""
        users = list(openstack_connection.identity.users())
        assert len(users) > 0

        # Admin user should exist
        user_names = [u.name for u in users]
        assert "admin" in user_names

    def test_get_user(self, openstack_connection: Connection) -> None:
        """Test getting a specific user."""
        users = list(openstack_connection.identity.users())
        assert len(users) > 0

        user = openstack_connection.identity.get_user(users[0].id)
        assert user is not None
        assert user.id == users[0].id

    def test_create_user(self, openstack_connection: Connection) -> None:
        """Test creating a new user."""
        user = openstack_connection.identity.create_user(
            name="test-sdk-user",
            password="testpassword123",
            description="Test user created via SDK",
        )
        assert user is not None
        assert user.name == "test-sdk-user"

    def test_update_user(self, openstack_connection: Connection) -> None:
        """Test updating a user."""
        # Create a user first
        user = openstack_connection.identity.create_user(
            name="update-test-user",
            password="password123",
        )

        # Update it
        updated = openstack_connection.identity.update_user(
            user.id,
            description="Updated user description",
        )
        assert updated.description == "Updated user description"

    def test_delete_user(self, openstack_connection: Connection) -> None:
        """Test deleting a user."""
        # Create a user first
        user = openstack_connection.identity.create_user(
            name="delete-test-user",
            password="password123",
        )

        # Delete it
        result = openstack_connection.identity.delete_user(user.id)
        assert result is None  # delete returns None on success


class TestKeystoneDomains:
    """Test Keystone domain operations via SDK."""

    def test_list_domains(self, openstack_connection: Connection) -> None:
        """Test listing domains."""
        domains = list(openstack_connection.identity.domains())
        assert len(domains) > 0

        # Default domain should exist
        domain_names = [d.name for d in domains]
        assert "Default" in domain_names

    def test_get_domain(self, openstack_connection: Connection) -> None:
        """Test getting a specific domain."""
        domains = list(openstack_connection.identity.domains())
        assert len(domains) > 0

        domain = openstack_connection.identity.get_domain(domains[0].id)
        assert domain is not None


class TestKeystoneRoles:
    """Test Keystone role operations via SDK."""

    def test_list_roles(self, openstack_connection: Connection) -> None:
        """Test listing roles."""
        roles = list(openstack_connection.identity.roles())
        assert len(roles) > 0

        # Admin and member roles should exist
        role_names = [r.name for r in roles]
        assert "admin" in role_names

    def test_get_role(self, openstack_connection: Connection) -> None:
        """Test getting a specific role."""
        roles = list(openstack_connection.identity.roles())
        assert len(roles) > 0

        role = openstack_connection.identity.get_role(roles[0].id)
        assert role is not None
        assert role.id == roles[0].id

    def test_create_role(self, openstack_connection: Connection) -> None:
        """Test creating a new role."""
        role = openstack_connection.identity.create_role(
            name="test-sdk-role",
        )
        assert role is not None
        assert role.name == "test-sdk-role"


class TestKeystoneServices:
    """Test Keystone service catalog operations via SDK."""

    def test_list_services(self, openstack_connection: Connection) -> None:
        """Test listing services."""
        services = list(openstack_connection.identity.services())
        assert len(services) > 0

        # Identity service should exist
        service_types = [s.type for s in services]
        assert "identity" in service_types


class TestKeystoneEndpoints:
    """Test Keystone endpoint operations via SDK."""

    def test_list_endpoints(self, openstack_connection: Connection) -> None:
        """Test listing endpoints."""
        # Get a service to create an endpoint for
        services = list(openstack_connection.identity.services())
        assert len(services) > 0
        service = services[0]

        # Create an endpoint first since none exist by default
        endpoint = openstack_connection.identity.create_endpoint(
            service_id=service.id,
            interface="public",
            url="http://localhost:8080/v1",
            region="RegionOne",
        )
        assert endpoint is not None

        endpoints = list(openstack_connection.identity.endpoints())
        assert len(endpoints) > 0

        # Should have endpoints for various interfaces
        interfaces = [e.interface for e in endpoints]
        assert "public" in interfaces
