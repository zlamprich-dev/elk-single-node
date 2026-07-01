from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Mapping

from .config import StackConfig, integration_versions
from .constants import (
    FLEET_NAMESPACE,
    FLEET_SERVER_POLICY_ID,
    IMAGES,
    LOCAL_AGENT_POLICY_ID,
    MEMORY_LIMITS,
    NETWORK_NAME,
    PORTS,
)
from .errors import ElkctlError
from .runner import CommandRunner

TOKEN_PATTERN = re.compile(r"@@([A-Z0-9_]+)@@")


def render_text(template: str, values: Mapping[str, str]) -> str:
    rendered = template
    for name, value in values.items():
        rendered = rendered.replace(f"@@{name}@@", value)
    unresolved = sorted(set(TOKEN_PATTERN.findall(rendered)))
    if unresolved:
        raise ElkctlError(f"template contains unresolved tokens: {', '.join(unresolved)}")
    return rendered


def atomic_write(path: Path, content: str, mode: int = 0o640) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="\n",
        dir=path.parent,
        delete=False,
    )
    temporary = Path(handle.name)
    try:
        with handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _mkdir(path: Path, mode: int) -> None:
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, mode)


def ensure_runtime_layout(config: StackConfig) -> None:
    runtime = config.runtime_root
    _mkdir(runtime, 0o750)
    _mkdir(runtime / "config" / "elasticsearch", 0o750)
    _mkdir(runtime / "config" / "kibana", 0o750)
    _mkdir(runtime / "records", 0o700)
    _mkdir(runtime / "tmp", 0o700)
    _mkdir(runtime / "pki", 0o755)
    for service in ("elasticsearch", "kibana", "fleet", "agent"):
        _mkdir(runtime / "pki" / service, 0o755)
    _mkdir(runtime / "data", 0o750)
    for service in ("elasticsearch", "fleet-server", "agent"):
        data = runtime / "data" / service
        _mkdir(data, 0o770)
        os.chown(data, 1000, 0)
    _mkdir(config.secrets_root, 0o700)


def _copy(source: Path, destination: Path, mode: int, owner: tuple[int, int] | None = None) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    os.chmod(destination, mode)
    if owner:
        os.chown(destination, *owner)


def install_pki(config: StackConfig) -> None:
    runtime = config.runtime_root / "pki"
    _copy(config.service_ca, runtime / "service-ca-chain.pem", 0o444)
    for service in ("elasticsearch", "kibana", "fleet"):
        service_dir = runtime / service
        _copy(config.service_ca, service_dir / "service-ca-chain.pem", 0o444)
        certificate_name = {
            "elasticsearch": "elasticsearch.crt",
            "kibana": "kibana.crt",
            "fleet": "fleet-server.crt",
        }[service]
        key_name = certificate_name.replace(".crt", ".key")
        _copy(config.certificate(service), service_dir / certificate_name, 0o444)
        _copy(config.private_key(service), service_dir / key_name, 0o400, (1000, 1000))
    _copy(config.service_ca, runtime / "agent" / "service-ca-chain.pem", 0o444)
    trust_source = config.proxy_ca if config.proxy.url else config.service_ca
    for service in ("kibana", "fleet", "agent"):
        _copy(trust_source, runtime / service / "proxy-ca-chain.pem", 0o444)


def _render_file(source: Path, destination: Path, values: Mapping[str, str], mode: int) -> None:
    rendered = render_text(source.read_text(encoding="utf-8"), values)
    atomic_write(destination, rendered, mode)


def render_configs(config: StackConfig) -> None:
    deploy = config.repo_root / "deploy"
    runtime_config = config.runtime_root / "config"
    system_version, journald_version = integration_versions(config)
    ca_yaml = "\n".join(f"          {line}" for line in config.service_ca.read_text().splitlines())
    registry_setting = ""
    if config.proxy.url:
        registry_setting = f'xpack.fleet.registryProxyUrl: "{config.proxy.url}"'
    shared = {
        "HOST_FQDN": config.host_fqdn,
        "ELASTICSEARCH_PORT": str(PORTS["elasticsearch"]),
        "KIBANA_PORT": str(PORTS["kibana"]),
        "FLEET_PORT": str(PORTS["fleet"]),
        "CA_CHAIN_YAML": ca_yaml,
        "SYSTEM_PACKAGE_VERSION": system_version,
        "JOURNALD_PACKAGE_VERSION": journald_version,
        "FLEET_SERVER_POLICY_ID": FLEET_SERVER_POLICY_ID,
        "LOCAL_AGENT_POLICY_ID": LOCAL_AGENT_POLICY_ID,
        "FLEET_NAMESPACE": FLEET_NAMESPACE,
        "REGISTRY_PROXY_SETTING": registry_setting,
    }
    _render_file(
        deploy / "elasticsearch" / "elasticsearch.yml.in",
        runtime_config / "elasticsearch" / "elasticsearch.yml",
        {},
        0o640,
    )
    _render_file(
        deploy / "kibana" / "kibana.yml.in",
        runtime_config / "kibana" / "kibana.yml",
        shared,
        0o640,
    )
    _copy(
        deploy / "scripts" / "agent-secret-entrypoint.sh",
        runtime_config / "agent-secret-entrypoint.sh",
        0o755,
    )
    for filename in ("system-package-policy.json.in", "journald-package-policy.json.in"):
        destination = runtime_config / filename.removesuffix(".in")
        _render_file(deploy / "fleet" / filename, destination, shared, 0o640)
        try:
            json.loads(destination.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ElkctlError(f"rendered Fleet policy is invalid JSON: {destination}") from exc


def render_quadlets(config: StackConfig) -> None:
    values = {
        "NETWORK_NAME": NETWORK_NAME,
        "BIND_ADDRESS": "0.0.0.0",
        "HOST_FQDN": config.host_fqdn,
        "ELASTICSEARCH_PORT": str(PORTS["elasticsearch"]),
        "KIBANA_PORT": str(PORTS["kibana"]),
        "FLEET_PORT": str(PORTS["fleet"]),
        "ELASTICSEARCH_IMAGE": IMAGES["elasticsearch"],
        "KIBANA_IMAGE": IMAGES["kibana"],
        "FLEET_SERVER_IMAGE": IMAGES["fleet_server"],
        "MONITORING_AGENT_IMAGE": IMAGES["agent"],
        "RUNTIME_ROOT": str(config.runtime_root),
        "ELASTICSEARCH_MEMORY": MEMORY_LIMITS["elasticsearch"],
        "KIBANA_MEMORY": MEMORY_LIMITS["kibana"],
        "FLEET_MEMORY": MEMORY_LIMITS["fleet"],
        "AGENT_MEMORY": MEMORY_LIMITS["agent"],
        "FLEET_SERVER_POLICY_ID": FLEET_SERVER_POLICY_ID,
        "PROXY_URL": config.proxy.url or "",
        "PROXY_CA_ENV": (
            "Environment=SSL_CERT_FILE=/etc/elk-pki/proxy-ca-chain.pem"
            if config.proxy.url
            else ""
        ),
        "NO_PROXY": config.no_proxy_value(),
    }
    source_dir = config.repo_root / "deploy" / "quadlet"
    destination_dir = config.runtime_root / "config"
    for source in sorted(source_dir.glob("*.in")):
        destination = destination_dir / source.name.removesuffix(".in")
        _render_file(source, destination, values, 0o644)


def render_all(config: StackConfig) -> None:
    ensure_runtime_layout(config)
    install_pki(config)
    render_configs(config)
    render_quadlets(config)


def install_quadlets(config: StackConfig, runner: CommandRunner) -> None:
    destination = Path("/etc/containers/systemd")
    destination.mkdir(parents=True, exist_ok=True)
    source = config.runtime_root / "config"
    for path in [source / "elk-poc.network", *sorted(source.glob("elk-poc-*.container"))]:
        _copy(path, destination / path.name, 0o644)
    runner.run(["systemctl", "daemon-reload"])
