from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
from typing import Callable
import unittest
from unittest.mock import Mock, patch

from elkctl.checks import CheckReport
from elkctl.stack import StackController


class SafetyTest(unittest.TestCase):
    def test_quadlet_restart_does_not_try_to_enable_generated_unit(self) -> None:
        runner = Mock()
        controller = StackController(Mock(), runner)

        controller.restart_quadlet("elk-poc-elasticsearch.service")

        runner.run.assert_called_once_with(
            ["systemctl", "restart", "elk-poc-elasticsearch.service"]
        )

    def test_missing_agent_policy_is_created_before_it_is_referenced(self) -> None:
        config = Mock()
        config.url.return_value = "https://server.test.internal:5601"
        client = Mock()
        client.request.return_value = (404, b"")
        controller = StackController(config, Mock())
        controller._kibana_client = Mock(return_value=client)

        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            controller.ensure_agent_policy("elk-poc-local-rhel", "ELK POC Local RHEL")

        payload = client.json.call_args.kwargs["payload"]
        self.assertEqual(payload["id"], "elk-poc-local-rhel")
        self.assertEqual(payload["namespace"], "elk_poc")
        self.assertEqual(payload["is_managed"], False)
        self.assertNotIn("data_output_id", payload)
        self.assertNotIn("monitoring_output_id", payload)
        client.json.assert_called_once()

    def test_existing_agent_policy_is_not_recreated(self) -> None:
        config = Mock()
        config.url.return_value = "https://server.test.internal:5601"
        client = Mock()
        client.request.return_value = (200, b'{"item":{"is_managed":false}}')
        controller = StackController(config, Mock())
        controller._kibana_client = Mock(return_value=client)

        controller.ensure_agent_policy("elk-poc-local-rhel", "ELK POC Local RHEL")

        client.json.assert_not_called()

    def test_stale_empty_hosted_policy_is_replaced(self) -> None:
        config = Mock()
        config.url.return_value = "https://server.test.internal:5601"
        client = Mock()
        client.request.return_value = (
            200,
            b'{"item":{"is_managed":true,"is_preconfigured":true,"agents":0}}',
        )
        controller = StackController(config, Mock())
        controller._kibana_client = Mock(return_value=client)

        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            controller.ensure_agent_policy("elk-poc-fleet-server", "ELK POC Fleet Server")

        self.assertEqual(client.json.call_count, 2)
        delete_call, create_call = client.json.call_args_list
        self.assertTrue(delete_call.args[1].endswith("/api/fleet/agent_policies/delete"))
        self.assertEqual(
            delete_call.kwargs["payload"],
            {"agentPolicyId": "elk-poc-fleet-server", "force": True},
        )
        self.assertTrue(create_call.args[1].endswith("/api/fleet/agent_policies"))

    def test_hosted_policy_with_agents_is_not_deleted(self) -> None:
        config = Mock()
        config.url.return_value = "https://server.test.internal:5601"
        client = Mock()
        client.request.return_value = (
            200,
            b'{"item":{"is_managed":true,"is_preconfigured":true,"agents":1}}',
        )
        controller = StackController(config, Mock())
        controller._kibana_client = Mock(return_value=client)

        with self.assertRaisesRegex(Exception, "reports 1 enrolled agents"):
            controller.ensure_agent_policy("elk-poc-fleet-server", "ELK POC Fleet Server")

        client.json.assert_not_called()

    def test_fleet_server_policy_is_api_managed_and_designated_for_fleet_server(self) -> None:
        config = Mock()
        config.url.return_value = "https://server.test.internal:5601"
        client = Mock()
        client.request.return_value = (404, b"")
        controller = StackController(config, Mock())
        controller._kibana_client = Mock(return_value=client)

        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            controller.ensure_agent_policy(
                "elk-poc-fleet-server",
                "ELK POC Fleet Server",
                fleet_server=True,
            )

        payload = client.json.call_args.kwargs["payload"]
        self.assertIs(payload["is_managed"], False)
        self.assertIs(payload["has_fleet_server"], True)
        self.assertIs(payload["is_default_fleet_server"], True)
        self.assertNotIn("data_output_id", payload)
        self.assertNotIn("monitoring_output_id", payload)

    def test_kibana_does_not_preconfigure_controller_owned_agent_policies(self) -> None:
        root = Path(__file__).resolve().parents[1]
        kibana = (root / "deploy" / "kibana" / "kibana.yml.in").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("xpack.fleet.agentPolicies", kibana)

    def test_fleet_setup_retries_temporary_license_unavailability(self) -> None:
        config = Mock()
        config.url.return_value = "https://server.test.internal:5601"
        client = Mock()
        client.json.side_effect = [
            (503, {"message": "License information could not be obtained"}),
            (200, {"isInitialized": True, "nonFatalErrors": []}),
        ]
        controller = StackController(config, Mock())
        controller._kibana_client = Mock(return_value=client)

        def exercise_wait(label: str, check: Callable[[], bool], attempts: int) -> None:
            self.assertEqual(label, "Fleet setup")
            self.assertEqual(attempts, 60)
            self.assertFalse(check())
            self.assertTrue(check())

        controller.wait_for = Mock(side_effect=exercise_wait)
        controller.initialize_fleet()

        self.assertEqual(client.json.call_count, 2)
        for call in client.json.call_args_list:
            self.assertTrue(call.args[1].endswith("/api/fleet/agents/setup"))
            self.assertEqual(call.kwargs["allow_status"], frozenset({503}))

    def test_kibana_readiness_does_not_accept_degraded_status(self) -> None:
        root = Path(__file__).resolve().parents[1]
        controller = (root / "src" / "elkctl" / "stack.py").read_text(encoding="utf-8")

        self.assertNotIn('level in {"available", "degraded"}', controller)
        self.assertIn('overall == "available" and elasticsearch == "available"', controller)

    def test_deployment_declares_basic_license_and_global_default_output(self) -> None:
        root = Path(__file__).resolve().parents[1]
        elasticsearch = (
            root / "deploy" / "elasticsearch" / "elasticsearch.yml.in"
        ).read_text(encoding="utf-8")
        kibana = (root / "deploy" / "kibana" / "kibana.yml.in").read_text(
            encoding="utf-8"
        )

        self.assertIn("xpack.license.self_generated.type: basic", elasticsearch)
        self.assertIn("is_default: true", kibana)
        self.assertIn("is_default_monitoring: true", kibana)

    def test_failed_preflight_prevents_mutation(self) -> None:
        config = Mock()
        runner = Mock()
        controller = StackController(config, runner)
        controller.require_root = Mock()
        controller.configure_host = Mock()
        report = CheckReport()
        report.failed("test failure")
        with patch("elkctl.stack.run_preflight", return_value=report):
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                with self.assertRaisesRegex(Exception, "preflight failed"):
                    controller.deploy()
        controller.configure_host.assert_not_called()

    def test_deployment_assets_contain_no_insecure_flags_or_runtime_socket(self) -> None:
        root = Path(__file__).resolve().parents[1]
        content = "\n".join(
            path.read_text(encoding="utf-8", errors="ignore")
            for path in (root / "deploy").rglob("*")
            if path.is_file()
        )
        self.assertNotIn("--insecure", content)
        self.assertNotIn("/run/podman/podman.sock", content)
        self.assertNotIn("/var/run/docker.sock", content)
        self.assertNotIn("@@NETWORK_SUBNET@@", content)

    def test_controller_does_not_enable_or_disable_generated_quadlet_services(self) -> None:
        root = Path(__file__).resolve().parents[1]
        content = (root / "src" / "elkctl" / "stack.py").read_text(encoding="utf-8")
        self.assertNotIn('["systemctl", "enable"', content)
        self.assertNotIn('["systemctl", "disable"', content)

    def test_mounted_secrets_are_not_world_readable(self) -> None:
        root = Path(__file__).resolve().parents[1]
        quadlets = (root / "deploy" / "quadlet").glob("*.container.in")
        secret_lines = [
            line
            for path in quadlets
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.startswith("Secret=")
        ]
        self.assertEqual(len(secret_lines), 3)
        self.assertTrue(all("mode=0400" in line for line in secret_lines))
        elasticsearch = next(line for line in secret_lines if "elastic_password" in line)
        fleet = next(line for line in secret_lines if "fleet_service_token" in line)
        agent = next(line for line in secret_lines if "enrollment_token" in line)
        self.assertIn("uid=1000", elasticsearch)
        self.assertIn("uid=1000,gid=1000", fleet)
        self.assertIn("uid=0,gid=0", agent)

    def test_fleet_server_runs_as_the_image_non_root_user(self) -> None:
        root = Path(__file__).resolve().parents[1]
        quadlet = (
            root / "deploy" / "quadlet" / "elk-poc-fleet-server.container.in"
        ).read_text(encoding="utf-8")

        self.assertIn("User=1000:1000", quadlet)
        self.assertNotIn("AddCapability=CHOWN", quadlet)
        self.assertNotIn("AddCapability=DAC_OVERRIDE", quadlet)

    def test_elasticsearch_keystore_is_not_directly_bind_mounted(self) -> None:
        root = Path(__file__).resolve().parents[1]
        quadlet = root / "deploy" / "quadlet" / "elk-poc-elasticsearch.container.in"
        content = quadlet.read_text(encoding="utf-8")
        self.assertNotIn(":/usr/share/elasticsearch/config/elasticsearch.keystore", content)

    def test_kibana_keystore_values_are_json_encoded_strings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = Mock()
            config.runtime_root = root / "runtime"
            config.secrets_root = root / "secrets"
            keystore = config.runtime_root / "config" / "kibana" / "kibana.keystore"
            keystore.parent.mkdir(parents=True)
            keystore.write_text("test", encoding="utf-8")
            config.secrets_root.mkdir()
            values = {
                "kibana-service-token": "service-token-value",
                "kibana-security-encryption-key": "s" * 32,
                "kibana-saved-objects-encryption-key": "o" * 32,
                "kibana-reporting-encryption-key": "r" * 32,
            }
            for name, value in values.items():
                (config.secrets_root / name).write_text(value, encoding="utf-8")

            runner = Mock()
            controller = StackController(config, runner)
            with patch("elkctl.stack.os.chown", create=True):
                controller.prepare_kibana_keystore()

            inputs = [call.kwargs["input_text"] for call in runner.run.call_args_list]
            self.assertEqual(inputs, [f"{json.dumps(value)}\n" for value in values.values()])
            for call in runner.run.call_args_list:
                self.assertIn("--interactive", call.args[0])


if __name__ == "__main__":
    unittest.main()
