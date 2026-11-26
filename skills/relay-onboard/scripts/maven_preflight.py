"""Find the requested JDK, confirm Maven's runtime, and optionally run a build."""

import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


WINDOWS = os.name == "nt"
JAVAC = "javac.exe" if WINDOWS else "javac"
JAVA = "java.exe" if WINDOWS else "java"


def major_version(version):
    match = re.match(r"(?:1\.)?(\d+)", version)
    return int(match[1]) if match else None


def captured(command, *, cwd=None, env=None):
    return subprocess.run(
        command, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, errors="replace", timeout=20, check=False,
    )


def jdk_version(home):
    compiler = home / "bin" / JAVAC
    if not (home / "bin" / JAVA).is_file() or not compiler.is_file():
        return None
    try:
        result = captured([str(compiler), "-version"])
    except (OSError, subprocess.TimeoutExpired):
        return None
    match = re.search(r"\bjavac\s+(\S+)", result.stdout)
    return major_version(match[1]) if result.returncode == 0 and match else None


def candidate_homes(version):
    current = os.environ.get("JAVA_HOME")
    for name in (f"JAVA{version}_HOME", f"JDK{version}_HOME", "JAVA_HOME"):
        if os.environ.get(name):
            yield Path(os.environ[name])
    compiler = shutil.which("javac")
    if compiler:
        yield Path(compiler).resolve().parent.parent

    roots = [Path.home() / ".jdks", Path("/usr/lib/jvm"), Path("/Library/Java/JavaVirtualMachines")]
    if current:
        roots.extend(list(Path(current).parents)[:2])
    if os.environ.get("ProgramFiles"):
        programs = Path(os.environ["ProgramFiles"])
        roots.extend(programs / vendor for vendor in ("Java", "Eclipse Adoptium", "Microsoft", "Amazon Corretto"))
    for root in roots:
        try:
            children = sorted(root.iterdir())
        except OSError:
            continue
        for child in children:
            if child.is_dir():
                yield child
                yield child / "Contents" / "Home"


def find_jdk(version, explicit_home):
    seen = set()
    candidates = (explicit_home,) if explicit_home else candidate_homes(version)
    for home in candidates:
        home = home.expanduser().resolve()
        if home not in seen and jdk_version(home) == version:
            return home
        seen.add(home)
    if explicit_home:
        raise ValueError(f"{explicit_home} 不是可用的 JDK {version} 目录")
    raise ValueError(f"未找到 JDK {version}，请通过 --java-home 指定已安装的 JDK")


def maven_runtime(command, project, env=None):
    result = captured([command, "-version"], cwd=project, env=env)
    version_line = re.search(r"Java version:\s*(\S+)", result.stdout)
    if result.returncode or not version_line:
        return None, result.stdout.strip()
    return major_version(version_line[1]), result.stdout.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--java-version", type=int, required=True)
    parser.add_argument("--java-home", type=Path)
    parser.add_argument("--verify", action="store_true", help="以同一 JDK 运行 Maven verify")
    parser.epilog = "在 -- 后传入项目自己的 Maven 参数，例如 -- -B -Dtest=ExampleTest test"
    arguments = sys.argv[1:]
    maven_args = []
    if "--" in arguments:
        separator = arguments.index("--")
        maven_args = arguments[separator + 1:]
        arguments = arguments[:separator]
        if not maven_args:
            parser.error("-- 后需要 Maven 参数")
    args = parser.parse_args(arguments)
    if args.verify and maven_args:
        parser.error("--verify 与 -- 后的 Maven 参数只能选一种")
    if args.verify:
        maven_args = ["-B", "-ntp", "verify"]

    project = args.project.resolve()
    wrapper = project / ("mvnw.cmd" if WINDOWS else "mvnw")
    command = str(wrapper) if wrapper.is_file() else shutil.which("mvn")
    try:
        if not project.is_dir():
            raise ValueError(f"项目目录不存在：{project}")
        if not command:
            raise ValueError("找不到 Maven，请核对项目 Wrapper 或 PATH")
        if args.verify and not (project / "pom.xml").is_file():
            raise ValueError("执行 verify 前需要项目根目录的 pom.xml")
        default_version, _ = maven_runtime(command, project)
        print(f"当前 Maven JDK：{default_version or '未识别'}", flush=True)
        home = find_jdk(args.java_version, args.java_home)
        env = os.environ.copy()
        env["JAVA_HOME"] = str(home)
        env["PATH"] = os.pathsep.join((str(home / "bin"), env.get("PATH", "")))
        actual, details = maven_runtime(command, project, env)
        if actual != args.java_version:
            raise ValueError(f"Maven 未使用要求的 JDK {args.java_version}：\n{details}")
        print(f"本次 JAVA_HOME：{home}\n{details}", flush=True)
        if maven_args:
            return subprocess.run([command, *maven_args], cwd=project, env=env).returncode
        print("预检通过。构建与依赖解析待项目验证命令确认。")
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
