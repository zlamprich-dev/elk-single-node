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

## A service fails

Inspect its journal with `elkctl logs`. Work in dependency order:

1. Elasticsearch
2. Kibana
3. Fleet Server
4. Local Agent

Do not troubleshoot Fleet while Elasticsearch or Kibana is unhealthy.

## Agent has no host data

Check Agent logs and SELinux denials:

```bash
sudo ausearch -m AVC,USER_AVC -ts recent
```

Do not disable SELinux or relabel system directories. Record the denial and create only the narrowly scoped policy required by the actual access.
