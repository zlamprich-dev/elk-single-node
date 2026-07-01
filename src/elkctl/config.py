from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import json
import os
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlparse

from .constants import PORTS, STACK_VERSION, repository_root
from .errors import ConfigurationError

FQDN_PATTERN = re.compile(
    r"^(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+"
    r"[A-Za-z0-9][A-Za-z0-9-]{0,62}$"
)


@dataclass(frozen=True)
class ServiceNames:
    elasticsearch: str
    kibana: str
    fleet: str


@dataclass(frozen=True)
class ProxyConfig:
    url: str | None
    no_proxy: tuple[str, ...] = ()

    @property
    def enabled(self) -> bool:
        return self.url is not None


@dataclass(frozen=True)
class StackConfig:
    repo_root: Path
    source: Path
    services: ServiceNames
    proxy: ProxyConfig
    bind_address: str = "0.0.0.0"

    @property
    def runtime_root(self) -> Path:
        return self.repo_root / "runtime"

    @property
    def secrets_root(self) -> Path:
        return self.repo_root / "secrets"

    @property
    def pki_root(self) -> Path:
        return self.repo_root / "pki"

    @property
    def service_ca(self) -> Path:
        return self.pki_root / "service-ca-chain.pem"

    @property
    def proxy_ca(self) -> Path:
        return self.pki_root / "proxy-ca-chain.pem"

    def certificate(self, service: str) -> Path:
        filename = {
            "elasticsearch": "elasticsearch.crt",
            "kibana": "kibana.crt",
            "fleet": "fleet-server.crt",
        }[service]
        return self.pki_root / filename

    def private_key(self, service: str) -> Path:
        filename = {
            "elasticsearch": "elasticsearch.key",
            "kibana": "kibana.key",
            "fleet": "fleet-server.key",
        }[service]
        return self.pki_root / filename

    def url(self, service: str) -> str:
        host = getattr(self.services, service)
        return f"https://{host}:{PORTS[service]}"

    def no_proxy_value(self) -> str:
        values = {
            "localhost",
            "127.0.0.1",
            "::1",
            self.services.elasticsearch,
            self.services.kibana,
            self.services.fleet,
            *self.proxy.no_proxy,
        }
        return ",".join(sorted(values))

    def proxy_environment(self) -> dict[str, str]:
        if not self.proxy.url:
            return {}
        no_proxy = self.no_proxy_value()
        return {
            "HTTP_PROXY": self.proxy.url,
            "HTTPS_PROXY": self.proxy.url,
            "NO_PROXY": no_proxy,
            "http_proxy": self.proxy.url,
            "https_proxy": self.proxy.url,
            "no_proxy": no_proxy,
        }


def _require_object(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigurationError(f"{name} must be a JSON object")
    return value


def _reject_unknown(value: dict[str, Any], allowed: set[str], name: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ConfigurationError(f"{name} contains unknown fields: {', '.join(unknown)}")


def _require_fqdn(value: Any, name: str, *, allow_examples: bool) -> str:
    if not isinstance(value, str) or not FQDN_PATTERN.fullmatch(value):
        raise ConfigurationError(f"{name} must be a fully qualified DNS name")
    if not allow_examples and value.endswith(".example.corp"):
        raise ConfigurationError(f"{name} still contains the example.corp placeholder")
    return value


def _parse_proxy(value: Any, *, allow_examples: bool) -> ProxyConfig:
    if value is None:
        return ProxyConfig(url=None)
    proxy = _require_object(value, "proxy")
    _reject_unknown(proxy, {"url", "noProxy"}, "proxy")
    no_proxy = proxy.get("noProxy", [])
    if not isinstance(no_proxy, list) or not all(isinstance(item, str) for item in no_proxy):
        raise ConfigurationError("proxy.noProxy must be an array of strings")
    if len(set(no_proxy)) != len(no_proxy):
        raise ConfigurationError("proxy.noProxy entries must be unique")
    for item in no_proxy:
        if not item or any(
            character.isspace() or character in {'"', "'", ",", "="}
            for character in item
        ):
            raise ConfigurationError(
                "proxy.noProxy entries must be individual hostnames, IP addresses, or CIDRs"
            )
    url = proxy.get("url")
    if url is None:
        return ProxyConfig(url=None, no_proxy=tuple(no_proxy))
    if not isinstance(url, str):
        raise ConfigurationError("proxy.url must be a string or null")
    if any(character.isspace() or character in {'"', "'"} for character in url):
        raise ConfigurationError("proxy.url must not contain whitespace or quotes")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ConfigurationError("proxy.url must be an HTTP(S) URL")
    try:
        parsed.port
    except ValueError as exc:
        raise ConfigurationError("proxy.url contains an invalid port") from exc
    if parsed.username or parsed.password:
        raise ConfigurationError("proxy.url must not contain credentials")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ConfigurationError("proxy.url must contain only a scheme, host, and optional port")
    if not allow_examples and parsed.hostname.endswith("example.corp"):
        raise ConfigurationError("proxy.url still contains the example.corp placeholder")
    return ProxyConfig(url=url, no_proxy=tuple(no_proxy))


def load_config(
    path: Path | None = None,
    *,
    repo_root: Path | None = None,
    allow_examples: bool = False,
) -> StackConfig:
    root = (repo_root or repository_root()).resolve()
    selected_value = path if path is not None else os.environ.get(
        "ELK_CONFIG", root / "config" / "stack.json"
    )
    selected = Path(selected_value)
    if not selected.is_file():
        raise ConfigurationError(
            f"configuration not found: {selected}; copy config/stack.example.json first"
        )
    try:
        raw = json.loads(selected.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigurationError(f"configuration is not valid JSON: {selected}: {exc}") from exc
    root_object = _require_object(raw, "configuration")
    _reject_unknown(root_object, {"$schema", "services", "proxy", "bindAddress"}, "configuration")
    if "proxy" not in root_object:
        raise ConfigurationError(
            "configuration.proxy is required; use null for approved direct access"
        )
    services = _require_object(root_object.get("services"), "services")
    _reject_unknown(services, {"elasticsearchFqdn", "kibanaFqdn", "fleetFqdn"}, "services")
    names = ServiceNames(
        elasticsearch=_require_fqdn(
            services.get("elasticsearchFqdn"),
            "services.elasticsearchFqdn",
            allow_examples=allow_examples,
        ),
        kibana=_require_fqdn(
            services.get("kibanaFqdn"), "services.kibanaFqdn", allow_examples=allow_examples
        ),
        fleet=_require_fqdn(
            services.get("fleetFqdn"), "services.fleetFqdn", allow_examples=allow_examples
        ),
    )
    if len({names.elasticsearch, names.kibana, names.fleet}) != 3:
        raise ConfigurationError("the three service FQDNs must be distinct")
    bind_address = root_object.get("bindAddress", "0.0.0.0")
    try:
        ipaddress.ip_address(bind_address)
    except (TypeError, ValueError) as exc:
        raise ConfigurationError("bindAddress must be an IPv4 or IPv6 address") from exc
    return StackConfig(
        repo_root=root,
        source=selected.resolve(),
        services=names,
        proxy=_parse_proxy(root_object.get("proxy"), allow_examples=allow_examples),
        bind_address=str(bind_address),
    )


def integration_versions(config: StackConfig) -> tuple[str, str]:
    path = config.repo_root / "config" / "locks" / "integrations.json"
    try:
        lock = json.loads(path.read_text(encoding="utf-8"))
        if lock["kibanaVersion"] != STACK_VERSION:
            raise ConfigurationError(
                f"integration lock targets {lock['kibanaVersion']}, expected {STACK_VERSION}"
            )
        return str(lock["packages"]["system"]), str(lock["packages"]["journald"])
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ConfigurationError(f"invalid integration lock: {path}: {exc}") from exc
