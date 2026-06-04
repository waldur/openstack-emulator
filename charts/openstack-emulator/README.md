# openstack-emulator Helm chart

Deploys the [OpenStack Emulator](https://code.opennodecloud.com/waldur/openstack-emulator) — a lightweight FastAPI-based stand-in for Keystone, Nova, Cinder, Glance, Neutron, Octavia, and Placement — into a Kubernetes cluster.

Primary use case: running next to a [Waldur](https://waldur.com/) deployment as a sandbox OpenStack backend for demos, exploratory testing, or failure-injection scenarios. See [`docs/kubernetes.md`](../../docs/kubernetes.md) in the same repo for the full deployment + Waldur integration walkthrough.

## TL;DR

```bash
helm install ose ./charts/openstack-emulator --namespace ose --create-namespace
helm test ose -n ose
```

In-cluster endpoint: `http://ose-openstack-emulator.ose.svc.cluster.local:5000/v3`
Hardcoded credentials: `admin` / `s4l4dus`, project `admin`, domain `Default`.

## Values reference

| Key | Default | Notes |
|---|---|---|
| `image.repository` | `opennode/openstack-emulator` | |
| `image.tag` | `""` | Falls back to `.Chart.AppVersion`. |
| `image.pullPolicy` | `IfNotPresent` | Set to `Never` when using a locally loaded image (e.g. `kind load`). |
| `replicaCount` | `1` | Fixed; emulator state lives in memory and is not HA. |
| `preset.name` | `""` | One of `development`, `production`, `enterprise`, `microservices`, `multi-tier`, `stress-test`, `empty`. |
| `customPreset.enabled` | `false` | Mount your own preset YAML via ConfigMap. Overrides `preset.name`. |
| `customPreset.yaml` | `""` | Inline preset YAML body. |
| `logLevel` | `info` | `debug`, `info`, `warning`, `error`. |
| `persistence.enabled` | `false` | When on, mounts a PVC and passes `--persist-db`. |
| `persistence.size` | `1Gi` | |
| `persistence.path` | `/data/emulator-db.json` | Mount dir is derived from this. |
| `persistence.autoSave` | `true` | Adds `--auto-save`. |
| `service.type` | `ClusterIP` | All 9 emulator ports exposed. |
| `ingress.enabled` | `false` | Disabled by default — admin credentials are static. |
| `gatewayApi.enabled` | `false` | Optional `gateway.networking.k8s.io/v1` HTTPRoute. Off for the same reason as `ingress`. |
| `gatewayApi.createGateway` | `false` | When `true`, the chart renders a `Gateway` alongside the HTTPRoute (useful in kind / throwaway envs). When `false`, set `gatewayApi.parentRefs` to attach to an existing Gateway. |
| `gatewayApi.gateway.gatewayClassName` | `""` | Required when `createGateway: true`. e.g. `envoy`, `istio`, `cilium`. |
| `resources` | 50m/128Mi → 500m/384Mi | Right-sized for the demo case. |
| `probes.{liveness,readiness}` | Enabled, hit `/health` on port 5000 | |
| `extraArgs` | `[]` | Appended verbatim to the container args. |

## Limitations

- Single replica only — multi-replica deployments cause incoherent state.
- Admin credentials are baked into the image (`emulator/core/database.py`); the chart does not pretend otherwise.
- Do not enable `ingress` without an authenticating proxy in front. Static admin/password on the public internet is a credential leak by design.
- Persistence is a single JSON file; switching emulator versions may break the on-disk schema.

## See also

- [`../../docs/kubernetes.md`](../../docs/kubernetes.md) — Full deployment + Waldur integration guide.
- [`../../docs/scenarios.md`](../../docs/scenarios.md) — Failure injection API on port 8999.
- [`../../README.md`](../../README.md) — Emulator overview, OS_* env vars, CLI flags.
