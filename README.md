# AI 项目接入与需求设计

`project-onboard` 接入已有的 Java、Python、Node 或混合技术栈项目，也可以从零创建 Spring 工程。团队通过 `AGENTS.md` 找到项目开发规范和各模块的实际验证命令。`change-design` 用一套需求设计和验收流程支持 Web、CLI、公共库、后台任务等项目。

## 使用

| 现在要做什么 | 在目标项目里可以直接这样说 |
| --- | --- |
| 第一次接入已有项目 | “用 project-onboard 找到订单模块的入口和实际验证命令，沿用团队的开发说明。” |
| 改一个已有行为 | “导出应当只含当前筛选结果。先找对应需求，更新受影响的规则和验收。” |
| 从中断处继续 | “接着做导出需求。核对原任务、当前改动和上次验证，完成下一个可验证的结果。” |
| 更新项目里已登记的工作流 | “更新工作流，先预览本项目的定制和上游改动。” |

已有可信的本仓库 Git 副本时，可以从目标项目根目录直接安装并登记版本：

```sh
python <上游副本>/skills/project-onboard/scripts/workflow_update.py --source <上游副本> --revision <提交或标签> --install project-onboard change-design
python <上游副本>/skills/project-onboard/scripts/workflow_update.py --doctor
```

安装会保留已有项目指令，追加工作流入口，并配置基本检查。预览加 `--dry-run`，Claude Code 加 `--tool claude`。已有定制发生冲突时停止。详细行为见 [安装与更新](skills/project-onboard/references/workflow-update.md)。

上述命令已安装两个 Skill。若希望个人跨项目调用，也可以把需要的 Skill 整个目录复制到对应工具的个人技能目录。

| 工具 | 个人技能目录 | 仓库技能目录 |
|---|---|---|
| Codex | `~/.agents/skills/` | `.agents/skills/` |
| Claude Code | `~/.claude/skills/` | `.claude/skills/` |

在目标工作区调用 `project-onboard`，例如：

- “用 project-onboard 在当前空目录创建一个 Spring 后端，使用 Maven。”
- “用 project-onboard 创建一个 Spring 后端，参考旁边的订单项目的模块组织和测试写法。”
- “用 project-onboard 接入这个现有 Spring 项目，先探查并给我接入草案。”

## 两条路径

- **创建 Spring 项目**：确定技术选择，按需借鉴用户提供的参考项目，生成构建配置、应用入口和基础测试，使用环境提供的 Maven 或 Gradle 验证。新项目无需 Wrapper。
- **接入已有项目**：根据构建清单、锁文件和 CI 确认工程边界，沿目标模块的一条真实链路核对行为和验证。把日常使用的结论写入既有开发文档，简单项目可直接写进根 `AGENTS.md`。只有冲突、未决事项或分批接入需要持续跟踪时，才长期保留接入摘要。见 [接入探查与交付](skills/project-onboard/references/onboarding.md)。

基础开发规范和 Java / Spring、Python、Node 的探查参考随接入 Skill 分发。接入方案见 [设计说明](DESIGN.md)。

Maven 项目可从 Skill 目录运行 `python scripts/maven_preflight.py --project <项目根目录> --java-version 17`，核对实际 JDK。可加 `--verify` 运行完整构建，或在 `--` 后传入项目自己的 Maven 参数。例如 `-- -B -Dtest=ExampleTest test` 可在选定的 JDK 下运行指定测试。

## 从需求到实现

启用 [change-design](skills/change-design/) 后，在目标项目里直接描述需求，例如「给看板增加按部门筛选和导出，先出设计」。

需要独立设计时，AI 从 `AGENTS.md` 进入，核对现有行为、调用入口和项目规范，再用 [设计模板](skills/change-design/assets/design.md) 创建或更新设计。默认位置为 `docs/design/Req-YYYYMMDD-需求名称/design.md`。设计记录业务规则、验收、技术方案和评审决定，按需补充 [技术章节](skills/change-design/references/design-sections.md)。前后端或多个仓库共同交付同一能力时，共用主设计和验收编号，各模块沿用自己的验证命令。

模板在对应小节提示何时使用时序图、ER 图、状态图、模块关系图或交互原型，并按影响展开异常处理、契约、数据迁移、质量要求和发布恢复。简单变更只保留必要内容，复杂契约与附件由主设计链接。评审核对图、业务规则、契约、数据约束与验收是否一致，图能渲染不等于方案正确。

先按变更影响选择工作量。预期清楚、影响局部时，可直接实施并验证。已有对应设计且预期变化，就更新原设计中的规则和验收。修复实现偏差时，引用原验收，在任务或 PR 中记录回归结果。需要以后接手的事项留下能从项目找到的记录。高风险变更补充评审、兼容、发布和恢复安排。

当前行为不清时先探查或复现，关键技术假设不明时先做有边界的实验，证据足够后直接实现。新证据可使方案返回调查或调整；已有能力能解决问题时优先说明复用方式。重要决定保留依据、适用条件和重新评估条件，普通细节不增加记录。功能验收通过与实际收益已验证分别说明。

两个 Skill 按职责选择，日常变更不必重复接入项目。设计时读取技术章节，实施或续做时读取 [小步实施与验收](skills/change-design/references/implementation.md)，新建或演进需求、维护看板时再读取 [需求演进与索引](skills/change-design/references/requirement-lifecycle.md)。每个实施增量按“选择结果 → 确定验证方法 → 实现 → 验证 → 记录证据 → 下一项”推进，在已有授权内连续工作。实际结果附环境及对应版本或工作区范围，命令和 PR 链接本身不代表通过；局部验证后仍按影响补充整体验收。

评审时可以直接说「把导出范围改成当前筛选结果」，AI 更新原设计并指出受影响的验收项。决定实施时说「按这份设计实现」。换会话时从已有设计、任务和验证证据恢复。跨工作区交接附接手者可访问的分支、提交或 PR，注明最后验证和下一步。

一份设计默认用小节组织。有多个实施增量时拆任务。局部契约或取舍需要单独维护时，把细节移到专题页，从原 `design.md` 链接。专题共用一份验收与任务记录。能够独立交付和维护的业务能力可拆为关联需求。并行变更合并前核对预期、任务引用、编号和生效条件。见 [需求演进与索引](skills/change-design/references/requirement-lifecycle.md)。

每个需求目录配一份 [任务看板](skills/change-design/assets/tasks.md)，按增量记录本次计划、实际改动和证据。总看板显示当前任务、已完成增量、需求关系和阻塞原因。隔离测试与正式数据验收可以单独交付时，分别记录进度。

采用本模板的项目可用 [看板工具](skills/change-design/scripts/requirements.py) 刷新或检查 `docs/design/README.md`。例如把 Skill 放进目标仓库的 `.agents/skills/` 后，从目标仓库根目录执行以下命令。辅助脚本使用 Python 3.9 或更新版本。

```sh
python .agents/skills/change-design/scripts/requirements.py --write
python .agents/skills/change-design/scripts/requirements.py --check
```

已有手写需求索引时，在希望显示看板的位置选定[自动更新区域](skills/change-design/references/requirement-lifecycle.md#看板与检查)，区域外继续由团队维护。

评审指定需求时，可运行 `python .agents/skills/change-design/scripts/requirements.py --review "Req-YYYYMMDD-需求名称"`。它检查「需求与验收」中的每条编号是否有关联任务或书面验证安排。覆盖缺口只输出提示，验收结果由实际验证和评审确认。

修改已有需求时，追加 `--base <上次确认的提交>` 可对照工作区，逐条查看增删或改写的预期，以及引用它们的当前任务。例如 AC-1 从「缺月留空」改成「缺月填 0」后，评审者能看到上一轮已完成的 T1，决定需要重跑哪个导出样例。

## 更新工作流

按 [同步参考](skills/project-onboard/references/workflow-update.md) 在目标项目的 `.ai-workflow.json` 登记上游、启用的 Skill、源提交、文件摘要和验证命令，在 `AGENTS.md` 保留更新入口。以后可说「更新工作流」，让 AI 获取确定版本并使用更新工具预览和应用。出现冲突时保持原状，验证失败时回退，强制中断后可恢复。目标项目继续维护自己的开发规范、构建配置和需求记录。

## 验证接入包

AI 任务效果使用 [真实任务评测](evals/README.md)，提供 Python CLI、续做、Maven/Spring、Gradle＋Node 的隔离场景和外部验收，可比较原有项目指令、当前版和候选版。脚本测试通过与 AI 任务效果分别记录。

设计深度、图示选择与续做行为另用 [设计工作流评审场景](evals/design-review.md) 检查，评审实际产物和过程，不用标题或图的数量代替质量。

在本仓库根目录运行 `python -B -m unittest discover -s tests`。测试覆盖看板生成、编号与引用校验、Markdown 格式容忍、验收安排提示，以及 Maven 参数和 JDK 环境的传递。更新工具使用隔离 Git 仓库验证预览、定制保留、冲突、回退和中断恢复。运行测试需要 Python 和 Git，无需访问网络。
