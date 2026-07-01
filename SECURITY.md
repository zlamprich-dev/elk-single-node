# Security model

## Protected assets

- `config/stack.json` contains no credentials.
- `secrets/`, `pki/`, and `runtime/` are Git-ignored.
- Generated secret files are mode 0600; secret directories are mode 0700.
- Runtime API calls use an in-process HTTPS client so passwords are not placed in command arguments.
- Kibana runtime credentials and encryption keys are stored in `kibana.keystore`.
- Fleet service and enrollment tokens enter containers through Podman secret mounts.

## Deliberate exclusions

- No privileged containers.
- No Podman API socket in Elastic Agent.
- No plaintext HTTP endpoints.
- No `--insecure` enrollment.
- No published Elasticsearch transport port.
- No automatic image or Agent upgrades.
- No automatic changes to host or corporate firewall policy.

## Reporting

Do not attach `secrets/`, `pki/`, `podman inspect` output, or unredacted debug logs to issues. Rotate any token or password that may have been disclosed.
