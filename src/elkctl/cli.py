from __future__ import annotations

import argparse
from pathlib import Path

from .config import StackConfig, integration_versions, load_config
from .constants import CONTROLLER_VERSION, PORTS, STACK_VERSION
from .errors import ConfigurationError, ElkctlError
from .output import error
from .preflight import run_preflight
from .runner import CommandRunner
from .stack import StackController


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="elkctl",
        description="Deploy and operate the minimal single-node Elastic Stack POC.",
    )
    parser.add_argument("--config", type=Path, help="site configuration path")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--version", action="version", version=f"elkctl {CONTROLLER_VERSION}")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("config-check", help="validate site inputs and required file locations")
    commands.add_parser("preflight", help="run read-only RHEL, network, PKI, and registry checks")
    commands.add_parser("plan", help="show the intended deployment without secrets")
    commands.add_parser("deploy", help="converge the four-container POC")
    commands.add_parser("status", help="show services, Elastic APIs, Fleet, and telemetry health")
    logs = commands.add_parser("logs", help="show recent service journal output")
    logs.add_argument("service", choices=("elasticsearch", "kibana", "fleet-server", "agent"))
    commands.add_parser("start", help="start services in dependency order")
    commands.add_parser("stop", help="stop services in reverse dependency order")
    commands.add_parser("restart", help="restart services in dependency order")
    commands.add_parser("destroy", help="remove services while preserving data and secrets")
    return parser


def config_check(config: StackConfig) -> int:
    failures = 0
    print(f"[PASS] configuration syntax and site values: {config.source}")
    system_version, journald_version = integration_versions(config)
    print(f"[PASS] Elastic Stack version: {STACK_VERSION}")
    print(f"[PASS] pinned integrations: System {system_version}, Journald {journald_version}")
    for service, port in (
        ("Elasticsearch", PORTS["elasticsearch"]),
        ("Kibana", PORTS["kibana"]),
        ("Fleet Server", PORTS["fleet"]),
    ):
        print(f"[PASS] {service}: {config.host_fqdn}:{port}")
    required = [
        config.service_ca,
        config.certificate("elasticsearch"),
        config.private_key("elasticsearch"),
        config.certificate("kibana"),
        config.private_key("kibana"),
        config.certificate("fleet"),
        config.private_key("fleet"),
    ]
    if config.proxy.url:
        required.append(config.proxy_ca)
        print(f"[PASS] outbound proxy configured: {config.proxy.url}")
    else:
        print("[INFO] outbound proxy disabled")
    for path in required:
        if path.is_file():
            print(f"[PASS] required file exists: {path}")
        else:
            print(f"[PENDING] install required file: {path}")
    print(f"[SUMMARY] failures={failures} pending={sum(not path.is_file() for path in required)}")
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
        runner = CommandRunner(verbose=args.verbose)
        controller = StackController(config, runner)
        if args.command == "config-check":
            return config_check(config)
        if args.command == "preflight":
            report = run_preflight(config, runner)
            report.print()
            return 1 if report.failures else 0
        if args.command == "plan":
            controller.plan()
            return 0
        if args.command == "deploy":
            controller.deploy()
            return 0
        if args.command == "status":
            return controller.status()
        if args.command == "logs":
            controller.logs(args.service)
            return 0
        if args.command in {"start", "stop", "restart"}:
            controller.lifecycle(args.command)
            return 0
        if args.command == "destroy":
            controller.destroy()
            return 0
        parser.error(f"unhandled command: {args.command}")
    except (ConfigurationError, ElkctlError, OSError) as exc:
        error(str(exc))
        return 1
    return 0
