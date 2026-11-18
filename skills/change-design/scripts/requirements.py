"""Validate requirement relationships and tasks, then render the Markdown board."""

import argparse
from collections import Counter
from graphlib import CycleError, TopologicalSorter
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from tempfile import NamedTemporaryFile
from urllib.parse import quote


RELATIONS = ("depends_on", "follows", "related")
TASK_HEADER = "| 编号 | 计划任务 | 状态 | 验收项 | 实际完成内容 | 证据或交接 |"
TASK_STATES = {"待办", "进行中", "阻塞", "完成", "取消"}
EMPTY_CELLS = {"", "—", "-"}
ACCEPTANCE_SECTION = re.compile(r"^##\s+(?:\d+\.\s*)?需求与验收\s*$")
VERIFICATION_PLACEHOLDERS = EMPTY_CELLS | {"测试、命令或手工步骤", "实现后填写"}
BOARD_START = "<!-- ai-workflow:board -->"
BOARD_END = "<!-- /ai-workflow:board -->"
BOARD_SOURCE = "由各需求的 `design.md` 和 `tasks.md` 生成。"
BOARD_HEADER = "| 需求 | 当前任务 | 已完成增量 | 前置需求 | 演进自 | 相关 |"


def visible_lines(lines):
    """Ignore fenced examples consistently in design and task validation."""
    fence = None
    for raw in lines:
        line = raw.strip()
        if fence:
            if len(line) >= len(fence) and not line.strip(fence[0]):
                fence = None
            yield ""
            continue
        marker = re.match(r"^(`{3,}|~{3,})", line)
        if marker:
            fence = marker[1]
            yield ""  # A code block terminates the preceding table.
        else:
            yield line


def table_cells(line):
    if not line.startswith("|"):
        return None
    cells = re.split(r"(?<!\\)\|", line)[1:]
    if cells and cells[-1] == "":
        cells.pop()
    return [cell.strip() for cell in cells]


def acceptance_data(lines):
    criteria = {}
    verification = set()
    references = set()
    section = ""
    in_verification_table = False
    for line in visible_lines(lines):
        if re.match(r"^#{1,2}\s", line):
            section = line
            in_verification_table = False
        cells = table_cells(line)
        if not cells:
            in_verification_table = False
            continue
        criterion = cells[0] if re.fullmatch(r"AC-\d+", cells[0]) else None
        if ACCEPTANCE_SECTION.fullmatch(section):
            if criterion:
                if criterion in criteria:
                    raise ValueError(f"重复验收编号：{criterion}")
                criteria[criterion] = tuple(cells[1:])
        elif cells[0] == "验收项":
            in_verification_table = "验证" in section or "验收" in section
        elif in_verification_table and criterion:
            references.add(criterion)
            if any(cell not in VERIFICATION_PLACEHOLDERS for cell in cells[1:]):
                verification.add(criterion)
    if references - criteria.keys():
        raise ValueError("验证表引用了未知验收项：" + ", ".join(sorted(references - criteria.keys())))
    return criteria, verification


def read_design(path, *, review=False):
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    if not lines or lines[0] != "---" or "---" not in lines[1:]:
        raise ValueError(f"{path}: 缺少需求元数据")
    metadata = {}
    for line in lines[1:lines.index("---", 1)]:
        key, separator, value = line.partition(":")
        if not separator or key in metadata:
            raise ValueError(f"{path}: 元数据格式有误：{line}")
        try:
            metadata[key] = json.loads(value.strip())
        except ValueError as error:
            raise ValueError(f"{path}: {key} 应使用 JSON 格式的值") from error
    title = metadata.get("title")
    if not isinstance(title, str) or not title.strip() or len(title.splitlines()) != 1:
        raise ValueError(f"{path}: title 应为单行字符串")
    for field in RELATIONS:
        references = metadata.setdefault(field, [])
        if not isinstance(references, list) or any(not isinstance(name, str) for name in references):
            raise ValueError(f"{path}: {field} 应为目录名列表")
        if len(references) != len(set(references)):
            raise ValueError(f"{path}: {field} 含重复引用")
    try:
        criteria, verification = acceptance_data(lines)
    except ValueError as error:
        raise ValueError(f"{path}: {error}") from error
    metadata["tasks"] = read_tasks(path.with_name("tasks.md"), criteria.keys())
    if review:
        metadata["criteria"] = criteria
        metadata["coverage_warnings"] = review_coverage(criteria.keys(), verification, metadata["tasks"])
    return metadata


def read_tasks(path, acceptance_ids):
    if not path.is_file():
        return None
    lines = list(visible_lines(path.read_text(encoding="utf-8-sig").splitlines()))
    headers = [i for i, line in enumerate(lines) if table_cells(line) == table_cells(TASK_HEADER)]
    if len(headers) != 1:
        raise ValueError(f"{path}: 应包含一份标准任务表")
    table = lines[headers[0] + 1:]
    separators = table_cells(table[0]) if table else None
    if not separators or len(separators) != 6 or any(not re.fullmatch(r":?-{3,}:?", cell) for cell in separators):
        raise ValueError(f"{path}: 缺少任务表分隔行")

    tasks = []
    seen = set()
    end = next((i for i in range(1, len(table)) if not table[i].startswith("|")), len(table))
    for line in [*lines[:headers[0]], *table[end:]]:
        cells = table_cells(line)
        if cells and re.fullmatch(r"T[1-9]\d*", cells[0]):
            raise ValueError(f"{path}: {cells[0]} 位于标准任务表之外，请移回表内并移除行间空行")
    for line in table[1:end]:
        cells = table_cells(line)
        if len(cells) != 6:
            raise ValueError(f"{path}: 任务行应包含六列")
        task_id, plan, status, acceptance, result, evidence = cells
        if not re.fullmatch(r"T[1-9]\d*", task_id) or task_id in seen or plan in EMPTY_CELLS:
            raise ValueError(f"{path}: 无效、重复或缺少计划的任务 {task_id!r}")
        seen.add(task_id)
        if status not in TASK_STATES:
            raise ValueError(f"{path}: {task_id} 的状态无效：{status!r}")
        references = set(re.split(r"[、,，]\s*", acceptance)) if acceptance not in EMPTY_CELLS else set()
        if references - acceptance_ids:
            raise ValueError(f"{path}: {task_id} 引用了未知验收项：{', '.join(sorted(references - acceptance_ids))}")
        if status == "完成" and (result in EMPTY_CELLS or evidence in EMPTY_CELLS):
            raise ValueError(f"{path}: {task_id} 完成时须记录实际内容和证据")
        if status == "阻塞" and evidence in EMPTY_CELLS:
            raise ValueError(f"{path}: {task_id} 阻塞时须记录原因或恢复条件")
        tasks.append({
            "id": task_id,
            "plan": plan,
            "status": status,
            "acceptance": references,
            "result": result,
            "evidence": evidence,
        })
    return tasks


def review_coverage(criteria, verification, tasks):
    if not criteria:
        return ["未识别「需求与验收」中的 AC-* 条目，请核对设计范围和表格。"]
    for task in tasks or []:
        if task["status"] != "取消":
            verification.update(task["acceptance"])
    return [
        f"{criterion} 缺少关联任务或验证安排，请补充任务、手工验证、历史证据或延期安排。"
        for criterion in sorted(criteria - verification, key=lambda value: (int(value[3:]), value))
    ]


def review_changes(design, base, current):
    def git(*args):
        result = subprocess.run(["git", "-C", str(design.parent), *args], capture_output=True)
        if result.returncode:
            raise ValueError(result.stderr.decode("utf-8", errors="replace").strip() or "无法读取 Git 基准")
        return result.stdout

    revision = git("rev-parse", "--verify", "--end-of-options", base + "^{commit}").decode().strip()
    # ls-tree resolves this path relative to the requirement's directory.
    entry = git("ls-tree", "-z", revision, "--", design.name)
    previous = {}
    if entry:
        object_id = entry.split(b"\t", 1)[0].split()[2].decode()
        previous, _ = acceptance_data(git("cat-file", "blob", object_id).decode("utf-8-sig").splitlines())
    criteria = current["criteria"]
    changes = []
    for key in sorted(previous.keys() | criteria.keys(), key=lambda k: (int(k[3:]), k)):
        if previous.get(key) == criteria.get(key):
            continue
        old = " / ".join(previous[key]) if key in previous else "（基准无此项）"
        new = " / ".join(criteria[key]) if key in criteria else "（当前无此项）"
        tasks = [f"{t['id']}（{t['status']}）" for t in current["tasks"] or [] if key in t["acceptance"]]
        changes.append(f"{key}: {old} → {new}。当前关联任务：{'、'.join(tasks) or '无'}")
    return revision, changes


def load_designs(root):
    designs = {path.parent.name: read_design(path) for path in sorted(root.glob("*/design.md"))}
    for name, metadata in designs.items():
        for field in RELATIONS:
            for reference in metadata[field]:
                if reference == name or reference not in designs:
                    raise ValueError(f"{name}: {field} 指向无效需求 {reference!r}")
    prerequisites = {
        name: [*metadata["depends_on"], *metadata["follows"]]
        for name, metadata in designs.items()
    }
    try:
        TopologicalSorter(prerequisites).prepare()
    except CycleError as error:
        raise ValueError("需求依赖或演进关系形成循环：" + " → ".join(error.args[1])) from error
    return designs


def table_text(value):
    title = value.replace(r"\|", "|").replace("\\", "\\\\")
    for character in "[]|":
        title = title.replace(character, "\\" + character)
    return title


def design_link(name, designs):
    return f"[{table_text(designs[name]['title'])}]({quote(name, safe='')}/design.md)"


def task_summary(name, tasks):
    if tasks is None:
        return "待建任务", "—"
    counts = Counter(task["status"] for task in tasks)
    current = "，".join(
        f"{status} {counts[status]}" for status in ("进行中", "阻塞", "待办") if counts[status]
    ) or "暂无未完任务"
    task_link = f"[{current}]({quote(name, safe='')}/tasks.md)"
    completed = [task for task in reversed(tasks) if task["status"] == "完成"]
    results = [
        f"{task['id']} {table_text(task['result'])}" for task in completed[:3]
    ]
    if len(completed) > len(results):
        results.append(f"另 {len(completed) - len(results)} 项见任务记录")
    return task_link, "；".join(results) or "—"


def render_board(designs, has_overview):
    rows = [
        "# 需求看板",
        "",
        BOARD_SOURCE,
        "",
    ]
    if has_overview:
        rows.extend(["业务背景见 [项目概览](../project.md)。", ""])
    rows.extend([
        BOARD_HEADER,
        "|---|---|---|---|---|---|",
    ])
    blockers = []
    for name, metadata in designs.items():
        current, results = task_summary(name, metadata["tasks"])
        cells = [design_link(name, designs), current, results]
        for references in (metadata["depends_on"], metadata["follows"], metadata["related"]):
            cells.append("、".join(design_link(key, designs) for key in references) or "—")
        rows.append("| " + " | ".join(cells) + " |")
        for task in metadata["tasks"] or []:
            if task["status"] == "阻塞":
                label = table_text(f"{metadata['title']} / {task['id']}")
                target = f"{quote(name, safe='')}/tasks.md"
                plan = table_text(task["plan"])
                evidence = table_text(task["evidence"])
                blockers.append(f"- [{label}]({target}) {plan} — {evidence}")
    if not designs:
        rows.append("| 暂无需求 | — | — | — | — | — |")
    if blockers:
        rows.extend(["", "## 阻塞任务", "", *blockers])
    return "\n".join(rows) + "\n"


def legacy_board(text):
    """Recognize the previous generator's layout, including a stale task list."""
    lines = text.splitlines()
    if lines[:4] != ["# 需求看板", "", BOARD_SOURCE, ""]:
        return False
    lines = lines[4:]
    if lines[:2] == ["业务背景见 [项目概览](../project.md)。", ""]:
        lines = lines[2:]
    if lines[:2] != [BOARD_HEADER, "|---|---|---|---|---|---|"]:
        return False
    index = 2
    while index < len(lines):
        cells = table_cells(lines[index])
        if not cells or len(cells) != 6:
            break
        if not (cells[0] == "暂无需求" or re.fullmatch(r"\[.+\]\([^)]+/design\.md\)", cells[0])):
            return False
        index += 1
    rest = lines[index:]
    return index > 2 and (not rest or (
        rest[:3] == ["", "## 阻塞任务", ""] and len(rest) > 3
        and all(re.fullmatch(r"- \[.+ / T\d+\]\([^)]+/tasks\.md\) .+ — .+", line) for line in rest[3:])
    ))


def board_document(original, content, *, check):
    """Replace only the opted-in region, preserving surrounding bytes."""
    bom = b"\xef\xbb\xbf" if original and original.startswith(b"\xef\xbb\xbf") else b""
    text = (original or b"").decode("utf-8-sig")
    lines = text.splitlines(keepends=True)
    markers = [(i, line) for i, line in enumerate(visible_lines(lines))
               if line in (BOARD_START, BOARD_END) and lines[i].rstrip("\r\n") == line]
    title, body = content.split("\n\n", 1)
    if markers:
        if [line for _, line in markers] != [BOARD_START, BOARD_END]:
            raise ValueError("看板生成区标记缺失、重复或顺序有误，请保留一对独立成行的标记")
        start, end = (i for i, _ in markers)
        newline = "\r\n" if lines[start].endswith("\r\n") else "\n"
        document = "".join(lines[:start + 1]) + body.replace("\n", newline) + "".join(lines[end:])
    else:
        if original is not None and not legacy_board(text):
            raise ValueError(f"已有需求索引。接入自动看板时，在选定位置分别加入 {BOARD_START} 和 {BOARD_END}")
        if check and original is not None and text.replace("\r\n", "\n") == content:
            return original
        newline = "\r\n" if "\r\n" in text else "\n"
        document = f"{title}\n\n{BOARD_START}\n{body}{BOARD_END}\n".replace("\n", newline)
    return bom + document.encode("utf-8")


def write_board(board, original, updated):
    board.parent.mkdir(parents=True, exist_ok=True)
    if original is None:
        with board.open("xb") as output:
            output.write(updated)
        return
    board = board.resolve()
    with NamedTemporaryFile(dir=board.parent, delete=False) as output:
        temporary = Path(output.name)
    try:
        temporary.write_bytes(updated)
        shutil.copymode(board, temporary)
        if board.read_bytes() != original:
            raise ValueError(f"{board}: 刷新期间文件发生变化，请重新读取看板")
        os.replace(temporary, board)
    finally:
        temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path.cwd())
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true", help="更新 docs/design/README.md")
    mode.add_argument("--check", action="store_true", help="检查需求关系、任务记录和看板时效")
    mode.add_argument("--review", metavar="需求目录名", help="只读检查指定需求的验收覆盖，缺口输出提示")
    parser.add_argument("--base", metavar="Git版本", help="配合 --review 对比同一路径的验收条目与关联任务")
    args = parser.parse_args()
    if args.base is not None and args.review is None:
        parser.error("--base 需与 --review 同用")
    project = args.project.resolve()
    root = project / "docs" / "design"
    board = root / "README.md"
    try:
        if not project.is_dir():
            raise ValueError(f"项目目录不存在或不是目录：{project}")
        if args.review is not None:
            design = next(
                (path for path in root.glob("*/design.md") if path.parent.name == args.review),
                None,
            )
            if design is None:
                raise ValueError(f"未找到需求目录：{args.review}")
            current = read_design(design, review=True)
            warnings = current["coverage_warnings"]
            if args.base is not None:
                revision, changes = review_changes(design, args.base, current)
                print(f"{args.review}: 对比 {revision[:12]} 与工作区")
                for change in changes:
                    print(change)
                print("请核对变更项的现行预期和原证据适用范围。" if changes else "同一路径的验收表条目无变化。")
            for warning in warnings:
                print(f"{args.review}: {warning}", file=sys.stderr)
            if not warnings:
                print(f"{args.review}: 验收项均已安排任务或验证；此检查不代表验收通过。")
            return 0
        content = render_board(load_designs(root), (root.parent / "project.md").is_file())
        if args.write or args.check:
            original = board.read_bytes() if board.exists() else None
            updated = board_document(original, content, check=args.check)
            if args.write and original != updated:
                write_board(board, original, updated)
            elif args.check and original != updated:
                raise ValueError(f"{board}: 看板需重新生成")
        else:
            sys.stdout.reconfigure(encoding="utf-8")
            print(content, end="")
    except (ValueError, OSError) as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
