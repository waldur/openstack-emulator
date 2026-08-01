# Federated identity (OIDC)

The emulator can authenticate a user through OpenID Connect the way a real
Keystone does: an identity provider issues an access token, Keystone exchanges it
for an unscoped token by running the claims through an attribute mapping, and the
client rescopes that token to a project.

This exists so that identity integrations can be tested end to end — in
particular the pattern where something provisions Keystone accounts ahead of
time and a federated login has to land on exactly those accounts rather than
creating new ones.

Two moving parts:

- **`oidc` (port 5556)** — an embedded OpenID Provider. Self-contained, so no
  external identity provider is needed. It can be bypassed in favour of a real
  one; see [Using an external provider](#using-an-external-provider).
- **Keystone's `OS-FEDERATION` endpoints** — identity providers, protocols,
  mappings, the bearer-token exchange, and project/domain discovery.

## Quick start

The shipped `waldur-site-agent` preset wires up everything below:

```bash
openstack-emulator --preset waldur-site-agent
```

It creates a `managed` domain holding a `demo-tenant` project, users named after
their email addresses (`alice@example.org`, `bob@example.org`), an identity
provider `keycloak` with an `openid` protocol, a mapping keyed on the `email`
claim, and matching end users in the embedded provider.

Then, with openstacksdk:

```python
import openstack

conn = openstack.connect(
    auth_type="v3oidcpassword",
    auth_url="http://localhost:5000/v3",
    identity_provider="keycloak",
    protocol="openid",
    client_id="waldur",
    client_secret="secret",
    discovery_endpoint="http://localhost:5556/.well-known/openid-configuration",
    username="alice",
    password="password",
    project_name="demo-tenant",
    project_domain_name="managed",
)
print(conn.session.auth.get_auth_ref(conn.session).user_id)
```

The `openstack` CLI works the same way with `--os-auth-type v3oidcpassword`.

## The exchange

1. The client reads `GET /.well-known/openid-configuration` from the provider to
   find its token endpoint.
2. It posts a grant (password, client credentials, authorization code or refresh
   token) to `POST /token` and gets back a signed RS256 access token.
3. It posts that token as `Authorization: Bearer …` to
   `POST /v3/OS-FEDERATION/identity_providers/{idp}/protocols/{protocol}/auth`.
4. Keystone validates the token, runs its claims through the protocol's mapping,
   and returns an **unscoped** token in `X-Subject-Token`. An unscoped token
   carries no project and no service catalog.
5. The client discovers what it may scope to with
   `GET /v3/OS-FEDERATION/projects`, then rescopes through
   `POST /v3/auth/tokens` with `methods: ["token"]`.

The rescoped token keeps the federated provenance: its `user` object still
carries an `OS-FEDERATION` block naming the identity provider, protocol and
mapped groups.

## Attribute mappings

A mapping is a list of rules, each with a `remote` section that matches the
provider's claims and a `local` section that describes the resulting identity.

```json
{
  "rules": [
    {
      "local": [
        {"user": {"name": "{0}", "type": "local", "domain": {"name": "managed"}}}
      ],
      "remote": [
        {"type": "email"}
      ]
    }
  ]
}
```

### Matching

Each entry in `remote` names a claim. If the claim is absent, the whole rule is
skipped. Beyond that:

| Key | Effect |
|-----|--------|
| *(none)* | The claim's value becomes the next positional match |
| `any_one_of` | Rule applies only if the claim matches one of these. Contributes **no** positional match |
| `not_any_of` | Rule applies only if the claim matches none of these. Contributes **no** positional match |
| `whitelist` | The claim is filtered down to these values, which become the positional match |
| `blacklist` | The claim minus these values becomes the positional match |
| `regex: true` | The values above are treated as regular expressions |

The distinction matters: `any_one_of` and `not_any_of` gate a rule without
consuming a position, so `{0}` refers to the first *unfiltered* requirement, not
the first requirement.

### The local section

`{0}`, `{1}` … are substituted from the positional matches.

- `user.type: "local"` — the account must already exist; a login for an unknown
  user is refused. This is the mode to use when something else creates the
  accounts.
- `user.type: "ephemeral"` — the account is created on the fly.
- `group` / `groups` — group membership, used to reach projects the group holds a
  role on. Groups are **not** created on demand; a mapping naming an unknown
  group has that group skipped, since inventing one would grant access nobody
  configured.
- `projects` — projects to auto-provision, each with the roles to assign. Unlike
  groups these are created if missing, but the roles must already exist.

Multi-valued claims that arrive as one semicolon-delimited string are split
before matching and before `groups` expansion.

## Using an external provider

Set `remote_ids` on the identity provider to the issuer URLs you trust:

```bash
curl -X PUT http://localhost:5000/v3/OS-FEDERATION/identity_providers/keycloak \
  -H "X-Auth-Token: $TOKEN" -H 'Content-Type: application/json' \
  -d '{"identity_provider": {"domain_id": "default",
        "remote_ids": ["http://localhost:8082/default"]}}'
```

A bearer token whose `iss` matches a `remote_id` is validated against that
issuer's published JWKS (fetched from `<iss>/.well-known/jwks.json`). Tokens
minted by the embedded provider continue to work alongside it.

This is how to point the emulator at a mock provider such as
`ghcr.io/navikt/mock-oauth2-server`, or at a real Keycloak.

## The embedded provider

| Endpoint | Purpose |
|----------|---------|
| `GET /.well-known/openid-configuration` | Discovery document |
| `POST /token` | Password, client credentials, authorization code and refresh token grants |
| `GET /authorize` | Issues an authorization code; the end user is named by a `username` query parameter rather than a login form |
| `GET /userinfo` | Claims for a bearer token |
| `POST /introspect` | RFC 7662 introspection |
| `GET /keys` | JWKS |

Clients authenticate with HTTP Basic or `client_id` in the form body; both are
accepted, because keystoneauth uses whichever the configuration implies.

The RSA signing key is generated at process start and never persisted, so tokens
do not survive a restart. Clients and users, in contrast, are persisted like any
other emulator state.

Per-user claims are configurable, so a mapping can be exercised against
realistic attributes:

```yaml
federation:
  oidc_users:
    - username: alice
      password: password
      email: alice@example.org
      groups: [hpc-users]
      claims:
        eduperson_entitlement: "urn:mace:example.org:hpc"
```

## Preset reference

```yaml
federation:
  identity_providers:
    - id: keycloak
      domain: managed
      remote_ids: []          # issuer URLs to trust, for external providers
  mappings:
    - id: email-to-local-user
      rules: [...]            # as described above
  protocols:
    - id: openid
      identity_provider: keycloak
      mapping: email-to-local-user
  oidc_clients:
    - client_id: waldur
      client_secret: secret
  oidc_users:
    - username: alice
      email: alice@example.org
```

## Troubleshooting

**401 "Mapped user … does not exist in domain …"** — the mapping resolved to a
`type: local` user that is not in that domain. Check that the account was created
in the domain the mapping (or the identity provider) names, not the default one.

**401 "Could not map any federated user properties"** — no rule matched. A rule
is skipped entirely when any claim in its `remote` section is missing from the
token, so check the claims with `GET /userinfo`.

**`EmptyCatalog` when using an unscoped token** — expected. Unscoped tokens carry
no catalog; discover projects with `GET /v3/OS-FEDERATION/projects` addressed
directly, then rescope.

**Groups in the mapping had no effect** — the group must already exist in the
same domain. Unknown groups are skipped and logged rather than created.
