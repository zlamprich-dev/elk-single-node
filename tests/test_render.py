from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from elkctl.errors import ElkctlError
from elkctl.render import atomic_write, render_text


class RenderTest(unittest.TestCase):
    def test_tokens_are_replaced(self) -> None:
        self.assertEqual(render_text("name=@@NAME@@\n", {"NAME": "elk-poc"}), "name=elk-poc\n")

    def test_unresolved_tokens_fail(self) -> None:
        with self.assertRaisesRegex(ElkctlError, "unresolved tokens"):
            render_text("@@MISSING@@", {})

    def test_atomic_write_replaces_complete_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rendered.conf"
            path.write_text("old", encoding="utf-8")
            atomic_write(path, "new\n", 0o600)
            self.assertEqual(path.read_text(encoding="utf-8"), "new\n")

    def test_all_deployment_templates_resolve(self) -> None:
        root = Path(__file__).resolve().parents[1]
        values = {
            "NETWORK_NAME": "elk-poc",
            "BIND_ADDRESS": "0.0.0.0",
            "ELASTICSEARCH_FQDN": "es.test.internal",
            "KIBANA_FQDN": "kibana.test.internal",
            "FLEET_FQDN": "fleet.test.internal",
            "ELASTICSEARCH_PORT": "9200",
            "KIBANA_PORT": "5601",
            "FLEET_PORT": "8220",
            "ELASTICSEARCH_IMAGE": "example/elasticsearch:9.4.2",
            "KIBANA_IMAGE": "example/kibana:9.4.2",
            "FLEET_SERVER_IMAGE": "example/agent:9.4.2",
            "MONITORING_AGENT_IMAGE": "example/agent-complete:9.4.2",
            "RUNTIME_ROOT": "/data/elk-poc/runtime",
            "ELASTICSEARCH_MEMORY": "20G",
            "KIBANA_MEMORY": "4G",
            "FLEET_MEMORY": "2G",
            "AGENT_MEMORY": "2G",
            "FLEET_SERVER_POLICY_ID": "elk-poc-fleet-server",
            "LOCAL_AGENT_POLICY_ID": "elk-poc-local-rhel",
            "FLEET_NAMESPACE": "elk_poc",
            "SYSTEM_PACKAGE_VERSION": "2.20.0",
            "JOURNALD_PACKAGE_VERSION": "1.2.1",
            "CA_CHAIN_YAML": "          TEST-CA",
            "REGISTRY_PROXY_SETTING": "",
            "PROXY_URL": "http://proxy.test.internal:8080",
            "PROXY_CA_ENV": "Environment=SSL_CERT_FILE=/etc/elk-pki/proxy-ca-chain.pem",
            "NO_PROXY": "localhost,es.test.internal,kibana.test.internal,fleet.test.internal",
        }
        for path in (root / "deploy").rglob("*.in"):
            rendered = render_text(path.read_text(encoding="utf-8"), values)
            if path.name.endswith(".json.in"):
                json.loads(rendered)


if __name__ == "__main__":
    unittest.main()
