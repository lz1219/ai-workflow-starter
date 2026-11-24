# 真实任务评测

评测 AI 的实际交付结果。脚本单元测试仍在 `tests/`，这里提供独立项目、统一任务、外部验收及试验记录。仓库自带的评测项目和数据均为合成样例。

已执行的检查与局限见 [首轮验证记录](VALIDATION.md)。

| 场景 | 外部验收 |
|---|---|
| python-cli | dry-run 不创建或改写文件，数量与普通导入一致 |
| resume-cli | 完成 dry-run 修复，同时保留此前已交付的去重行为 |
| cold-handoff-cli | 从原任务续做，保留现行的大小写规则和历史证据，留下与当前代码一致且可定位的验证回执 |
| maven-spring | 通过真实 Spring MockMvc 验证计数、筛选和非法参数 |
| gradle-node | 后端 HTTP 验证，并启动真实应用核对 Node 消费端筛选与错误处理 |
| design-review | 语义评审，由评审者按判据判定；`grade` 返回 `environment_error`，不自动评分 |
| claim-check-cli | 行为验收加任务回写是否与实际结果一致（用于规则消融） |
| gate-check-cli | 自带检查不覆盖某条验收项时，外部验收能否发现漏项（用于规则消融） |
| drift-cli | 两阶段：A 交付一半，B 冷接手；外部验收核对是否保持已交付的导入顺序（用于跨会话对照） |
| quarter-handoff | 交接清单是否准确记录两份报表的实报月、缺报月，并保留已发布报表。两份的合计和平均相同。 |

## DeepSeek 接手入口

2026-11-24 交接。评测实现位于 `codex/first-ab-evidence` 分支的 `d0b40bc`。在源仓库根目录运行 `git merge-base --is-ancestor d0b40bc HEAD`，退出码 0 表示当前检出已包含这批实现。该提交增加了两阶段运行、Windows MXC runner 配置和月份回写场景。全量回归命令为 `python -X utf8 -B -m unittest discover -s tests`，交付时 53 项通过。

| 接手时要核对的问题 | 从哪里核对 |
| --- | --- |
| 上轮 DeepSeek 已经测了什么？ | 11 月 23 日的五组对照共 36 次运行，使用派生会话，缺少原始读取轨迹。场景、分组与证据边界见[历史记录](VALIDATION.md)。 |
| Codex 补齐了哪段证据？ | 11 月 24 日用 `gpt-6.2-sol` 跑通一对真实 A → B。先看 `stage-a-audit.json` 核对 A 交付的行为，再看两组 `B/trace.jsonl` 核对 B 读到的规则，最后看 `drift-report.json` 核对最终验收和早先受阻的试验。原始文件的位置见[本轮记录](VALIDATION.md#2026-11-24--带轨迹的冷接手与月份回写复测)。 |
| 为什么保留现有 Skill？ | 评分器能检出把“仅二月上报”写成“二月缺报”的历史错误。给出逐月 CSV 明细后，基线和候选各 3/3 通过。工作簿交接的原始错误与本次合成任务的可见信息不同。六次结果汇总在同一试验目录的 `quarter-report.json`。 |

**下一步取决于要验证的问题。** 若要补 DeepSeek 自身的冷接手轨迹，先确认其运行器能从 stdin 接收任务、每次创建新会话、写出最终答复和可核查的工具轨迹，再按[两阶段复跑步骤](#复跑两阶段冷接手)做一对。仓库内已实测的 MXC 配置调用的是 Codex；DeepSeek 的新结果应单独记录模型路由和 runner 版本。

若重点是找出真实交接为何写反月份，优先对照接手者当时看到的汇总、可访问的工作簿和最终任务文字。先确认基线在哪种材料条件下会重现错误，再决定是否调整 `change-design`。新的观察追加到验证记录，注明可复核的试验、环境和未验证项。[11 月 19 日原稿与复查路径](VALIDATION.md#只在任务内增加回写提示--2026-11-19)

## 准备试验

从本仓库根目录执行。每次试验使用新的目录，建议放在系统临时目录，不能复用已执行目录。

```sh
python evals/run.py prepare --case python-cli --variant baseline --trial <临时目录>/cli-baseline-1
python evals/run.py prepare --case python-cli --variant candidate --workflow <候选工作流仓库> --trial <临时目录>/cli-candidate-1
```

`baseline` 保留项目原有入口和规范。`current`、`candidate` 分别传入对应工作流副本，加入其 Skills 和入口链接。两种版本复制实际文件并计算摘要，包括尚未提交的修改。任务、原始项目、工作流、评分器和 runner 都有摘要，以便识别不同实验条件。宿主的全局 Skills、模型、环境变量和权限必须保持一致并另行记录，基线不意味着关闭宿主的所有内置能力。

将上述 `--case` 值替换为 `cold-handoff-cli`，可以复跑一次无聊天历史的交接。项目内含已发布规则、待确认方案、只验证旧版本普通导入的历史回执，以及一项尚未完成的任务。日常语法检查可以通过，完整验证另有项目原生命令。

## 运行 AI

使用自己的受信任 runner 配置。下面是 Codex CLI 示例，使用本机默认模型，不嵌入凭据：

```json
{
  "label": "codex-local-default",
  "environment": "填写模型、CLI版本、系统、运行时及全局Skills配置",
  "argv": ["codex", "exec", "--ephemeral", "--ignore-user-config", "--skip-git-repo-check", "--json", "--sandbox", "workspace-write", "-C", "{workspace}", "-o", "{response}", "-"]
}
```

```sh
python evals/run.py run --trial <试验目录> --runner <runner.json> --timeout 600
```

任务通过标准输入传入，参数数组直接执行。`{workspace}` 和 `{response}` 必须各占一个数组元素。runner 应读取标准输入，在限定工作区内执行任务。试验目录只是工作隔离，文件系统权限由所用 Agent 宿主或容器提供。不要将试验运行器连接到生产环境或赋予额外凭据。

原始过程保存在 `trace.jsonl`、`stderr.log` 和 `response.md`，执行状态在 `execution.json`。成功退出后运行外部验收，结果在 `grade.json` 和 `grade.log`。runner 成功退出不等于任务通过。退出码 0 表示验收通过，1 表示验收失败，2 表示运行器失败或明确的环境受阻。缺少评分器运行条件也返回 2。

### 复跑两阶段冷接手

用同一份 runner 配置运行下面两组。将 `<trial>` 替换为系统临时目录下的新路径，将 `<runner.json>` 替换为上面配置的路径，固定 CLI 版本和模型。runner 每次启动都须创建新会话，能将最终答复写入 `{response}`。配置只放参数和环境说明，凭据由宿主管理。

支持 MXC 的 Windows 机器可使用 [本轮配置](runners/codex-windows-mxc.json)。先用 `codex --version` 核对可执行文件，在合成项目内运行 `codex -c windows.sandbox=mxc sandbox --include-managed-config --permission-profile :workspace -- cmd.exe /d /c type AGENTS.md` 确认沙箱可读项目入口。配置里的 `codex` 由 PATH 解析；有多个版本时可在本地副本中填写所选可执行文件的绝对路径。

```sh
python evals/run.py prepare --case drift-cli --variant baseline --trial <trial>/baseline
python evals/run.py prepare --case drift-cli --variant candidate --trial <trial>/candidate
python evals/run.py run --trial <trial>/baseline --runner <runner.json>
python evals/run.py run --trial <trial>/candidate --runner <runner.json>
python evals/run.py report <trial>/baseline <trial>/candidate --output <trial>/report.json
```

每组的 A 和 B 是两个 runner 进程，各有独立的提示、答复、轨迹和执行状态，共用同一工作区。`--timeout` 按阶段计时。A 成功退出后，`A/workspace/` 保存交接时的项目文件，沿用 trial 快照对 Git 和构建缓存的排除规则。B 只接收续做提示。可对照快照与最终工作区，检查 B 的轨迹里是否有成功读取交接记录的命令。两阶段提示共同参与报告分组，完整 runner 配置保存在 trial 根目录。任一阶段运行失败即停止，两个阶段都成功退出后才做最终行为验收。

Python 场景无需第三方包。Java 场景需要 JDK 17、Maven 或 Gradle，混合场景还需要 Node 22。可用 `EVAL_MAVEN`、`EVAL_GRADLE` 指定构建工具路径，`JAVA_HOME` 指定 JDK。构建依赖可能需要联网下载。应先在相同环境验证原始项目能够构建，再比较 AI 结果。被测程序删除文件、超时或输出错误属于任务失败。

## 评分与比较

```sh
python evals/run.py grade --trial <试验目录>
python evals/run.py report <基线试验目录> <候选试验目录> --output <结果.json>
```

评分器位于试验工作区之外。Python 直接观察命令行行为；Java 在独立临时副本中加入验收测试，并核对实际测试报告，避免只看构建退出码。混合场景还启动后端并从 Node 调用，结束后停止服务。`grade` 本身不证明有 AI 参与，手工修复的正例只能用于验证评分器。

`cold-handoff-cli` 分别给出行为、现行规则、历史保留、证据一致性和原任务链接的检查结果。评分器用自己的输入重跑 CLI，并核对回执范围、检查结果和当前实现摘要。原任务必须通过工作区内可解析的相对链接指向此次回执。会话实际执行了哪些步骤，仍以 runner 日志为依据。

报告按相同项目、任务、runner 和评分器分组，保留每次结果、耗时、文件改动和新增设计文件数量。token 只从运行器提供的事件读取，成本和人工纠正次数缺少可靠来源时为 null。新建设计文件数量只是观察指标，不能单独代表质量。

同一个任务每种配置建议至少重复三次，报告所有失败和受阻试验，不只挑成功结果。比较完成率、遗漏的验收、人工纠正、时间和成本，并人工抽查轨迹中的验证选择与多余工作。少量试验只能作为回归信号，不能据此宣称模型或工作流整体更优。

新规则先对应一个实际失败案例，新增能暴露该失败的任务，再对照验证改进。业务项目的私有代码、地址和数据不进入公共样例。

描述选择、设计深度、图与契约一致性及续做行为，可补充使用 [设计工作流评审场景](design-review.md)。这些场景需要独立检查产物和过程，尚未接入自动评分，不将图数量或标题匹配视为效果证据。

## 用删减对照检查流程成本

当一份文档、一个字段或一个步骤的价值有争议，可以先明确接手者因此应当更容易作出的判断或完成的动作，再用删减对照验证。

1. 从同一项目基线准备两组干净副本。保持任务、运行环境、模型、工具权限和必要事实一致，只移除待评估的材料或步骤。先核对文件差异。如果材料包含唯一的事实或未决事项，单独评估它们的保存位置。
2. 开启独立会话，由实际工作区开始。同一个任务可交换两组执行顺序，按既有评测方法重复。检查定位、命令选择、实际结果、回写及历史行为是否保留。
3. 环境受阻时仍可单独验证工程可运行性，或比较会话根据两组文档材料作出的判断。工程执行、材料判断与完整接手各自记录。能选对命令只支持判断层面的结论。
4. 对照结果用于决定保留、移动或简化该内容。如果收益集中在一条信息，可以再测一次，只把这条信息移入现有规范或任务。样例和次数有限时，把结论限于本次观察。
