# First deployment walkthrough

## 1. Install the prerequisites

Confirm Python and Podman:

```bash
python3.13 --version
podman version
getenforce
```

Expected: Python 3.13, Podman 5, and `Enforcing`.

## 2. Clone into the final location

```bash
sudo install -d -m 0750 -o "$USER" -g "$(id -gn)" /data/elk-poc
git clone <enterprise-gitlab-url> /data/elk-poc
cd /data/elk-poc
chmod +x bin/elkctl tests/run.sh deploy/scripts/agent-secret-entrypoint.sh
```

## 3. Enter the site configuration

Complete the [site input worksheet](site-input-worksheet.md). For a new deployment, create the local configuration:

```bash
cp config/stack.example.json config/stack.json
vi config/stack.json
bin/elkctl config-check
```

Expected: configuration passes and only not-yet-installed PKI files are `PENDING`.

If this checkout previously used a `services` block containing three FQDNs, do not run the preceding copy command first. `git pull` does not replace the ignored `config/stack.json`. Back it up, copy the new example, and enter the VM hostname and proxy again:

```bash
cp config/stack.json config/stack.json.before-host-fqdn
cp config/stack.example.json config/stack.json
vi config/stack.json
bin/elkctl config-check
```

## 4. Install the PKI files

Follow the [PKI guide](../security-and-network/pki.md), using the exact filenames listed in the README. Then protect them:

```bash
sudo chown -R root:root /data/elk-poc/pki
sudo chmod 0700 /data/elk-poc/pki
sudo chmod 0644 /data/elk-poc/pki/*.crt /data/elk-poc/pki/*.pem
sudo chmod 0600 /data/elk-poc/pki/*.key
```

## 5. Run read-only validation

```bash
sudo bin/elkctl preflight
```

Expected ending:

```text
[SUMMARY] failures=0 warnings=<number>
```

Do not deploy while failures remain. Warnings include context and may be reviewed individually.

## 6. Review and deploy

```bash
sudo bin/elkctl plan
sudo bin/elkctl deploy
```

Deployment starts Elasticsearch, Kibana, Fleet Server, and the local Agent in dependency order. The command is rerunnable after an interruption.

## 7. Verify the POC

```bash
sudo bin/elkctl status
```

Browse to `https://<hostFqdn>:5601`. Use the initial administrator password stored in `secrets/elastic-password` only through an approved handling method.

In Kibana:

1. Open **Management → Fleet → Agents** and confirm the local Agent is healthy.
2. Open **Discover** and look for `logs-*` data streams.
3. Open the System integration dashboards and confirm CPU, memory, load, disk, and network data.

## 8. Verify restart behavior

```bash
sudo bin/elkctl restart
sudo bin/elkctl status
```

The Agent should remain enrolled because its state directory is persistent.
