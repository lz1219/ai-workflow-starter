"""Independent behavioral checks. Kept outside agent workspaces."""

import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import URLError
from urllib.request import urlopen
import xml.etree.ElementTree as ET

from cold_handoff import check_handoff


HTTP_TEST = '''package example;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
@SpringBootTest @AutoConfigureMockMvc
class WorkflowAcceptanceTest {
 @Autowired MockMvc mvc;
 @Test void total() throws Exception { mvc.perform(get("/orders/count")).andExpect(status().isOk()).andExpect(jsonPath("$.count").value(3)); }
 @Test void pending() throws Exception { mvc.perform(get("/orders/count").param("status","pending")).andExpect(status().isOk()).andExpect(jsonPath("$.count").value(2)); }
 @Test void done() throws Exception { mvc.perform(get("/orders/count").param("status","done")).andExpect(status().isOk()).andExpect(jsonPath("$.count").value(1)); }
 @Test void unknown() throws Exception { mvc.perform(get("/orders/count").param("status","other")).andExpect(status().isBadRequest()); }
 @Test void empty() throws Exception { mvc.perform(get("/orders/count").param("status","")).andExpect(status().isBadRequest()); }
}
'''


class EnvironmentUnavailable(Exception):
    pass


def command(argv, cwd, timeout=180):
    return subprocess.run(argv, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)


def check_python(workspace, resume):
    checks = {}
    with tempfile.TemporaryDirectory(prefix="workflow-grade-") as directory:
        root = Path(directory)
        source, target = root / "input.csv", root / "result.json"
        source.write_text('name,email\nAlice,old\n"",blank\nBob,b\nAlice,new\n', encoding="utf-8")
        expected = {"accepted": 2 if resume else 3, "rejected": 2 if resume else 1}
        argv = [sys.executable, "-B", str(workspace / "importer.py"), str(source), str(target)]
        target.write_bytes(b"existing target must survive\n")
        before = target.read_bytes()
        preview = command([*argv, "--dry-run"], workspace, 30)
        checks["dry_run_preserves_existing_file"] = target.is_file() and target.read_bytes() == before
        checks["dry_run_exit_and_counts"] = preview.returncode == 0 and json.loads(preview.stdout) == expected
        if target.exists():
            target.unlink()
        preview = command([*argv, "--dry-run"], workspace, 30)
        checks["dry_run_does_not_create_target"] = preview.returncode == 0 and not target.exists()
        actual = command(argv, workspace, 30)
        checks["normal_import_counts"] = actual.returncode == 0 and json.loads(actual.stdout) == expected
        rows = json.loads(target.read_text(encoding="utf-8")) if target.exists() else []
        expected_rows = ([{"name": "Alice", "email": "new"}, {"name": "Bob", "email": "b"}] if resume else
                         [{"name": "Alice", "email": "old"}, {"name": "Bob", "email": "b"}, {"name": "Alice", "email": "new"}])
        checks["normal_import_preserves_existing_rules"] = rows == expected_rows
    return checks, ""


def check_java(workspace, mixed):
    tool = os.environ.get("EVAL_GRADLE" if mixed else "EVAL_MAVEN") or shutil.which("gradle" if mixed else "mvn")
    if not tool:
        raise EnvironmentUnavailable("Set EVAL_GRADLE/EVAL_MAVEN or install the native build tool")
    with tempfile.TemporaryDirectory(prefix="workflow-grade-") as directory:
        root = Path(directory) / "project"
        shutil.copytree(workspace, root, ignore=shutil.ignore_patterns(".git", ".agents", ".claude", "build", "target", ".gradle", "__pycache__"))
        module = root / "backend" if mixed else root
        test = module / "src/test/java/example/WorkflowAcceptanceTest.java"
        test.parent.mkdir(parents=True, exist_ok=True)
        test.write_text(HTTP_TEST, encoding="utf-8")
        argv = ([tool, "--no-daemon", ":backend:test", ":backend:bootJar"] if mixed else [tool, "-B", "-ntp", "test"])
        result = command(argv, root, 240)
        output = result.stdout + result.stderr
        reports = list(module.glob("build/test-results/test/*WorkflowAcceptanceTest.xml")) if mixed else list(module.glob("target/surefire-reports/*WorkflowAcceptanceTest.xml"))
        checks = {"native_build": result.returncode == 0, "http_acceptance": False}
        if reports:
            report = ET.parse(reports[0]).getroot()
            checks["http_acceptance"] = int(report.get("tests", "0")) == 5 and all(int(report.get(key, "0")) == 0 for key in ("failures", "errors", "skipped"))
        if mixed:
            checks["real_http_client"] = False
            jar = module / "build/libs/backend.jar"
            if result.returncode == 0 and jar.is_file():
                node = shutil.which("node")
                java = str(Path(os.environ["JAVA_HOME"]) / "bin" / ("java.exe" if os.name == "nt" else "java")) if os.environ.get("JAVA_HOME") else shutil.which("java")
                if not node or not java:
                    raise EnvironmentUnavailable("Java and Node are required for HTTP acceptance")
                with socket.socket() as listener:
                    listener.bind(("127.0.0.1", 0))
                    port = listener.getsockname()[1]
                base = f"http://127.0.0.1:{port}"
                with (Path(directory) / "server.log").open("w", encoding="utf-8") as log:
                    server = subprocess.Popen([java, "-jar", str(jar), f"--server.port={port}", "--server.address=127.0.0.1"], cwd=root, stdout=log, stderr=log)
                    try:
                        ready = False
                        for _ in range(120):
                            try:
                                with urlopen(base + "/orders/count", timeout=1) as response:
                                    ready = response.status == 200
                                if ready:
                                    break
                            except (URLError, TimeoutError):
                                if server.poll() is not None:
                                    break
                                time.sleep(0.25)
                        if ready:
                            js = ("import assert from 'node:assert/strict';\n"
                                  "import {orderLabel} from " + json.dumps((root / "frontend/orders.js").as_uri()) + ";\n"
                                  "const base=" + json.dumps(base) + ";\n"
                                  "assert.equal(await orderLabel(base),'Orders: 3');\n"
                                  "assert.equal(await orderLabel(base,'pending'),'Orders: 2');\n"
                                  "assert.equal(await orderLabel(base,'done'),'Orders: 1');\n"
                                  "await assert.rejects(()=>orderLabel(base,'other'));\n")
                            client = command([node, "--input-type=module", "-e", js], root, 30)
                            checks["real_http_client"] = client.returncode == 0
                            output += client.stdout + client.stderr
                    finally:
                        server.terminate()
                        try:
                            server.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            server.kill()
                            server.wait()
        return checks, output


def grade(workspace, case):
    if case == "design-review":
        # Semantic scenarios are judged by a reviewer against the criteria in
        # design-review.md; there is no behavioral grader that could pass or fail them.
        return {"status": "environment_error", "checks": {},
                "output": "design-review is reviewed semantically, not graded automatically"}
    try:
        if case.endswith("cli"):
            checks, output = check_python(workspace, case != "python-cli")
            if case == "cold-handoff-cli":
                checks.update(check_handoff(workspace, command))
        else:
            checks, output = check_java(workspace, case == "gradle-node")
        return {"status": "passed" if all(checks.values()) else "failed", "checks": checks, "output": output}
    except EnvironmentUnavailable as error:
        return {"status": "environment_error", "checks": {}, "output": str(error)}
    except (ValueError, OSError, ET.ParseError, subprocess.TimeoutExpired) as error:
        return {"status": "failed", "checks": {}, "output": str(error)}
