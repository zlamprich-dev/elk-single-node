from __future__ import annotations

import subprocess
import unittest
from unittest.mock import patch

from elkctl.errors import CommandError
from elkctl.runner import CommandRunner


class CommandRunnerTest(unittest.TestCase):
    def test_timeout_is_reported_as_operator_error(self) -> None:
        with patch(
            "elkctl.runner.subprocess.run",
            side_effect=subprocess.TimeoutExpired("tool", 5),
        ):
            with self.assertRaisesRegex(CommandError, "timed out after 5 seconds"):
                CommandRunner().run(["tool"], timeout=5)


if __name__ == "__main__":
    unittest.main()
