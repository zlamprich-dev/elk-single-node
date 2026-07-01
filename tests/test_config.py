from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from elkctl.config import load_config
from elkctl.errors import ConfigurationError


class ConfigTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "config" / "locks").mkdir(parents=True)
        (self.root / "config" / "locks" / "integrations.json").write_text(
            json.dumps(
                {
                    "kibanaVersion": "9.4.2",
                    "packages": {"system": "2.20.0", "journald": "1.2.1"},
                }
            )
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write(self, value: dict) -> Path:
        path = self.root / "config" / "stack.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def valid(self) -> dict:
        return {
            "hostFqdn": "server.test.internal",
            "proxy": {"url": "http://proxy.test.internal:8080"},
        }

    def test_minimal_configuration_loads_with_defaults(self) -> None:
        config = load_config(self.write(self.valid()), repo_root=self.root)
        self.assertEqual(config.host_fqdn, "server.test.internal")
        self.assertEqual(config.url("kibana"), "https://server.test.internal:5601")
        self.assertIn("server.test.internal", config.no_proxy_value())

    def test_proxy_may_be_disabled(self) -> None:
        value = self.valid()
        value["proxy"] = None
        config = load_config(self.write(value), repo_root=self.root)
        self.assertFalse(config.proxy.enabled)

    def test_unknown_field_is_rejected(self) -> None:
        value = self.valid()
        value["subnet"] = "10.89.42.0/24"
        with self.assertRaisesRegex(ConfigurationError, "unknown fields"):
            load_config(self.write(value), repo_root=self.root)

    def test_example_placeholder_is_rejected(self) -> None:
        value = self.valid()
        value["hostFqdn"] = "server.example.corp"
        with self.assertRaisesRegex(ConfigurationError, "placeholder"):
            load_config(self.write(value), repo_root=self.root)

    def test_proxy_credentials_are_rejected(self) -> None:
        value = self.valid()
        value["proxy"]["url"] = "http://user:password@proxy.test.internal:8080"
        with self.assertRaisesRegex(ConfigurationError, "must not contain credentials"):
            load_config(self.write(value), repo_root=self.root)

    def test_proxy_path_is_rejected(self) -> None:
        value = self.valid()
        value["proxy"]["url"] = "http://proxy.test.internal:8080/unexpected"
        with self.assertRaisesRegex(ConfigurationError, "scheme, host"):
            load_config(self.write(value), repo_root=self.root)

    def test_no_proxy_command_syntax_is_rejected(self) -> None:
        value = self.valid()
        value["proxy"]["noProxy"] = ["safe.test", "bad value"]
        with self.assertRaisesRegex(ConfigurationError, "individual hostnames"):
            load_config(self.write(value), repo_root=self.root)

    def test_invalid_proxy_port_is_rejected(self) -> None:
        value = self.valid()
        value["proxy"]["url"] = "http://proxy.test.internal:not-a-port"
        with self.assertRaisesRegex(ConfigurationError, "invalid port"):
            load_config(self.write(value), repo_root=self.root)

    def test_retired_services_block_has_migration_message(self) -> None:
        value = self.valid()
        value.pop("hostFqdn")
        value["services"] = {
            "elasticsearchFqdn": "es.test.internal",
            "kibanaFqdn": "kibana.test.internal",
            "fleetFqdn": "fleet.test.internal",
        }
        with self.assertRaisesRegex(ConfigurationError, "retired services block"):
            load_config(self.write(value), repo_root=self.root)


if __name__ == "__main__":
    unittest.main()
