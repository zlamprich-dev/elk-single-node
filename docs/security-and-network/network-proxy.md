# Network and proxy

## Required DNS

Three aliases resolve to the same RHEL VM and match the service certificates:

```text
Elasticsearch FQDN
Kibana FQDN
Fleet Server FQDN
```

Podman assigns the private bridge subnet automatically. The operator does not select container IP addresses.

## Required flows

| Source | Destination | Port | Purpose |
|---|---|---:|---|
| Administrator workstation | Kibana FQDN | 5601 | Browser and API |
| Agent network | Fleet Server FQDN | 8220 | Enrollment and policy |
| Agent network | Elasticsearch FQDN | 9200 | Telemetry output |
| RHEL VM through proxy | `docker.elastic.co` | 443 | Images |
| RHEL VM through proxy | `epr.elastic.co` | 443 | Integrations |
| RHEL VM/Agent through proxy | `artifacts.elastic.co` | 443 | Agent components |

Port 9300 is not an administrator or Agent endpoint and must not be published.

## Proxy trust

`config/stack.json` contains only the credential-free proxy URL. Store its CA chain as:

```text
/data/elk-poc/pki/proxy-ca-chain.pem
```

Install that CA into RHEL host trust through the approved corporate process so rootful Podman can pull images. The framework separately mounts the same CA for Kibana and Agent outbound connections.

The service FQDNs and loopback addresses are automatically added to `NO_PROXY`.

## Firewall ownership

The framework reports `firewalld` state but does not change it. Do not disable the firewall merely to make the POC work.
