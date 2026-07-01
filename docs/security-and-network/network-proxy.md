# Network and proxy

## Required DNS

Use the RHEL VM's existing fully qualified hostname. It must have an IPv4 address because this POC publishes its service ports on the VM's IPv4 interfaces:

```text
servername.us.company.com
```

The same hostname addresses three HTTPS services by port. Podman assigns the private bridge subnet automatically, and the operator does not select container IP addresses. Containers map the configured hostname to Podman's host gateway so internal connections reach the published host ports without ambiguous shared network aliases.

## Required flows

| Source | Destination | Port | Purpose |
|---|---|---:|---|
| Administrator workstation | VM FQDN | 5601 | Kibana browser and API |
| Local Agent container | VM FQDN | 8220 | Fleet enrollment and policy |
| Kibana, Fleet, and Agent containers | VM FQDN | 9200 | Elasticsearch APIs and telemetry |
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

The VM FQDN and loopback addresses are automatically added to both `NO_PROXY` and `no_proxy`. Add corporate suffixes such as `.company.com` or `.local` through the optional `proxy.noProxy` array only when corporate policy expects those namespaces to bypass the proxy. Do not include URL schemes, commas, or spaces in individual array entries.

The framework sets `HTTP_PROXY`, `HTTPS_PROXY`, `http_proxy`, and `https_proxy` to the configured URL for compatibility across Elastic, Node.js, and command-line clients. An `http://proxy-host:80` value is valid for `HTTPS_PROXY`: the variable identifies HTTPS destination traffic, while the URL describes the HTTP CONNECT proxy itself. Quadlets set `HttpProxy=false` to prevent unrelated proxy values from the root Podman environment being inherited into containers.

## Firewall ownership

The framework reports `firewalld` state but does not change it. Do not disable the firewall merely to make the POC work.
