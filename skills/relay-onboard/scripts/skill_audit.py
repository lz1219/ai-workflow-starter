"""Report skill entry size, reference fan-out, and front matter health.

The audit is static and offline. Token counts are estimates: CJK characters
count as one token each and other non-whitespace characters as one token per
four. They are intended for comparing skills and spotting oversized entries,
not for billing.
"""

import argparse
import json
import re
from collections import deque
from pathlib import Path


CJK = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af]")
LINK = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)(?:\s+[\"'][^\"']*[\"'])?\)")
FENCE = re.compile(r"^\s*(`{3,}|~{3,})")
SKIP_PARTS = {".git", "__pycache__", "node_modules"}


def estimate_tokens(text):
    """Approximate token count without model-specific tokenizers."""
    cjk = len(CJK.findall(text))
    other = re.sub(r"\s+", "", CJK.sub("", text))
    return cjk + (len(other) + 3) // 4


def human(value):
    return f"{value:,}"


def front_matter(text):
    """Read the small YAML subset used by SKILL.md files."""
    lines = text.replace("\r\n", "\n").splitlines()
    if not lines or lines[0] != "---":
        return {}, "缺少 front matter"
    try:
        end = lines.index("---", 1)
    except ValueError:
        return {}, "front matter 未闭合"
    metadata = {}
    for line in lines[1:end]:
        key, separator, value = line.partition(":")
        if not separator:
            return {}, f"front matter 行格式有误：{line}"
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        metadata[key.strip()] = value
    return metadata, None


def markdown_links(path, text):
    """Yield resolved Markdown links that stay inside the skill directory."""
    inside_fence = False
    for line in text.replace("\r\n", "\n").splitlines():
        if FENCE.match(line):
            inside_fence = not inside_fence
            continue
        if inside_fence:
            continue
        for target in LINK.findall(line):
            target = target.split("#", 1)[0].split("?", 1)[0]
            if not target or "://" in target or target.startswith(("mailto:", "/")):
                continue
            candidate = (path.parent / target).resolve()
            yield candidate


def markdown_files(skill):
    return sorted(
        path for path in skill.rglob("*.md")
        if path.is_file() and not (set(path.relative_to(skill).parts) & SKIP_PARTS)
    )


def scan(skill, max_entry_tokens):
    entry = skill / "SKILL.md"
    text = entry.read_text(encoding="utf-8-sig")
    metadata, front_error = front_matter(text)
    files = markdown_files(skill)
    tokens = {path: estimate_tokens(path.read_text(encoding="utf-8-sig")) for path in files}

    links = {}
    missing = []
    for path in files:
        links[path] = set()
        for target in markdown_links(path, path.read_text(encoding="utf-8-sig")):
            if target.suffix.lower() != ".md":
                continue
            try:
                target.relative_to(skill.resolve())
            except ValueError:
                continue
            if target.is_file():
                links[path].add(target)
            else:
                missing.append(f"{path.relative_to(skill).as_posix()} -> {target}")

    reachable = set()
    queue = deque([entry.resolve()])
    while queue:
        current = queue.popleft()
        if current in reachable:
            continue
        reachable.add(current)
        queue.extend(links.get(current, ()))

    references = [path for path in files if "references" in path.relative_to(skill).parts]
    orphans = [path for path in references if path.resolve() not in reachable]

    warnings = []
    if front_error:
        warnings.append(front_error)
    if metadata.get("name") != skill.name:
        warnings.append(f"name 应为目录名 {skill.name!r}，当前为 {metadata.get('name')!r}")
    if not metadata.get("description", "").strip():
        warnings.append("description 为空")
    if tokens[entry] > max_entry_tokens:
        warnings.append(f"SKILL.md 约 {human(tokens[entry])} tokens，超过上限 {human(max_entry_tokens)}")
    if orphans:
        warnings.append("未被 SKILL.md 链接的 references：" + ", ".join(
            path.relative_to(skill).as_posix() for path in orphans
        ))
    if missing:
        warnings.append("指向不存在文件的链接：" + "; ".join(missing))

    all_tokens = sum(tokens.values())
    reachable_tokens = sum(tokens[path] for path in reachable)
    return {
        "name": skill.name,
        "entry_tokens": tokens[entry],
        "reachable_tokens": reachable_tokens,
        "all_tokens": all_tokens,
        "reference_files": len(references),
        "markdown_files": len(files),
        "script_files": len([path for path in skill.rglob("*.py") if path.is_file()]),
        "asset_files": len([
            path for path in skill.rglob("*")
            if path.is_file() and path.suffix.lower() not in {".md", ".py", ".pyc"}
            and not (set(path.relative_to(skill).parts) & SKIP_PARTS)
        ]),
        "orphan_references": [path.relative_to(skill).as_posix() for path in orphans],
        "warnings": warnings,
    }


def main():
    default = Path(__file__).resolve().parents[2]
    if default.name != "skills":
        default = Path.cwd() / "skills"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skills", type=Path, default=default, help="包含 <名称>/SKILL.md 的目录")
    parser.add_argument("--max-entry-tokens", type=int, default=3000, help="SKILL.md 入口 token 上限")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("--strict", action="store_true", help="存在警告时以 1 退出")
    args = parser.parse_args()

    root = args.skills.resolve()
    if not root.is_dir():
        print(f"技能目录不存在：{root}")
        return 2
    skills = sorted(
        path.parent for path in root.glob("*/SKILL.md") if path.is_file()
    )
    if not skills:
        print(f"未找到 <名称>/SKILL.md：{root}")
        return 2

    reports = [scan(skill, args.max_entry_tokens) for skill in skills]
    warnings = [f"{report['name']}: {warning}" for report in reports for warning in report["warnings"]]
    if args.json:
        print(json.dumps({"skills": reports, "warnings": warnings}, ensure_ascii=False, indent=2))
    else:
        header = f"{'skill':24} {'entry':>8} {'reachable':>10} {'all':>8} {'refs':>5} {'assets':>7} {'warn':>5}"
        print(header)
        print("-" * len(header))
        for report in reports:
            print(
                f"{report['name']:24} {human(report['entry_tokens']):>8} "
                f"{human(report['reachable_tokens']):>10} {human(report['all_tokens']):>8} "
                f"{report['reference_files']:>5} {report['asset_files']:>7} "
                f"{len(report['warnings']):>5}"
            )
        print()
        print(f"合计：{len(reports)} 个技能，入口约 "
              f"{human(sum(report['entry_tokens'] for report in reports))} tokens，"
              f"全部 Markdown 约 {human(sum(report['all_tokens'] for report in reports))} tokens。")
        for warning in warnings:
            print(f"警告：{warning}")
        if not warnings:
            print("未发现体积、链接或 front matter 警告。")
    return 1 if args.strict and warnings else 0


if __name__ == "__main__":
    raise SystemExit(main())