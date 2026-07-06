from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
from pathlib import Path
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


if __name__ == "__main__":
    unittest.main()
