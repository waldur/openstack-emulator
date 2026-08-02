# Deploying the OpenStack Emulator on Kubernetes

This guide walks an operator through deploying the OpenStack Emulator into a Kubernetes cluster as a sandbox OpenStack backend that other workloads (CI runners, integration tests, demo platforms, OpenStack clients under development) can target via in-cluster DNS.

**Scope:** demo / sandbox / CI environments. The emulator ships with hardcoded admin credentials and is not safe to expose on the public internet — see [Limitations](#limitations) below.

## Prerequisites

| Tool | Tested version | Why |
|---|---|---|
| `kubectl` | 1.30+ | Talking to the cluster |
| `helm` | 3.14+ | Installing the chart |
| A running cluster | k8s 1.27+ | Anywhere from kind to a managed cloud cluster |

If your cluster denies cross-namespace traffic by default, allow it explicitly with a `NetworkPolicy` or co-locate the consumer workload with the emulator namespace.

## Step 1 — Install the chart

The chart is published to GitHub Pages, so the usual install needs no checkout:

```bash
helm repo add openstack-emulator https://waldur.github.io/openstack-emulator/
helm repo update

helm install openstack-emulator openstack-emulator/openstack-emulator \
  --namespace ose --create-namespace \
  --version 0.4.1 --wait
```

The chart version equals the emulator release tag, and `appVersion` — the image
tag the chart deploys — matches it. Omit `--version` to take the newest.

The chart source lives at [`charts/openstack-emulator/`](../charts/openstack-emulator) in this repo; to install an unreleased change, clone and install from disk instead:

```bash
git clone https://code.opennodecloud.com/waldur/openstack-emulator.git
cd openstack-emulator

helm install openstack-emulator ./charts/openstack-emulator \
  --namespace ose --create-namespace \
  --wait
```

Once the rollout completes, Helm prints the in-cluster URLs and credentials. Confirm the chart with its bundled health check:

```bash
helm test openstack-emulator -n ose
```

`helm test` runs a one-shot Pod that hits `/health` on Keystone (5000), Nova (8774), Glance (9292), Neutron (9696), and Cinder (8776). All five must return `{"status":"healthy",...}` for the test to pass.

### Useful variants

```bash
# Seed a richer set of sample resources at startup.
helm install openstack-emulator ./charts/openstack-emulator \
  --namespace ose --create-namespace \
  --set preset.name=development

# Survive pod restarts by writing to a PVC.
helm install openstack-emulator ./charts/openstack-emulator \
  --namespace ose --create-namespace \
  --set persistence.enabled=true --set persistence.size=2Gi

# Mount a custom preset YAML from disk.
helm install openstack-emulator ./charts/openstack-emulator \
  --namespace ose --create-namespace \
  --set customPreset.enabled=true \
  --set-file customPreset.yaml=./my-preset.yaml
```

Built-in preset names: `development`, `production`, `enterprise`, `microservices`, `multi-tier`, `stress-test`, `waldur-site-agent`, `empty`. `waldur-site-agent` additionally seeds federated identity — see [federation.md](federation.md). See [`emulator/presets/`](../emulator/presets) for the YAML schema (each file starts with `name:` and `description:`, followed by per-service resource lists).

## Step 2 — Smoke-test the emulator from your laptop

Port-forward Keystone and run a token request as the hardcoded `admin` user:

```bash
kubectl -n ose port-forward svc/openstack-emulator 5000:5000 &

curl -s http://localhost:5000/health
# {"status":"healthy","service":"keystone"}

curl -s -X POST http://localhost:5000/v3/auth/tokens \
  -H 'Content-Type: application/json' \
  -d '{
    "auth": {
      "identity": {
        "methods": ["password"],
        "password": {"user": {"name": "admin", "domain": {"name": "Default"}, "password": "s4l4dus"}}
      },
      "scope": {"project": {"name": "admin", "domain": {"name": "Default"}}}
    }
  }' -D - -o /dev/null | grep -i x-subject-token
# x-subject-token: <uuid>
```

The OpenStack CLI works too:

```bash
export OS_AUTH_URL=http://localhost:5000/v3
export OS_PROJECT_NAME=admin
export OS_USERNAME=admin
export OS_PASSWORD=s4l4dus
export OS_USER_DOMAIN_NAME=Default
export OS_PROJECT_DOMAIN_NAME=Default
export OS_IDENTITY_API_VERSION=3

openstack project list
openstack network list
```

(Stop the port-forward with `kill %1` when you're done.)

## Step 3 — Use the in-cluster endpoint from another workload

Other workloads reach the emulator via in-cluster DNS:

```text
http://openstack-emulator.<emulator-namespace>.svc.cluster.local:5000/v3
```

Substitute the namespace you installed into (e.g. `ose`). If your release name differs from the chart name, the Service name becomes `<release>-openstack-emulator` — `kubectl get svc -n <ns>` always shows the real name.

All twelve emulator ports are exposed on that one Service; the emulator binds them from a single process, so individual services cannot be disabled:

| Port | Service | Port | Service |
|---|---|---|---|
| 5000 | Keystone | 8080 | Swift |
| 8774 | Nova | 5556 | OIDC provider |
| 8776 | Cinder | 8889 | CloudKitty |
| 9292 | Glance | 8778 | Placement |
| 9696 | Neutron | 10000 | Status UI |
| 9876 | Octavia | 8999 | Scenarios |

In practice consumers only need Keystone — clients follow the service catalog, which the emulator builds from the request's `Host` header (see [Service catalog follows the request hostname](#service-catalog-follows-the-request-hostname)).

A consumer Pod sets the standard `OS_*` env block to that URL and uses the hardcoded admin credentials:

```yaml
env:
  - name: OS_AUTH_URL
    value: http://openstack-emulator.ose.svc.cluster.local:5000/v3
  - name: OS_USERNAME
    value: admin
  - name: OS_PASSWORD
    value: s4l4dus
  - name: OS_PROJECT_NAME
    value: admin
  - name: OS_USER_DOMAIN_NAME
    value: Default
  - name: OS_PROJECT_DOMAIN_NAME
    value: Default
  - name: OS_IDENTITY_API_VERSION
    value: "3"
```

Sanity check from a throwaway pod *in a different namespace* (simulates the consumer):

```bash
kubectl create ns consumer
kubectl run -n consumer curlcheck --restart=Never \
  --image=curlimages/curl:8.10.1 --command -- \
  sh -c 'curl -fsS http://openstack-emulator.ose.svc.cluster.local:5000/health'

kubectl -n consumer logs curlcheck
# {"status":"healthy","service":"keystone"}

kubectl -n consumer delete pod curlcheck
kubectl delete ns consumer
```

If this returns anything other than `"healthy"`, fix the URL before pointing real consumers at it.

### Service catalog follows the request hostname

The emulator's Keystone derives the service-catalog endpoint URLs from the request's `Host` header — so a token request to `http://openstack-emulator.ose.svc.cluster.local:5000/v3/auth/tokens` returns catalog entries like `http://openstack-emulator.ose.svc.cluster.local:8774/v2.1` (Nova), `http://openstack-emulator.ose.svc.cluster.local:9696` (Neutron), and so on. OpenStack clients (`openstacksdk`, `python-novaclient`, etc.) that follow the catalog therefore work without any extra configuration once they reach Keystone via the in-cluster Service DNS.

## Step 4 (optional) — Expose externally

The Status UI lives on port 10000 and is convenient for poking at emulator state during a demo. The chart supports either Ingress or Gateway API; pick whichever your cluster already runs. **Only expose on a trusted network** — the emulator's hardcoded admin credentials are still in play.

### Option A: Ingress (`networking.k8s.io/v1`)

```bash
helm upgrade openstack-emulator ./charts/openstack-emulator \
  -n ose --reuse-values \
  --set ingress.enabled=true \
  --set 'ingress.hosts[0].host=ose.example.com' \
  --set 'ingress.hosts[0].paths[0].path=/' \
  --set 'ingress.hosts[0].paths[0].pathType=Prefix' \
  --set 'ingress.hosts[0].paths[0].port=10000'
```

Each host in `ingress.hosts` targets a single emulator port — repeat the block to expose more than one (e.g. Keystone on port 5000 too). Add `ingress.className`, `ingress.annotations`, and `ingress.tls` to suit your ingress controller and cert-manager setup.

### Option B: Gateway API (`gateway.networking.k8s.io/v1`)

The chart can either attach an HTTPRoute to a Gateway you already operate, or render its own Gateway for self-contained envs.

**With an existing shared Gateway** (most production setups):

```bash
helm upgrade openstack-emulator ./charts/openstack-emulator \
  -n ose --reuse-values \
  --set gatewayApi.enabled=true \
  --set 'gatewayApi.parentRefs[0].name=shared-gateway' \
  --set 'gatewayApi.parentRefs[0].namespace=gateway-system' \
  --set 'gatewayApi.hostnames[0]=ose.example.com' \
  --set 'gatewayApi.rules[0].matches[0].path.type=PathPrefix' \
  --set 'gatewayApi.rules[0].matches[0].path.value=/' \
  --set 'gatewayApi.rules[0].port=10000'
```

**Self-contained Gateway** (kind, throwaway test envs — needs a Gateway API controller installed for the `gatewayClassName` you pick):

```bash
helm upgrade openstack-emulator ./charts/openstack-emulator \
  -n ose --reuse-values \
  --set gatewayApi.enabled=true \
  --set gatewayApi.createGateway=true \
  --set gatewayApi.gateway.gatewayClassName=envoy \
  --set 'gatewayApi.hostnames[0]=ose.example.com' \
  --set 'gatewayApi.rules[0].matches[0].path.type=PathPrefix' \
  --set 'gatewayApi.rules[0].matches[0].path.value=/' \
  --set 'gatewayApi.rules[0].port=10000'
```

Prerequisite for either Gateway API path: the standard Gateway API CRDs must already be installed in the cluster:

```bash
kubectl apply -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.2.0/standard-install.yaml
```

Without those CRDs, `helm upgrade` will fail to apply the `Gateway`/`HTTPRoute` objects.

## Step 5 (optional) — Failure injection

The emulator ships a Scenarios API on port 8999 that injects HTTP failures into selected endpoints — useful for testing consumer error paths. Reach it the same way as any other emulator port:

```text
http://openstack-emulator.<ns>.svc.cluster.local:8999
```

See [`docs/scenarios.md`](scenarios.md) for the API.

## Uninstall

```bash
helm uninstall openstack-emulator -n ose
kubectl delete ns ose       # also removes the PVC if persistence was enabled
```

If you only `helm uninstall` and keep the namespace, the PVC stays — delete it manually with `kubectl -n ose delete pvc -l app.kubernetes.io/instance=openstack-emulator` to reclaim disk.

## Limitations

- **Single replica only.** Emulator state is in memory; running two pods produces two diverging realities. The chart hard-codes `replicaCount: 1`.
- **Hardcoded credentials.** `admin` / `s4l4dus`, project `admin`, domain `Default` — not configurable, see [`emulator/core/database.py`](../emulator/core/database.py). Do not expose the Service publicly without an authenticating proxy.
- **Persisted state is versioned, but only rolls forward.** The on-disk JSON carries a `schema_version`. A file written by an older emulator is read through a compatibility path and rewritten in the current format on the next save, so upgrading the image over an existing PVC is safe. Downgrading is not: an older image will not understand a newer file. Records that cannot be read are skipped and logged, and the original file is copied to `<path>.corrupt-<timestamp>` before it is replaced.
- **ConfigMap updates don't restart the pod.** If you change `customPreset.yaml` after install, `helm upgrade` updates the ConfigMap but the running pod keeps the old preset. Force a restart with `kubectl -n ose rollout restart deploy/openstack-emulator` to pick up the new content.
- **Not a substitute for real OpenStack.** The emulator implements *enough* of each API for typical client flows; many operations (e.g. live migration, real block storage attach) are stubs that return success without doing anything.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `helm test` Pod fails with `connection refused` | Pod still starting up | Re-run `helm test` after `kubectl -n ose wait --for=condition=available deploy/openstack-emulator --timeout=120s` |
| Consumer can't resolve the emulator URL | Wrong namespace in the URL | `kubectl get svc -A` to find the actual Service, then rebuild the URL as `<svc>.<ns>.svc.cluster.local:5000/v3` |
| Pod `CrashLoopBackOff` with `Failed to load preset` | `customPreset.yaml` missing required `name:` / `description:` top-level fields | Mirror one of the files in [`emulator/presets/`](../emulator/presets); update the value; `helm upgrade`; `kubectl rollout restart` |
| `helm install` times out at "wait for deployment" | Image pull failed (typo in tag or registry not reachable) | `kubectl -n ose describe pod` — fix the image reference and `helm upgrade` |
| OpenStack client can reach Keystone but other services fail | Client cached an older catalog from before in-cluster install | Re-authenticate (request a new token); the catalog will pick up the current `Host` header |
| `helm upgrade` errors on Gateway/HTTPRoute "no matches for kind" | Gateway API CRDs not installed | `kubectl apply -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.2.0/standard-install.yaml`, then re-run the upgrade |
| `Gateway` shows `PROGRAMMED: Unknown` indefinitely | No Gateway API controller in the cluster for the picked `gatewayClassName` | Install a controller (Envoy Gateway, Istio, Cilium…) or change `gatewayClassName` to one already present |

## See also

- [`../README.md`](../README.md) — Emulator overview, CLI flags, OS_* env block.
- [`../charts/openstack-emulator/README.md`](../charts/openstack-emulator/README.md) — Chart values reference.
- [`scenarios.md`](scenarios.md) — Failure injection API.
- [`architecture/`](architecture/) — Emulator internals.
