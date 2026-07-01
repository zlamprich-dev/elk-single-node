# Deployment assets

These files are inputs consumed by `elkctl`; they are not copied to the RHEL host manually.

- `quadlet/` defines the Podman network and four systemd-managed containers.
- `elasticsearch/` contains the Elasticsearch configuration template.
- `kibana/` contains the Kibana and Fleet preconfiguration template.
- `fleet/` contains framework-owned Fleet package-policy templates.
- `scripts/` contains the container entrypoint used to read mounted Podman secrets.

Templates use `@@TOKEN@@` placeholders that `src/elkctl/render.py` replaces from validated site values and internal POC defaults. Do not place secrets in these files.
