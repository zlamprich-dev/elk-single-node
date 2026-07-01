# Site input worksheet

Collect these values before editing `config/stack.json`. Do not invent values merely to pass validation.

| Input | Where it comes from | Confirmed? |
|---|---|---|
| Elasticsearch FQDN | DNS/PKI team | [ ] |
| Kibana FQDN | DNS/PKI team | [ ] |
| Fleet Server FQDN | DNS/PKI team | [ ] |
| Credential-free proxy URL | Network team | [ ] |
| Proxy CA chain | PKI/security team | [ ] |
| Service CA chain | PKI team | [ ] |
| Elasticsearch certificate/key | PKI team | [ ] |
| Kibana certificate/key | PKI team | [ ] |
| Fleet Server certificate/key | PKI team | [ ] |
| Inbound ports 5601, 8220, and 9200 approved | Network/security team | [ ] |

The framework already defines:

- Elastic Stack version 9.4.2.
- Official Elastic image repositories.
- Ports 9200, 5601, and 8220.
- Automatic Podman subnet allocation.
- Fleet policy IDs and integration versions.
- Resource limits for the planned 8-vCPU/32-GiB VM.
- PKI filenames under `/data/elk-poc/pki`.

Run `bin/elkctl config-check` after entering the FQDNs and proxy URL. `PENDING` PKI files may be installed next; configuration failures must be corrected first.
