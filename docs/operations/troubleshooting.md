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

## Agent has no host data

Check Agent logs and SELinux denials:

```bash
sudo ausearch -m AVC,USER_AVC -ts recent
```

Do not disable SELinux or relabel system directories. Record the denial and create only the narrowly scoped policy required by the actual access.
