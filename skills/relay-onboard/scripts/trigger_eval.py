"""Score skill routing against a labeled set of real requests.

Inputs are two JSON Lines files. Cases label each request:

    {"utterance": "把这个仓库接入一下", "expected": "relay-onboard"}
    {"utterance": "解释这段 Java 代码", "expected": null}

Predictions record the skill a runner chose for the same request:

    {"utterance": "把这个仓库接入一下", "predicted": "relay-onboard"}

`expected` and `predicted` use the installed skill directory name; null means
"should not trigger a workflow skill". The scorer is offline: predictions can be
supplied as a file, or produced by a local router command for each request:

    python trigger_eval.py --cases cases.jsonl \
      --predict-command "python my-router.py --request {utterance}" \
      --output predictions.jsonl

The command prints one skill name, or `none`/empty for "no workflow skill".
Precision and recall are reported per label so a broad description that
over-triggers is visible next to one that under-triggers.
"""

import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys


def load_jsonl(path):
    path = path.resolve()
    if not path.is_file():
        raise ValueError(f"文件不存在：{path}")
    records = []
    seen = set()
    for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"{path.name}:{number} 不是有效 JSON：{error.msg}") from None
        if not isinstance(record, dict):
            raise ValueError(f"{path.name}:{number} 应为 JSON 对象")
        utterance = record.get("utterance")
        if not isinstance(utterance, str) or not utterance.strip():
            raise ValueError(f"{path.name}:{number} 缺少 utterance")
        utterance = utterance.strip()
        if utterance in seen:
            raise ValueError(f"{path.name}:{number} utterance 重复：{utterance}")
        seen.add(utterance)
        records.append(record)
    if not records:
        raise ValueError(f"{path.name} 没有可用样本")
    return records


def label(record, key, source):
    value = record.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{source} 的 {key} 应为技能目录名或 null：{record.get('utterance')!r}")
    return value.strip()


def collect(path, key):
    return {record["utterance"].strip(): label(record, key, path.name) for record in load_jsonl(path)}


def ratio(numerator, denominator):
    return None if denominator == 0 else numerator / denominator


def evaluate(expected, predicted, minimum_precision, minimum_recall):
    missing = sorted(set(expected) - set(predicted))
    extra = sorted(set(predicted) - set(expected))
    if missing or extra:
        raise ValueError(
            "用例与预测不一致："
            + (f"缺少预测 {len(missing)} 条；" if missing else "")
            + (f"多出预测 {len(extra)} 条" if extra else "")
        )

    labels = sorted({value for value in expected.values() if value is not None})
    labels += sorted({value for value in predicted.values() if value is not None and value not in labels})
    results = {}
    for name in labels + [None]:
        support = sum(1 for value in expected.values() if value == name)
        chosen = sum(1 for value in predicted.values() if value == name)
        true_positive = sum(
            1 for utterance, value in expected.items()
            if value == name and predicted[utterance] == name
        )
        precision = ratio(true_positive, chosen)
        recall = ratio(true_positive, support)
        results["（不触发）" if name is None else name] = {
            "support": support,
            "predicted": chosen,
            "true_positive": true_positive,
            "precision": precision,
            "recall": recall,
            "passed": (precision is None or precision >= minimum_precision)
            and (recall is None or recall >= minimum_recall),
        }

    misrouted = [
        {"utterance": utterance, "expected": expected[utterance], "predicted": predicted[utterance]}
        for utterance in expected
        if expected[utterance] != predicted[utterance]
    ]
    return {
        "cases": len(expected),
        "labels": results,
        "misrouted": misrouted,
        "ok": all(result["passed"] for result in results.values()),
    }


def show(value):
    return "—" if value is None else f"{value:.0%}"


def route(command, utterance):
    """Run a local router for one request and normalize its answer."""
    argv = shlex.split(command) if isinstance(command, str) else list(command)
    if not argv:
        raise ValueError("路由命令不能为空")
    if any("{utterance}" in argument for argument in argv):
        argv = [argument.replace("{utterance}", utterance) for argument in argv]
    else:
        argv.append(utterance)
    result = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    if result.returncode:
        raise ValueError(f"router 退出码 {result.returncode}：{result.stderr.strip()[:300]}")
    lines = result.stdout.strip().splitlines()
    value = lines[0].strip() if lines else ""
    return None if value.lower() in ("", "none", "null", "-") else value


def write_predictions(path, predictions):
    lines = [json.dumps({"utterance": utterance, "predicted": value}, ensure_ascii=False)
             for utterance, value in predictions.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, required=True, help="标注用例，JSON Lines")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--predictions", type=Path, help="同一批请求的路由结果，JSON Lines")
    source.add_argument("--predict-command", help="对每条请求运行的路由命令，用 {utterance} 传参")
    source.add_argument("--predict-argv", nargs="+", metavar="ARG",
                        help="以参数数组运行路由，用 {utterance} 传参；适合含空格的路径")
    parser.add_argument("--output", type=Path, help="使用路由命令时保存预测结果")
    parser.add_argument("--min-precision", type=float, default=0.9)
    parser.add_argument("--min-recall", type=float, default=0.9)
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args()

    try:
        if not 0 <= args.min_precision <= 1 or not 0 <= args.min_recall <= 1:
            raise ValueError("阈值应在 0 到 1 之间")
        if args.output and not (args.predict_command or args.predict_argv):
            raise ValueError("--output 只与路由命令同用")
        expected = collect(args.cases.resolve(), "expected")
        if args.predictions:
            predicted = collect(args.predictions.resolve(), "predicted")
        else:
            router = args.predict_command or args.predict_argv
            predicted = {utterance: route(router, utterance) for utterance in expected}
            if args.output:
                write_predictions(args.output, predicted)
                print(f"预测结果已写入：{args.output}", file=sys.stderr)
        report = evaluate(expected, predicted, args.min_precision, args.min_recall)
    except (ValueError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"样本：{report['cases']} 条；阈值：精确率 {show(args.min_precision)}、召回率 {show(args.min_recall)}")
        header = f"{'标签':16} {'样本':>4} {'预测':>4} {'命中':>4} {'精确率':>7} {'召回率':>7} {'结果':>5}"
        print(header)
        print("-" * len(header))
        for name, result in report["labels"].items():
            print(
                f"{name:16} {result['support']:>4} {result['predicted']:>4} "
                f"{result['true_positive']:>4} {show(result['precision']):>7} "
                f"{show(result['recall']):>7} {'通过' if result['passed'] else '失败':>5}"
            )
        for row in report["misrouted"]:
            print(f"误判：{row['utterance']} → 期望 {row['expected']}，实际 {row['predicted']}")
        if report["ok"]:
            print("所有标签均达到阈值。此结果只说明该批请求的路由选择，不代表任务质量。")
        else:
            print("存在未达阈值的标签。先修 description 或补充参考，再重跑同一批请求。")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())