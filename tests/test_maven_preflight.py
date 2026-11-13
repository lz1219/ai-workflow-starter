from contextlib import redirect_stdout
import importlib.util
from io import StringIO
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "skills/project-onboard/scripts/maven_preflight.py"
spec = importlib.util.spec_from_file_location("maven_preflight", SCRIPT)
preflight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preflight)


class MavenPreflightTests(unittest.TestCase):
    def test_forwards_arguments_with_the_checked_jdk_and_returns_maven_status(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary).resolve()
            home = project / "test jdk"
            maven = "test-maven"
            maven_args = ["-B", "-Dtest=ExampleTest", "-Dsample=two words", "test"]
            cli_args = [str(SCRIPT), "--project", str(project), "--java-version", "17", "--", *maven_args]

            with (
                patch.object(sys, "argv", cli_args),
                patch.object(preflight.shutil, "which", return_value=maven),
                patch.object(preflight, "find_jdk", return_value=home) as find_jdk,
                patch.object(preflight, "maven_runtime", side_effect=[(8, ""), (17, "Java version: 17")]) as runtime,
                patch.object(preflight.subprocess, "run", return_value=subprocess.CompletedProcess([], 7)) as build,
                redirect_stdout(StringIO()),
            ):
                self.assertEqual(preflight.main(), 7)

            find_jdk.assert_called_once_with(17, None)
            runtime.assert_any_call(maven, project)
            args, kwargs = build.call_args
            self.assertEqual(args, ([maven, *maven_args],))
            self.assertEqual(kwargs["cwd"], project)
            environment = kwargs["env"]
            self.assertEqual(environment["JAVA_HOME"], str(home))
            self.assertEqual(environment["PATH"].split(os.pathsep)[0], str(home / "bin"))
            runtime.assert_called_with(maven, project, environment)
