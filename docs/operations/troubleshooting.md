# Troubleshooting

Use this order; do not delete data and start over unless the cause is understood.

## Standard checks

```bash
sudo bin/elkctl status
sudo systemctl --failed
sudo podman ps -a
sudo bin/elkctl logs elasticsearch
sudo bin/elkctl logs kibana
sudo bin/elkctl logs fleet-server
sudo bin/elkctl logs agent
```

## Configuration fails

Run:

```bash
bin/elkctl config-check
```

Replace all `example.corp` values. Proxy credentials must never be embedded in the URL.

## DNS fails

```bash
hostname -f
getent ahosts <hostFqdn>
```

The configured hostname must resolve to the RHEL VM and appear in all three service certificates' SANs.

## A container cannot reach the shared hostname

The generated Kibana, Fleet Server, and Agent Quadlets contain:

```text
AddHost=<hostFqdn>:host-gateway
```

Inspect the rendered unit and the container's host mapping:

```bash
sudo grep AddHost runtime/config/elk-poc-*.container
sudo podman exec elk-poc-kibana getent hosts <hostFqdn>
```

If Podman cannot determine `host-gateway`, review the rootful Podman network configuration with the RHEL administrator rather than substituting an invented static address.

## Registry or package access fails

Confirm the proxy URL, install the proxy interception CA through the approved RHEL trust process, and follow the [network/proxy guide](../security-and-network/network-proxy.md).

## Certificate validation fails

Use the [PKI guide](../security-and-network/pki.md). Common causes are a missing intermediate, wrong SAN, mismatched key, expired certificate, or missing client-authentication EKU on the Elasticsearch certificate.

## Common preflight findings

Do not deploy while preflight reports failures. Warnings require review but do not, by themselves, prevent deployment.

### SELinux is permissive

This framework requires SELinux to remain enforcing. When policy is loaded but the current mode is `Permissive`, inspect and enable it with:

```bash
getenforce
sestatus
grep '^SELINUX=' /etc/selinux/config
sudo setenforce 1
getenforce
sudoedit /etc/selinux/config
```

Set `SELINUX=enforcing` in `/etc/selinux/config`; do not change `SELINUXTYPE`. If corporate policy prevents this change, stop and contact the RHEL or security owner. After attempting deployment, inspect denials with:

```bash
sudo ausearch -m AVC,USER_AVC -ts recent
```

Do not disable SELinux to work around a container error.

### A required port is already occupied

Identify the listener before stopping anything. For Fleet Server port 8220:

```bash
sudo ss -ltnp 'sport = :8220'
sudo podman ps --format 'table {{.ID}}\t{{.Names}}\t{{.Ports}}\t{{.Status}}'
sudo systemctl list-units --type=service --all | grep -Ei 'elastic|fleet|podman'
```

Inspect the reported process, unit, or container. Stop it only after confirming that it is an obsolete deployment. Do not kill an unidentified process. Rerun the `ss` command; no output means the port is available.

### The VM reports insufficient memory or disk

The default POC profile requires 8 logical CPUs, 24 GiB RAM, and 100 GiB free on the filesystem containing `/data/elk-poc`. Its container memory ceilings total 19 GiB: 12 GiB for Elasticsearch, 3 GiB for Kibana, and 2 GiB each for Fleet Server and the monitoring Agent. The remaining memory is reserved for RHEL, Podman, and filesystem cache.

Do not lower these checks merely to make preflight pass. Increase the VM resources or reduce the workload only after measuring actual use. Check current capacity with:

```bash
free -h
df -h /data/elk-poc
```

### Swap is active

Inspect rather than immediately disabling it:

```bash
swapon --show
free -h
```

This is a warning for the POC. After deployment, use `sudo podman stats --no-stream` to confirm the containers remain within their limits. If normal operation consumes swap, reduce the workload or add memory. Coordinate any `/etc/fstab` change with the VM owner.

### `vm.max_map_count` is below 1048576

`elkctl deploy` persists and applies the required setting automatically. To apply it before deployment, create `/etc/sysctl.d/90-elk-poc.conf` containing:

```text
vm.max_map_count=1048576
```

Then run:

```bash
sudo sysctl --system
sysctl vm.max_map_count
```

### firewalld is inactive

Confirm whether this is intentional with the RHEL or network owner:

```bash
sudo systemctl status firewalld
```

Do not blindly enable firewalld on a remote VM because an incomplete ruleset can terminate SSH access. The deployment needs approved inbound TCP access to 5601, 8220, and 9200, preferably restricted to approved source networks. The framework reports firewall state but intentionally does not change firewall rules.

### Elastic artifact access is not confirmed

Test the same small versioned checksum file used by preflight:

```bash
curl --fail --silent --show-error --output /dev/null \
  https://artifacts.elastic.co/downloads/beats/elastic-agent/elastic-agent-9.4.2-linux-x86_64.tar.gz.sha512
echo $?
```

Exit status `0` means it succeeded. If the shell does not already have approved proxy variables, add `--proxy <proxy-url>` and `--cacert /data/elk-poc/pki/proxy-ca-chain.pem`. Do not place proxy credentials in the URL.

## A service fails

Inspect its journal with `elkctl logs`. Work in dependency order:

1. Elasticsearch
2. Kibana
3. Fleet Server
4. Local Agent

Do not troubleshoot Fleet while Elasticsearch or Kibana is unhealthy.

## systemd says a Quadlet service is transient or generated

Quadlet creates generated `.service` units, so `systemctl enable` and
`systemctl disable` are invalid for them. Boot activation comes from the
`[Install]` section in each `.container` source file. Manage the generated
services with `systemctl start`, `stop`, or `restart`.

If an older controller version fails while trying to enable a generated unit,
pull the corrected repository and rerun `sudo bin/elkctl deploy`. Deployment is
convergent: existing protected secrets, rendered files, and downloaded images
are reused.

## Elasticsearch rejects `elastic_password` mode 0444

Podman secret mounts default to mode `0444`, but Elasticsearch rejects password
files readable by other users. Current Quadlet templates mount the Elasticsearch
password as UID 1000 with mode `0400`; Fleet and Agent secrets also use mode
`0400`.

If an older rendered unit is restarting with this error, stop that unit, pull
the corrected repository, and rerun deployment. The Podman secret itself does
not need to be deleted or recreated because ownership and mode are consumer
mount options in the Quadlet definition.

## Elasticsearch reports `elasticsearch.keystore: Device or resource busy`

Elasticsearch updates its keystore by creating `elasticsearch.keystore.tmp` and
atomically replacing the original file. A directly bind-mounted keystore cannot
be replaced. The current POC does not add custom secure settings to that
keystore, so it uses the image's automatically generated keystore and does not
bind-mount a host keystore file. The bootstrap password remains protected in a
mode-`0400` Podman secret.

If an older unit is restarting with this error, stop it, pull the corrected
repository, and rerun deployment. An old
`runtime/config/elasticsearch/elasticsearch.keystore` file may remain on the
host, but it is no longer mounted and does not need to be deleted.

## Kibana reports an encryption-key length of zero

Kibana JSON-parses values supplied to `kibana-keystore add --stdin`. The
controller therefore sends every value as a JSON-encoded string followed by a
newline, runs the temporary Podman container with `--interactive` so the pipe is
connected to container stdin, and validates that each encryption key contains
at least 32 characters before updating the keystore. Without `--interactive`,
Podman starts the command with empty stdin even though the host process supplied
input.

After pulling this correction, rerun deployment. The controller uses `--force`
to replace the empty keystore entries with the existing protected secret-file
values; do not delete or regenerate those secret files.

## Fleet rejects `Variable system-system/metrics:[system.hostfs] not found`

System integration 2.20.0 defines the input variable as `system.hostfs`. Square
brackets are part of the simplified API's stream-selector keys, but they must
not be added to variable names. The current System package-policy template uses
the exact variable name and sets it to `/hostfs` for the containerized Agent.

This HTTP 400 response occurs before Fleet creates the package policy. Pull the
corrected template and rerun deployment; no Fleet object or secret needs to be
removed.

The same rule applies to stream selectors: use exact package stream names such
as `system.core`, not `[system.core]`. The locked payloads have also been audited
for their input shapes. System logs use the `system-logfile` input with
`system.auth` and `system.syslog` streams. Journald 1.2.1 uses the
`logs-journald` input and does not define a synthetic stream block.

## Fleet rejects `Variable logs-journald: paths not found`

Journald 1.2.1 is an input package and is explicitly licensed for Basic. Its
`paths` and `include_matches` settings are optional, but mapping those variables
through Fleet's simplified package-policy selector proved version-sensitive.

The POC does not need custom journal filtering, so its package policy now
enables the input without overriding optional variables. The Agent Quadlet
bind-mounts the host's `/var/log`, `/run/log/journal`, and `/etc/machine-id` at
the same standard paths inside the container. Journald therefore uses its
documented system-journal defaults. Separate `/hostfs` mounts remain available
to the System integration.

Pull the correction and rerun `sudo bin/elkctl deploy`. The rejected HTTP 400
request does not create the Journald package policy, so no Fleet objects, data,
or secrets need to be removed.

## Fleet reports that `elk-poc-local-rhel` was not found

Before creating any package policy, the controller checks both framework
agent-policy IDs using the supported Fleet API and creates only a missing
policy. Existing policies are preserved. Pull the correction and rerun
deployment; do not delete Fleet saved objects or Elasticsearch data.

## Fleet says the Fleet Server policy is hosted or externally managed

In Fleet, `is_managed: true` means an external orchestrator such as Elastic
Cloud or ECK owns the policy. Fleet deliberately blocks package-policy changes
through the normal API for such a policy. It does **not** mean the policy is an
ordinary Fleet-managed policy.

The controller must add the Fleet Server integration, so it now creates both
framework policies as ordinary API-managed policies (`is_managed: false`). The
Kibana startup configuration defines Fleet hosts, outputs, and pinned packages,
but does not also declare the policies. This gives each policy one owner and
avoids a race or ownership conflict between Kibana preconfiguration and the
controller.

Pull the correction and rerun `sudo bin/elkctl deploy`. Deployment rewrites the
rendered Kibana configuration and restarts Kibana before reconciling Fleet. If
the failed attempt left a hosted policy with the framework's exact ID and zero
enrolled agents, the controller removes that stale policy through Fleet's
documented delete API and recreates it. It refuses this migration when the
policy has an enrolled agent, because deleting it could orphan that agent. Do
not delete Elasticsearch data, secrets, or Agent state before retrying.

## Fleet setup returns HTTP 503 because license information is unavailable

Kibana can answer HTTPS requests while still reporting a degraded state and
waiting for Elasticsearch-backed services such as licensing. Starting Fleet at
that point can return `License information could not be obtained from
Elasticsearch` from the setup API.

The deployment now waits for both Kibana's overall status and its core
Elasticsearch status to be `available`. It then calls the current
`POST /api/fleet/agents/setup` endpoint, which Elastic documents as idempotent,
and retries only a temporary HTTP 503 response for up to five minutes. Other
HTTP errors remain immediate failures so configuration defects are not hidden.

Pull the correction and rerun `sudo bin/elkctl deploy`. Do not remove data,
secrets, certificates, or Fleet objects for this temporary readiness failure.

## Fleet says per-policy output assignment requires Platinum

The Basic license supports Fleet, Elastic Agent, Fleet Server, the System and
Journald integrations, and a global default Elasticsearch output. It does not
support explicitly selecting an output separately on each agent policy.

Earlier controller payloads included `data_output_id` and
`monitoring_output_id`. Although both values selected the same default
Elasticsearch output, their presence requested Fleet's licensed per-policy
output-assignment feature and caused the HTTP 400 response.

The controller now omits those fields. Both agent policies automatically
inherit `elk-poc-elasticsearch-output`, which `kibana.yml` marks as the global
default for integration data and Agent monitoring. This preserves the intended
single-cluster data flow without requiring Platinum or Enterprise.

Pull the correction and rerun `sudo bin/elkctl deploy`. No license upgrade,
trial activation, data deletion, or secret regeneration is required.

## Agent has no host data

Check Agent logs and SELinux denials:

```bash
sudo ausearch -m AVC,USER_AVC -ts recent
```

Do not disable SELinux or relabel system directories. Record the denial and create only the narrowly scoped policy required by the actual access.
