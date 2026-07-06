from __future__ import annotations

from pathlib import Path

CONTROLLER_VERSION = "0.1.0"
STACK_VERSION = "9.4.2"

SERVICE_PREFIX = "elk-poc"
NETWORK_NAME = "elk-poc"
FLEET_NAMESPACE = "elk_poc"
FLEET_SERVER_POLICY_ID = "elk-poc-fleet-server"
LOCAL_AGENT_POLICY_ID = "elk-poc-local-rhel"

PORTS = {
    "elasticsearch": 9200,
    "kibana": 5601,
    "fleet": 8220,
}

IMAGES = {
    "elasticsearch": f"docker.elastic.co/elasticsearch/elasticsearch:{STACK_VERSION}",
    "kibana": f"docker.elastic.co/kibana/kibana:{STACK_VERSION}",
    "fleet_server": f"docker.elastic.co/elastic-agent/elastic-agent:{STACK_VERSION}",
    "agent": f"docker.elastic.co/elastic-agent/elastic-agent-complete:{STACK_VERSION}",
}

MEMORY_LIMITS = {
    "elasticsearch": "12G",
    "kibana": "3G",
    "fleet": "2G",
    "agent": "2G",
}

MINIMUM_CPU = 8
MINIMUM_MEMORY_GIB = 24
MINIMUM_FREE_DISK_GIB = 100
MINIMUM_CERTIFICATE_VALIDITY_DAYS = 30

SERVICES = (
    "elk-poc-elasticsearch",
    "elk-poc-kibana",
    "elk-poc-fleet-server",
    "elk-poc-agent",
)


def repository_root() -> Path:
    """Return the repository root, whether run from source or through bin/elkctl."""
    return Path(__file__).resolve().parents[2]
