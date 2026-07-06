from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import time
from typing import Callable

from .config import StackConfig
from .constants import (
    FLEET_NAMESPACE,
    FLEET_SERVER_POLICY_ID,
    IMAGES,
    LOCAL_AGENT_POLICY_ID,
    PORTS,
    SERVICES,
)
from .errors import ElkctlError
from .http import HttpClient
from .output import log, warning
from .preflight import run_preflight
from .render import atomic_write, install_quadlets, render_all
from .runner import CommandRunner


class StackController:
    def __init__(self, config: StackConfig, runner: CommandRunner) -> None:
        self.config = config
        self.runner = runner

    def require_root(self) -> None:
        if not hasattr(os, "geteuid") or os.geteuid() != 0:
            raise ElkctlError("this command must run as root (use sudo)")

    def restart_quadlet(self, unit: str) -> None:
        """Start or restart a generated Quadlet service.

        Quadlet services are transient generator output and cannot be enabled
        with systemctl. Their source files' [Install] sections establish boot
        activation when systemd regenerates the services.
        """
        self.runner.run(["systemctl", "restart", unit])

    def secret_file(self, name: str) -> Path:
        return self.config.secrets_root / name

    def read_secret(self, name: str) -> str:
        path = self.secret_file(name)
        if not path.is_file():
            raise ElkctlError(f"required secret is missing: {path}")
        return path.read_text(encoding="utf-8").strip()

    def ensure_secret(self, name: str, bytes_of_entropy: int = 48) -> Path:
        path = self.secret_file(name)
        self.config.secrets_root.mkdir(parents=True, exist_ok=True)
        os.chmod(self.config.secrets_root, 0o700)
        if not path.is_file() or path.stat().st_size == 0:
            value = secrets.token_urlsafe(bytes_of_entropy)
            path.write_text(value, encoding="utf-8")
            os.chmod(path, 0o600)
            log(f"generated protected secret: {name}")
        elif path.stat().st_mode & 0o077:
            os.chmod(path, 0o600)
        return path

    def ensure_initial_secrets(self) -> None:
        self.ensure_secret("elastic-password", 48)
        self.ensure_secret("kibana-security-encryption-key", 32)
        self.ensure_secret("kibana-saved-objects-encryption-key", 32)
        self.ensure_secret("kibana-reporting-encryption-key", 32)

    def ensure_podman_secret(self, podman_name: str, source: Path) -> None:
        records = self.config.runtime_root / "records"
        records.mkdir(parents=True, exist_ok=True)
        record = records / f"podman-secret-{podman_name}.sha256"
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        exists = self.runner.run(["podman", "secret", "inspect", podman_name], check=False)
        if exists.returncode != 0:
            self.runner.run(["podman", "secret", "create", podman_name, source])
            record.write_text(f"{digest}\n", encoding="utf-8")
            os.chmod(record, 0o600)
            log(f"created Podman secret: {podman_name}")
        elif not record.is_file():
            raise ElkctlError(
                f"Podman secret {podman_name} exists without a framework hash record; "
                "remove it only through an approved credential-rotation procedure"
            )
        elif record.read_text(encoding="utf-8").strip() != digest:
            raise ElkctlError(
                f"source for Podman secret {podman_name} changed; explicit rotation is required"
            )

    def configure_host(self) -> None:
        destination = Path("/etc/sysctl.d/90-elk-poc.conf")
        expected = "# Managed by elkctl\nvm.max_map_count=1048576\n"
        if not destination.is_file() or destination.read_text() != expected:
            atomic_write(destination, expected, 0o644)
            self.runner.run(["sysctl", "--system"])
            log("applied Elasticsearch vm.max_map_count requirement")

    def pull_images(self) -> None:
        for name, image in IMAGES.items():
            log(f"pulling {name} image: {image}")
            self.runner.run(
                ["podman", "pull", image],
                env=self.config.proxy_environment(),
                timeout=600,
            )

    def _es_client(self) -> HttpClient:
        return HttpClient(
            self.config.runtime_root / "pki" / "service-ca-chain.pem",
            username="elastic",
            password=self.read_secret("elastic-password"),
        )

    def _kibana_client(self) -> HttpClient:
        return HttpClient(
            self.config.runtime_root / "pki" / "service-ca-chain.pem",
            username="elastic",
            password=self.read_secret("elastic-password"),
        )

    def _fleet_client(self) -> HttpClient:
        return HttpClient(self.config.runtime_root / "pki" / "service-ca-chain.pem")

    def wait_for(self, label: str, check: Callable[[], bool], attempts: int) -> None:
        for _ in range(attempts):
            try:
                if check():
                    log(f"{label} is ready")
                    return
            except ElkctlError:
                pass
            time.sleep(5)
        raise ElkctlError(f"{label} did not become ready after {attempts * 5} seconds")

    def start_elasticsearch(self) -> None:
        self.ensure_podman_secret("elk_poc_elastic_password", self.secret_file("elastic-password"))
        self.restart_quadlet("elk-poc-elasticsearch.service")

        def healthy() -> bool:
            status, payload = self._es_client().json(
                "GET",
                f"{self.config.url('elasticsearch')}/_cluster/health"
                "?wait_for_status=yellow&timeout=5s",
            )
            return status == 200 and payload.get("status") in {"yellow", "green"}

        self.wait_for("Elasticsearch", healthy, 60)

    def create_service_token(self, service: str, token_name: str, secret_name: str) -> Path:
        path = self.secret_file(secret_name)
        if path.is_file() and path.stat().st_size:
            return path
        _, payload = self._es_client().json(
            "POST",
            f"{self.config.url('elasticsearch')}/_security/service/"
            f"{service}/credential/token/{token_name}",
        )
        try:
            value = payload["token"]["value"]
        except (KeyError, TypeError) as exc:
            raise ElkctlError(f"Elasticsearch did not return the {service} service token") from exc
        path.write_text(value, encoding="utf-8")
        os.chmod(path, 0o600)
        log(f"created protected service token: {service}/{token_name}")
        return path

    def _kibana_keystore(self, *arguments: str, input_text: str | None = None) -> None:
        config_dir = self.config.runtime_root / "config" / "kibana"
        cert_dir = self.config.runtime_root / "pki" / "kibana"
        podman_arguments: list[str | Path] = ["podman", "run", "--rm"]
        if input_text is not None:
            # Podman does not connect the pipe to container stdin without -i.
            podman_arguments.append("--interactive")
        podman_arguments.extend(
            [
                "--user",
                "0",
                "--entrypoint",
                "/usr/share/kibana/bin/kibana-keystore",
                "-v",
                f"{config_dir}:/usr/share/kibana/config:Z",
                "-v",
                f"{cert_dir}:/usr/share/kibana/config/certs:ro,Z",
                IMAGES["kibana"],
                *arguments,
            ]
        )
        self.runner.run(
            podman_arguments,
            input_text=input_text,
        )

    def prepare_kibana_keystore(self) -> None:
        keystore = self.config.runtime_root / "config" / "kibana" / "kibana.keystore"
        if not keystore.is_file():
            self._kibana_keystore("create")
        entries = {
            "elasticsearch.serviceAccountToken": "kibana-service-token",
            "xpack.security.encryptionKey": "kibana-security-encryption-key",
            "xpack.encryptedSavedObjects.encryptionKey": "kibana-saved-objects-encryption-key",
            "xpack.reporting.encryptionKey": "kibana-reporting-encryption-key",
        }
        for key, secret_name in entries.items():
            value = self.read_secret(secret_name)
            if key.endswith("encryptionKey") and len(value) < 32:
                raise ElkctlError(
                    f"protected secret {secret_name} must contain at least 32 characters"
                )
            self._kibana_keystore(
                "add",
                key,
                "--stdin",
                "--force",
                input_text=f"{json.dumps(value)}\n",
            )
        os.chmod(keystore, 0o660)
        os.chown(keystore, 1000, 0)

    def start_kibana(self) -> None:
        self.create_service_token("elastic/kibana", "elk-poc", "kibana-service-token")
        self.prepare_kibana_keystore()
        self.restart_quadlet("elk-poc-kibana.service")

        def ready() -> bool:
            status, payload = self._kibana_client().json(
                "GET", f"{self.config.url('kibana')}/api/status"
            )
            kibana_status = payload.get("status", {})
            overall = kibana_status.get("overall", {}).get("level")
            elasticsearch = kibana_status.get("core", {}).get("elasticsearch", {}).get("level")
            return status == 200 and overall == "available" and elasticsearch == "available"

        self.wait_for("Kibana", ready, 90)

    def initialize_fleet(self) -> None:
        """Wait until Kibana can complete Elasticsearch-backed Fleet setup."""
        headers = {"kbn-xsrf": "elkctl", "Content-Type": "application/json"}

        def setup_ready() -> bool:
            status, payload = self._kibana_client().json(
                "POST",
                f"{self.config.url('kibana')}/api/fleet/agents/setup",
                headers=headers,
                payload={},
                allow_status=frozenset({503}),
            )
            return (
                status == 200
                and isinstance(payload, dict)
                and payload.get("isInitialized") is True
            )

        self.wait_for("Fleet setup", setup_ready, 60)

    def ensure_package_policy(self, policy_id: str, path: Path) -> None:
        headers = {"kbn-xsrf": "elkctl", "Content-Type": "application/json"}
        status, _ = self._kibana_client().request(
            "GET",
            f"{self.config.url('kibana')}/api/fleet/package_policies/{policy_id}",
            headers=headers,
            allow_status=frozenset({404}),
        )
        if status == 200:
            return
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ElkctlError(f"invalid rendered Fleet policy: {path}") from exc
        self._kibana_client().json(
            "POST",
            f"{self.config.url('kibana')}/api/fleet/package_policies?format=simplified",
            headers=headers,
            payload=payload,
        )
        log(f"created Fleet package policy: {policy_id}")

    def ensure_agent_policy(
        self,
        policy_id: str,
        name: str,
        *,
        fleet_server: bool = False,
    ) -> None:
        """Ensure a framework-owned Fleet agent policy exists before it is referenced."""
        headers = {"kbn-xsrf": "elkctl", "Content-Type": "application/json"}
        client = self._kibana_client()
        status, body = client.request(
            "GET",
            f"{self.config.url('kibana')}/api/fleet/agent_policies/{policy_id}",
            headers=headers,
            allow_status=frozenset({404}),
        )
        if status == 200:
            try:
                item = json.loads(body).get("item", {})
            except (json.JSONDecodeError, AttributeError) as exc:
                raise ElkctlError(
                    f"Fleet returned an invalid agent policy response for {policy_id}"
                ) from exc
            if not item.get("is_managed") and not item.get("is_preconfigured"):
                return
            agents = item.get("agents", 0)
            if not isinstance(agents, int) or agents != 0:
                raise ElkctlError(
                    f"cannot migrate hosted Fleet policy {policy_id}: "
                    f"it reports {agents!r} enrolled agents"
                )
            client.json(
                "POST",
                f"{self.config.url('kibana')}/api/fleet/agent_policies/delete",
                headers=headers,
                payload={"agentPolicyId": policy_id, "force": True},
            )
            log(f"removed stale hosted Fleet agent policy: {policy_id}")
        payload: dict[str, object] = {
            "id": policy_id,
            "name": name,
            "namespace": FLEET_NAMESPACE,
            "description": "Framework-managed policy for the ELK POC",
            "monitoring_enabled": ["logs", "metrics"],
            # Do not set data_output_id or monitoring_output_id here. Explicit
            # per-policy output assignment requires a paid subscription. On the
            # Basic license, policies inherit the global default data and
            # monitoring output declared in kibana.yml.
            "fleet_server_host_id": "elk-poc-fleet-host",
            # The controller attaches integrations to these policies through the
            # Fleet API.  A managed/hosted policy is read-only to that API and is
            # reserved for an external orchestrator such as Elastic Cloud or ECK.
            "is_managed": False,
        }
        if fleet_server:
            payload.update(
                {
                    "has_fleet_server": True,
                    "is_default_fleet_server": True,
                }
            )
        client.json(
            "POST",
            f"{self.config.url('kibana')}/api/fleet/agent_policies",
            headers=headers,
            payload=payload,
        )
        log(f"created Fleet agent policy: {policy_id}")

    def configure_single_node_templates(self) -> None:
        datasets = (
            "logs-system.auth",
            "logs-system.syslog",
            "logs-journald.logs",
            "metrics-system.core",
            "metrics-system.cpu",
            "metrics-system.diskio",
            "metrics-system.filesystem",
            "metrics-system.fsstat",
            "metrics-system.load",
            "metrics-system.memory",
            "metrics-system.network",
            "metrics-system.process.summary",
            "metrics-system.uptime",
        )
        for dataset in datasets:
            self._es_client().json(
                "PUT",
                f"{self.config.url('elasticsearch')}/_component_template/{dataset}@custom",
                payload={"template": {"settings": {"index.number_of_replicas": 0}}},
            )

    def create_enrollment_token(self) -> Path:
        path = self.secret_file("local-agent-enrollment-token")
        if path.is_file() and path.stat().st_size:
            return path
        _, payload = self._kibana_client().json(
            "POST",
            f"{self.config.url('kibana')}/api/fleet/enrollment_api_keys",
            headers={"kbn-xsrf": "elkctl", "Content-Type": "application/json"},
            payload={"policy_id": LOCAL_AGENT_POLICY_ID},
        )
        try:
            value = payload["item"]["api_key"]
        except (KeyError, TypeError) as exc:
            raise ElkctlError("Kibana did not return an Agent enrollment token") from exc
        path.write_text(value, encoding="utf-8")
        os.chmod(path, 0o600)
        log("created protected local Agent enrollment token")
        return path

    def local_agent_online(self) -> bool:
        _, payload = self._kibana_client().json(
            "GET",
            f"{self.config.url('kibana')}/api/fleet/agents?perPage=100",
            headers={"kbn-xsrf": "elkctl"},
        )
        return any(
            item.get("policy_id") == LOCAL_AGENT_POLICY_ID and item.get("status") == "online"
            for item in payload.get("items", [])
        )

    def bootstrap_fleet(self) -> None:
        self.initialize_fleet()
        self.ensure_agent_policy(
            FLEET_SERVER_POLICY_ID,
            "ELK POC Fleet Server",
            fleet_server=True,
        )
        self.ensure_agent_policy(
            LOCAL_AGENT_POLICY_ID,
            "ELK POC Local RHEL",
        )
        rendered = self.config.runtime_root / "config"
        self.ensure_package_policy("elk-poc-local-system", rendered / "system-package-policy.json")
        self.ensure_package_policy(
            "elk-poc-local-journald", rendered / "journald-package-policy.json"
        )
        self.configure_single_node_templates()
        fleet_token = self.create_service_token(
            "elastic/fleet-server", "elk-poc", "fleet-service-token"
        )
        self.ensure_podman_secret("elk_poc_fleet_service_token", fleet_token)
        self.restart_quadlet("elk-poc-fleet-server.service")

        def fleet_ready() -> bool:
            status, payload = self._fleet_client().json(
                "GET", f"{self.config.url('fleet')}/api/status"
            )
            return status == 200 and payload.get("name") == "fleet-server"

        self.wait_for("Fleet Server", fleet_ready, 90)
        enrollment = self.create_enrollment_token()
        self.ensure_podman_secret("elk_poc_local_enrollment_token", enrollment)
        self.restart_quadlet("elk-poc-agent.service")
        self.wait_for("local monitoring Agent", self.local_agent_online, 60)

    def deploy(self) -> None:
        self.require_root()
        log("running mandatory preflight before making changes")
        report = run_preflight(self.config, self.runner)
        report.print()
        if report.failures:
            raise ElkctlError("preflight failed; no deployment changes were made")
        self.configure_host()
        self.ensure_initial_secrets()
        render_all(self.config)
        self.pull_images()
        install_quadlets(self.config, self.runner)
        self.start_elasticsearch()
        self.start_kibana()
        self.bootstrap_fleet()
        log("deployment converged; run 'sudo bin/elkctl status'")

    def plan(self) -> None:
        print(f"Repository/runtime root: {self.config.repo_root}")
        print("Stack version: 9.4.2")
        print("Podman network: automatic subnet allocation")
        print("Images:")
        for name, image in IMAGES.items():
            print(f"  {name}: {image}")
        print("Published endpoints:")
        for service in ("elasticsearch", "kibana", "fleet"):
            print(f"  {self.config.url(service)}")
        print("PKI files:")
        print(f"  service CA: {self.config.service_ca}")
        if self.config.proxy.url:
            print(f"  proxy: {self.config.proxy.url}")
            print(f"  proxy CA: {self.config.proxy_ca}")
        else:
            print("  outbound proxy: disabled")
        print("Persistent state:")
        print(f"  {self.config.runtime_root / 'data'}")

    def status(self) -> int:
        self.require_root()
        failures = 0
        print("POC service health")
        for service in SERVICES:
            result = self.runner.run(
                ["systemctl", "is-active", "--quiet", f"{service}.service"], check=False
            )
            state = "PASS" if result.returncode == 0 else "FAIL"
            print(f"[{state}] {service}.service")
            failures += result.returncode != 0
        if failures:
            print("[INFO] API and telemetry checks skipped until all services are active")
            return 1
        try:
            _, health = self._es_client().json(
                "GET", f"{self.config.url('elasticsearch')}/_cluster/health"
            )
            cluster_status = health.get("status", "unknown")
            marker = "PASS" if cluster_status == "green" else "WARN"
            print(f"[{marker}] Elasticsearch cluster status: {cluster_status}")
            _, kibana = self._kibana_client().json(
                "GET", f"{self.config.url('kibana')}/api/status"
            )
            level = kibana.get("status", {}).get("overall", {}).get("level", "unknown")
            print(f"[{'PASS' if level == 'available' else 'WARN'}] Kibana status: {level}")
            _, fleet = self._fleet_client().json("GET", f"{self.config.url('fleet')}/api/status")
            print(f"[PASS] Fleet Server status: {fleet.get('status', 'HEALTHY')}")
            online = self.local_agent_online()
            print(f"[{'PASS' if online else 'FAIL'}] Local Agent online")
            failures += not online
            status, streams = self._es_client().json(
                "GET",
                f"{self.config.url('elasticsearch')}/_data_stream/"
                "metrics-system.*,logs-system.*,logs-journald.*",
                allow_status=frozenset({404}),
            )
            count = len(streams.get("data_streams", [])) if status == 200 and streams else 0
            print(f"[{'PASS' if count else 'WARN'}] System/Journald data streams: {count}")
        except ElkctlError as exc:
            print(f"[FAIL] API health checks: {exc}")
            failures += 1
        usage = shutil.disk_usage(self.config.repo_root)
        used_percent = round((usage.used / usage.total) * 100, 1)
        print(f"[INFO] Filesystem usage: {used_percent}%")
        return 1 if failures else 0

    def logs(self, service: str) -> None:
        aliases = {
            "elasticsearch": "elk-poc-elasticsearch.service",
            "kibana": "elk-poc-kibana.service",
            "fleet-server": "elk-poc-fleet-server.service",
            "agent": "elk-poc-agent.service",
        }
        if service not in aliases:
            raise ElkctlError("service must be elasticsearch, kibana, fleet-server, or agent")
        result = self.runner.run(
            ["journalctl", "-u", aliases[service], "--no-pager", "-n", "200"], check=False
        )
        print(result.stdout, end="")
        if result.stderr:
            print(result.stderr, end="", file=os.sys.stderr)

    def lifecycle(self, action: str) -> None:
        self.require_root()
        units = [f"{service}.service" for service in SERVICES]
        if action == "stop":
            units.reverse()
        verb = "restart" if action == "restart" else action
        for unit in units:
            self.runner.run(["systemctl", verb, unit], check=action != "stop")

    def destroy(self) -> None:
        self.require_root()
        for service in reversed(SERVICES):
            self.runner.run(["systemctl", "stop", f"{service}.service"], check=False)
        unit_root = Path("/etc/containers/systemd")
        for path in [unit_root / "elk-poc.network", *unit_root.glob("elk-poc-*.container")]:
            path.unlink(missing_ok=True)
        self.runner.run(["systemctl", "daemon-reload"])
        self.runner.run(["podman", "network", "rm", "elk-poc"], check=False)
        log("services removed; persistent data, secrets, and supplied PKI were preserved")
