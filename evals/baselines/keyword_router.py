"""Deterministic keyword baseline for the trigger dataset.

This is not a model or the installed skills' routing. It exists to exercise the
scoring pipeline without a runner and to give a reproducible floor:

    python skills/relay-onboard/scripts/trigger_eval.py \
      --cases evals/trigger_cases.jsonl \
      --predict-argv python evals/baselines/keyword_router.py {utterance}

A low score here can still mean the dataset is fine and the baseline is crude.
Compare model predictions against the same dataset, not against a claim that
this baseline represents real routing.
"""

import sys

CHANGE = ("设计", "需求", "验收", "看板", "任务", "AC-", "CI", "评审", "模板")
ONBOARD = ("接入", "初始化", "安装", "更新工作流", "AGENTS", "monorepo", "规范", "覆盖层", "框架", "测试入口")


def route(text):
    if any(word in text for word in CHANGE):
        return "relay-change"
    if any(word in text for word in ONBOARD):
        return "relay-onboard"
    return "none"


if __name__ == "__main__":
    print(route(sys.argv[1] if len(sys.argv) > 1 else sys.stdin.read()))