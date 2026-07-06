# Site input worksheet

Collect these values before editing `config/stack.json`. Do not invent values merely to pass validation.

| Input | Where it comes from | Confirmed? |
|---|---|---|
| RHEL VM FQDN (`hostname -f`) | Existing VM/DNS record | [ ] |
| Credential-free proxy URL | Network team | [ ] |
| Optional additional `NO_PROXY` suffixes | Network team/current approved host settings | [ ] |
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
- Resource limits for the planned 8-vCPU/24-GiB POC VM with at least 100 GiB free under `/data`.
- PKI filenames under `/data/elk-poc/pki`.

Run `bin/elkctl config-check` after entering the VM FQDN and proxy settings. `PENDING` PKI files may be installed next; configuration failures must be corrected first.
