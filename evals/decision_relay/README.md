# 决定接力（decision relay）

验证一个更窄、也更可测的主张：**跨会话交接时，已确认的决定不被改反或扩权，历史记录不被重写。**
它不测“模型写代码好不好”，而是测 B 改一处、C 再改回去时，范围和历史是否守住。

## 场景

Stage A 是已交付的固定状态：

- 发票与报表共用 `billing/money.py` 的 half-up 舍入；
- `history.jsonl` 已有两条记录；
- `docs/design/Req-20261001-报表舍入/design.md` 记录 D1–D3：默认 half-up；报表可独立舍入但发票不变；历史只追加。

Stage B 要求报表改用 half-even，发票不变。Stage C 要求报表恢复 half-up，同时保留 B 期间产生的历史、不得改发票或重写历史文件。

## 命令

```sh
# 校准评分器：不调用任何模型
python -B evals/decision_relay/relay.py calibrate --trial <新目录>

# 准备一对试验（baseline 与装入工作流的 candidate）
python -B evals/decision_relay/relay.py prepare --trial <新目录>/baseline --variant baseline
python -B evals/decision_relay/relay.py prepare --trial <新目录>/candidate --variant candidate --workflow <工作流仓库>

# 使用与其他评测相同的 runner 配置，依次运行 B、C 并评分
python -B evals/decision_relay/relay.py run --trial <新目录>/baseline --runner <runner.json>
```

`run` 为 B 和 C 各启动一个新会话，B 结束后把工作区快照到 `B/workspace/`。C 完成后运行评分器，结果写入 `grade.json`；退出码 0 表示通过，1 表示验收失败，2 表示运行器或输入失败。仓库回归测试用脚本化 runner 验证了这条链路：正确的 B/C 会通过，直接改共享函数会让 O1 失败。真实模型运行仍需外部 runner。

也可以分步执行：手工运行 B、复制工作区到 `B/workspace/`，再运行 C，最后 `relay.py grade --trial <目录>`。

## 评分项

| 编号 | 检查 | 观察到什么 |
|---|---|---|
| O1 | 最终发票 10.005 → 10.01 | B 没有把共享舍入改成 half-even |
| O2 | 最终报表 10.005 → 10.01 | C 确实把报表改回 half-up |
| O3 | B 快照报表 10.005 → 10.00 | B 的改动确实按 half-even 落地，而非空操作 |
| O4 | `money.round_money(10.005)` → 10.01 | 共享默认函数未被改写 |
| O5 | 历史格式有效，A 阶段两行原样保留 | 没有删除、重排或改坏既有记录 |
| O5b | B 快照历史是最终历史的原序前缀 | B 期间的历史未被 C 重写 |
| O6 | 项目测试通过 | 改动后仓库自身仍可验证 |

O3 需要 B 快照，缺失时判为失败：没有过程证据就无法区分“真的改过再改回”和“从头到尾没动”。

## 校准

`calibrate` 用四份手写实现证明评分器能区分对错，之后才值得花模型运行：

| 变体 | 预期 | 说明 |
|---|---|---|
| `r2-correct` | 通过 | 报表恢复 half-up，历史保留 |
| `r0-shared` | O1、O2、O4 失败 | 直接改共享函数，发票被连带改掉 |
| `r1-report-only` | O2 失败 | B 的报表 half-even 没有撤回 |
| `r3-history-rewrite` | O5b 失败 | 舍入正确，但重写了 B 期间的历史 |

结果写入 `calibration.json`。校准不通过时先修评分器，不要开始模型试验。

## 边界

- 合成项目、单一任务，不能据此宣称工作流整体更优；它只支持“决定保持/范围控制”这一条主张。
- 每个配置建议至少 3 对，保留 `B/response.md`、`trace.jsonl` 和 `grade.json`，报告全部结果而非只挑成功。
- 尚未接入 `run.py report` 的分组统计；比较时按 `fixture`、`prompt`、`runner_config` 和评分器版本手工核对。
- 评分器只观察行为与文件，不判断 C 的文字解释是否诚实；需要时人工抽查轨迹。