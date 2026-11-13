"""Validate requirement relationships and tasks, then render the Markdown board."""

import argparse
from collections import Counter
from graphlib import CycleError, TopologicalSorter
import json
from pathlib import Path
import re
import sys
from urllib.parse import quote


RELATIONS = ("depends_on", "follows", "related")
TASK_HEADER = "| 编号 | 计划任务 | 状态 | 验收项 | 实际完成内容 | 证据或交接 |"
TASK_STATES = {"待办", "进行中", "阻塞", "完成", "取消"}
EMPTY_CELLS = {"", "—", "-"}


def read_design(path):
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
    acceptance_ids = {
        match[1] for line in lines
        if (match := re.match(r"^\|\s*(AC-\d+)\s*\|", line))
    }
    metadata["tasks"] = read_tasks(path.with_name("tasks.md"), acceptance_ids)
    return metadata


def read_tasks(path, acceptance_ids):
    if not path.is_file():
        return None
    lines = [line.strip() for line in path.read_text(encoding="utf-8-sig").splitlines()]
    if lines.count(TASK_HEADER) != 1:
        raise ValueError(f"{path}: 应包含一份标准任务表")
    table = lines[lines.index(TASK_HEADER) + 1:]
    if not table or not re.fullmatch(r"\|(?:\s*:?-{3,}:?\s*\|){6}", table[0]):
        raise ValueError(f"{path}: 缺少任务表分隔行")

    tasks = []
    seen = set()
    for line in table[1:]:
        if not line.startswith("|"):
            break
        cells = re.split(r"(?<!\\)\|", line)
        if len(cells) != 8 or cells[-1]:
            raise ValueError(f"{path}: 任务行应包含六列")
        task_id, plan, status, acceptance, result, evidence = (cell.strip() for cell in cells[1:-1])
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
            "result": result,
            "evidence": evidence,
        })
    return tasks


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
        "由各需求的 `design.md` 和 `tasks.md` 生成。",
        "",
    ]
    if has_overview:
        rows.extend(["业务背景见 [项目概览](../project.md)。", ""])
    rows.extend([
        "| 需求 | 当前任务 | 已完成增量 | 前置需求 | 演进自 | 相关 |",
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path.cwd())
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true", help="更新 docs/design/README.md")
    mode.add_argument("--check", action="store_true", help="检查需求关系、任务记录和看板时效")
    args = parser.parse_args()
    project = args.project.resolve()
    root = project / "docs" / "design"
    board = root / "README.md"
    try:
        if not project.is_dir():
            raise ValueError(f"项目目录不存在或不是目录：{project}")
        content = render_board(load_designs(root), (root.parent / "project.md").is_file())
        if args.write:
            root.mkdir(parents=True, exist_ok=True)
            board.write_bytes(content.encode("utf-8"))
        elif args.check:
            if not board.is_file() or board.read_text(encoding="utf-8") != content:
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
