# Minimal single-node Elastic Stack POC

This repository deploys Elastic Stack **9.4.2** on one RHEL 9 VM with rootful Podman 5 Quadlets. It is deliberately limited to four containers:

1. Elasticsearch
2. Kibana
3. Fleet Server
4. A Fleet-managed Elastic Agent that collects RHEL system metrics and journal logs

The objective is to demonstrate searchable host telemetry, Fleet management, and Kibana dashboards—not to provide a production platform. The VM and its disk remain a single failure domain.

## What the POC demonstrates

```text
RHEL metrics and journals
          |
          v
  Elastic Agent ---> Fleet Server
          |                |
          +-------> Elasticsearch <------ Kibana
```

- CPU, memory, disk, load, network, and uptime metrics.
- RHEL journal and common system log events.
- Agent health and policy management in Fleet.
- Search, Discover, and System integration dashboards in Kibana.
- Corporate TLS and outbound proxy compatibility.

## Start here

Follow the [first deployment walkthrough](docs/getting-started/first-deployment.md). It assumes no prior Elastic experience.

Supporting guides:

- [Manual GitLab transfer](docs/getting-started/gitlab-transfer.md)
- [Site inputs](docs/getting-started/site-input-worksheet.md)
- [PKI](docs/security-and-network/pki.md)
- [Network and proxy](docs/security-and-network/network-proxy.md)
- [Troubleshooting](docs/operations/troubleshooting.md)
- [POC acceptance](docs/operations/acceptance-checklist.md)
- [Deferred production work](docs/future-production.md)

## Prerequisites

- x86-64 RHEL 9 with systemd and cgroup v2.
- Rootful Podman major version 5.
- Python 3.13 from the approved Enterprise Software Center.
- No third-party Python packages; do not run `pip install` for this project.
- SELinux enforcing.
- `curl` and OpenSSL.
- The planned POC VM profile: 8 vCPU, 24 GiB RAM, and at least 100 GiB free under `/data`.
- The RHEL VM's existing fully qualified hostname, resolvable from operator workstations.
- Corporate service certificates and the proxy interception CA.

## Minimal site configuration

Copy the example:

```bash
cp config/stack.example.json config/stack.json
vi config/stack.json
```

Only the VM FQDN and proxy settings normally need to change:

```json
{
  "$schema": "./schema/stack.schema.json",
  "hostFqdn": "servername.us.company.com",
  "proxy": {
    "url": "http://proxy.us.company.com:80",
    "noProxy": [".company.com", ".local"]
  }
}
```

The same hostname serves Elasticsearch on 9200, Kibana on 5601, and Fleet Server on 8220. Set `proxy` to `null` only when the VM has approved direct access. Podman chooses the private container subnet automatically. Ports, images, memory ceilings, Fleet IDs, and integration versions are internal defaults.

## Required PKI filenames

Place these supplied files under `/data/elk-poc/pki`:

```text
service-ca-chain.pem
proxy-ca-chain.pem
elasticsearch.crt
elasticsearch.key
kibana.crt
kibana.key
fleet-server.crt
fleet-server.key
```

Each service certificate must contain the configured `hostFqdn` as a DNS SAN. Elasticsearch uses its certificate for both HTTP and single-node transport TLS, so that certificate must permit both TLS server and client authentication. Private keys must be unencrypted PEM and mode `0600`.

## Commands

```bash
bin/elkctl config-check
sudo bin/elkctl preflight
sudo bin/elkctl plan
sudo bin/elkctl deploy
sudo bin/elkctl status
sudo bin/elkctl logs elasticsearch
sudo bin/elkctl logs kibana
sudo bin/elkctl logs fleet-server
sudo bin/elkctl logs agent
sudo bin/elkctl restart
sudo bin/elkctl stop
sudo bin/elkctl start
sudo bin/elkctl destroy
```

`destroy` removes services while preserving data, supplied PKI, and generated secrets.

## Security boundaries

- HTTPS is required on Elasticsearch, Kibana, and Fleet Server.
- Generated secrets enter containers through Podman secret mounts or Kibana keystore entries.
- The Podman socket is not mounted.
- Containers are not privileged.
- Elasticsearch transport port 9300 is not published.
- The framework never disables SELinux or uses insecure TLS flags.
- The framework reports firewall state but never changes firewall rules.

## Repository layout

```text
bin/elkctl          Python 3.13 launcher
src/elkctl/         Controller implementation
config/             Minimal example, schema, and integration lock
deploy/             Quadlet and Elastic/Fleet templates
docs/               First-deployment and troubleshooting guidance
tests/              Focused offline tests
```

Generated `config/stack.json`, `pki/`, `secrets/`, and `runtime/` are ignored by Git.
