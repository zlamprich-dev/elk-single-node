from __future__ import annotations

import os
from pathlib import Path
import platform
import shutil
import socket

from .checks import CheckReport
from .config import StackConfig, integration_versions
from .constants import (
    IMAGES,
    MINIMUM_CERTIFICATE_VALIDITY_DAYS,
    MINIMUM_CPU,
    MINIMUM_FREE_DISK_GIB,
    MINIMUM_MEMORY_GIB,
    PORTS,
    STACK_VERSION,
)
from .errors import CommandError
from .runner import CommandRunner


def _command_check(report: CheckReport, command: str) -> None:
    if shutil.which(command):
        report.passed(f"required command is available: {command}")
    else:
        report.failed(f"required command is missing: {command}")


def _validate_certificate(
    report: CheckReport,
    runner: CommandRunner,
    *,
    label: str,
    certificate: Path,
    private_key: Path,
    fqdn: str,
    ca_file: Path,
    require_client_auth: bool = False,
) -> None:
    for path, description in (
        (certificate, "certificate"),
        (private_key, "private key"),
        (ca_file, "service CA chain"),
    ):
        if not path.is_file():
            report.failed(f"{label} {description} is missing: {path}")
            return
    try:
        runner.run(["openssl", "x509", "-in", certificate, "-noout"])
        runner.run(["openssl", "pkey", "-in", private_key, "-noout"])
        runner.run(["openssl", "verify", "-CAfile", ca_file, certificate])
        runner.run(["openssl", "x509", "-in", certificate, "-noout", "-checkhost", fqdn])
        runner.run(
            [
                "openssl",
                "x509",
                "-in",
                certificate,
                "-noout",
                "-checkend",
                str(MINIMUM_CERTIFICATE_VALIDITY_DAYS * 86400),
            ]
        )
        purposes = runner.run(
            ["openssl", "x509", "-in", certificate, "-noout", "-purpose"]
        ).stdout
        if "SSL server : Yes" not in purposes:
            report.failed(f"{label} certificate does not permit TLS server authentication")
            return
        if require_client_auth and "SSL client : Yes" not in purposes:
            report.failed(
                f"{label} certificate must permit TLS client authentication for transport TLS"
            )
            return
        cert_public = runner.run(
            ["openssl", "x509", "-in", certificate, "-pubkey", "-noout"]
        ).stdout.strip()
        key_public = runner.run(
            ["openssl", "pkey", "-in", private_key, "-pubout"]
        ).stdout.strip()
        if cert_public != key_public:
            report.failed(f"{label} certificate and private key do not match")
            return
    except CommandError as exc:
        report.failed(f"{label} PKI validation failed: {exc}")
        return
    report.passed(f"{label} certificate, SAN, chain, key, EKU, and expiry validate")


def _check_host(report: CheckReport, runner: CommandRunner, config: StackConfig) -> None:
    release = Path("/etc/redhat-release")
    if release.is_file() and "release 9" in release.read_text(errors="ignore").lower():
        report.passed("RHEL 9 detected")
    else:
        report.failed("target must be RHEL 9")
    podman = runner.run(["podman", "version", "--format", "{{.Client.Version}}"], check=False)
    version = podman.stdout.strip()
    if podman.returncode == 0 and version.split(".", 1)[0] == "5":
        report.passed(f"Podman {version} detected")
    else:
        report.failed(f"Podman major version 5 is required; detected {version or 'unknown'}")
    machine = platform.machine().lower()
    if machine in {"x86_64", "amd64"}:
        report.passed("x86-64 architecture detected")
    else:
        report.failed(f"x86-64 architecture required; detected {machine}")
    if Path("/run/systemd/system").is_dir():
        report.passed("systemd runtime detected")
    else:
        report.failed("systemd must be PID 1")
    cgroup = runner.run(["stat", "-fc", "%T", "/sys/fs/cgroup"], check=False).stdout.strip()
    if cgroup == "cgroup2fs":
        report.passed("cgroup v2 detected")
    else:
        report.failed("cgroup v2 is required")
    selinux = runner.run(["getenforce"], check=False).stdout.strip()
    if selinux == "Enforcing":
        report.passed("SELinux enforcing")
    else:
        report.failed(f"SELinux must be enforcing; detected {selinux or 'unknown'}")
    cpu = os.cpu_count() or 0
    if cpu >= MINIMUM_CPU:
        report.passed(f"{cpu} logical CPUs available")
    else:
        report.failed(f"{cpu} CPUs available; recommended POC profile requires {MINIMUM_CPU}")
    memory_kib = 0
    with Path("/proc/meminfo").open() as handle:
        for line in handle:
            if line.startswith("MemTotal:"):
                memory_kib = int(line.split()[1])
                break
    memory_gib = memory_kib // 1024 // 1024
    if memory_gib >= MINIMUM_MEMORY_GIB:
        report.passed(f"{memory_gib} GiB RAM available")
    else:
        report.failed(
            f"{memory_gib} GiB RAM available; POC profile requires {MINIMUM_MEMORY_GIB} GiB"
        )
    usage = shutil.disk_usage(config.repo_root)
    free_gib = usage.free // 1024**3
    if free_gib >= MINIMUM_FREE_DISK_GIB:
        report.passed(f"{free_gib} GiB free under {config.repo_root}")
    else:
        report.failed(
            f"{free_gib} GiB free; selected POC profile requires {MINIMUM_FREE_DISK_GIB} GiB"
        )
    swaps = Path("/proc/swaps").read_text().splitlines()
    if len(swaps) <= 1:
        report.passed("swap is disabled")
    else:
        report.warning("swap is active; disable it before presenting the POC as production-shaped")
    mmap = runner.run(["sysctl", "-n", "vm.max_map_count"], check=False).stdout.strip()
    try:
        current_mmap = int(mmap)
    except ValueError:
        current_mmap = 0
    if current_mmap >= 1048576:
        report.passed(f"vm.max_map_count={current_mmap}")
    else:
        report.warning(f"vm.max_map_count={current_mmap}; deploy will set 1048576")


def _check_network(report: CheckReport, runner: CommandRunner, config: StackConfig) -> None:
    try:
        address_info = socket.getaddrinfo(config.host_fqdn, None)
        addresses = sorted({item[4][0] for item in address_info})
        report.passed(
            f"stack hostname resolves {config.host_fqdn} to {', '.join(addresses)}"
        )
        if any(item[0] == socket.AF_INET for item in address_info):
            report.passed("stack hostname has an IPv4 address for published POC ports")
        else:
            report.failed(
                "stack hostname has no IPv4 address; this POC publishes services on IPv4"
            )
    except socket.gaierror:
        report.failed(f"stack hostname does not resolve: {config.host_fqdn}")
    units = {
        "elasticsearch": "elk-poc-elasticsearch.service",
        "kibana": "elk-poc-kibana.service",
        "fleet": "elk-poc-fleet-server.service",
    }
    for service, port in PORTS.items():
        unit = units[service]
        listeners = runner.run(["ss", "-H", "-ltn", f"sport = :{port}"], check=False)
        if listeners.stdout.strip():
            active = runner.run(["systemctl", "is-active", "--quiet", unit], check=False)
            if active.returncode == 0:
                report.passed(f"port {port} is used by the existing {unit}")
            else:
                report.failed(f"port {port} is already in use by another process")
        else:
            report.passed(f"port {port} is available")
    firewalld = runner.run(["systemctl", "is-active", "--quiet", "firewalld"], check=False)
    if firewalld.returncode == 0:
        report.info("firewalld is active; elkctl does not modify firewall rules")
    else:
        report.warning("firewalld is not active; confirm the intended RHEL firewall policy")


def _check_supply_chain(report: CheckReport, runner: CommandRunner, config: StackConfig) -> None:
    env = config.proxy_environment()
    for label, image in IMAGES.items():
        result = runner.run(["podman", "manifest", "inspect", image], check=False, env=env)
        if result.returncode == 0:
            report.passed(f"official {label} image is reachable: {image}")
        else:
            report.failed(f"cannot resolve {image}; verify proxy and host CA trust")
    curl_common: list[str | Path] = ["curl", "--silent", "--show-error", "--fail"]
    if config.proxy.url:
        curl_common.extend(["--proxy", config.proxy.url, "--cacert", config.proxy_ca])
    epr = runner.run(
        [
            *curl_common,
            f"https://epr.elastic.co/search?package=system&kibana.version={STACK_VERSION}",
        ],
        check=False,
        env=env,
    )
    if epr.returncode == 0:
        report.passed("Elastic Package Registry is reachable")
    else:
        report.failed("Elastic Package Registry is unreachable through the configured proxy/trust")
    artifacts = runner.run(
        [*curl_common, "--head", "https://artifacts.elastic.co/downloads/"],
        check=False,
        env=env,
    )
    if artifacts.returncode == 0:
        report.passed("Elastic artifact service is reachable")
    else:
        report.warning(
            "Elastic artifact service was not confirmed; some Agent components may need it later"
        )


def run_preflight(config: StackConfig, runner: CommandRunner) -> CheckReport:
    report = CheckReport()
    try:
        system_version, journald_version = integration_versions(config)
        report.passed(
            f"configuration is valid; System {system_version} and "
            f"Journald {journald_version} are pinned"
        )
    except Exception as exc:  # converted to a report instead of a traceback
        report.failed(str(exc))
        return report
    if os.geteuid() != 0:
        report.failed("full preflight must run as root (use sudo)")
        return report
    commands = (
        "podman",
        "systemctl",
        "openssl",
        "curl",
        "ss",
        "sysctl",
        "stat",
        "getenforce",
    )
    for command in commands:
        _command_check(report, command)
    if any(shutil.which(command) is None for command in commands):
        return report
    _check_host(report, runner, config)
    _check_network(report, runner, config)
    for service in ("elasticsearch", "kibana", "fleet"):
        key = config.private_key(service)
        if key.exists() and key.stat().st_mode & 0o077:
            report.failed(f"private key must use mode 0600 or stricter: {key}")
        _validate_certificate(
            report,
            runner,
            label=service.title(),
            certificate=config.certificate(service),
            private_key=key,
            fqdn=config.host_fqdn,
            ca_file=config.service_ca,
            require_client_auth=service == "elasticsearch",
        )
    if config.proxy.url:
        if not config.proxy_ca.is_file():
            report.failed(f"proxy CA bundle is missing: {config.proxy_ca}")
        else:
            parsed = runner.run(
                ["openssl", "x509", "-in", config.proxy_ca, "-noout"], check=False
            )
            if parsed.returncode == 0:
                report.passed("proxy CA bundle parses as PEM")
            else:
                report.failed(f"proxy CA bundle is not valid PEM: {config.proxy_ca}")
    _check_supply_chain(report, runner, config)
    return report
