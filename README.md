# AI 项目接入与需求设计

`project-onboard` 接入已有的 Java、Python、Node 或混合技术栈项目，也可以从零创建 Spring 工程。团队通过 `AGENTS.md` 找到项目开发规范和各模块的实际验证命令。`change-design` 用一套需求设计和验收流程支持 Web、CLI、公共库、后台任务等项目。

## 使用

已有可信的本仓库 Git 副本时，可以从目标项目根目录直接安装并登记版本：

```sh
python <上游副本>/skills/project-onboard/scripts/workflow_update.py --source <上游副本> --revision <提交或标签> --install project-onboard change-design
python <上游副本>/skills/project-onboard/scripts/workflow_update.py --doctor
```

安装会保留已有项目指令，追加工作流入口，并配置基本检查。预览加 `--dry-run`，Claude Code 加 `--tool claude`。已有定制发生冲突时停止。详细行为见 [安装与更新](skills/project-onboard/references/workflow-update.md)。

把 [project-onboard](skills/project-onboard/) 整个目录放到工具的技能目录下。个人配置一次即可在多个项目中调用。

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
- **接入已有项目**：根据构建清单、锁文件和 CI 按模块识别运行时、调用入口和验证方式，沿一条实际链路核对约定。缺少项目开发规范时默认使用 `docs/development.md`，各模块有独立约定时在根 `AGENTS.md` 链接。

基础开发规范和 Java / Spring、Python、Node 的探查参考随接入 Skill 分发。接入方案见 [设计说明](DESIGN.md)。

Maven 项目可从 Skill 目录运行 `python scripts/maven_preflight.py --project <项目根目录> --java-version 17`，核对实际 JDK。可加 `--verify` 运行完整构建，或在 `--` 后传入项目自己的 Maven 参数。例如 `-- -B -Dtest=ExampleTest test` 可在选定的 JDK 下运行指定测试。

## 从需求到实现

把 [change-design](skills/change-design/) 按上表放入同一技能目录，在目标项目里直接描述需求，例如「给看板增加按部门筛选和导出，先出设计」。

需要独立设计时，AI 从 `AGENTS.md` 进入，核对现有行为、调用入口和项目规范，再用 [设计模板](skills/change-design/assets/design.md) 创建或更新设计。默认位置为 `docs/design/Req-YYYYMMDD-需求名称/design.md`。设计记录业务规则、验收、技术方案和评审决定，按需补充 [技术章节](skills/change-design/references/design-sections.md)。前后端或多个仓库共同交付同一能力时，共用主设计和验收编号，各模块沿用自己的验证命令。

模板在对应小节提示何时使用时序图、ER 图、状态图、模块关系图或交互原型，并按影响展开异常处理、契约、数据迁移、质量要求和发布恢复。简单变更只保留必要内容，复杂契约与附件由主设计链接。评审核对图、业务规则、契约、数据约束与验收是否一致，图能渲染不等于方案正确。

先按影响选择工作量。预期清楚的局部调整在任务或 PR 中记录方案和验证即可。需要拆分实施或跨模块协调的功能维护设计与任务，高风险变更补充评审、兼容、发布和恢复安排。用户明确要求设计时交付设计。

两个 Skill 按职责选择，日常变更不必重复接入项目。设计时读取技术章节，实施或续做时读取 [小步实施与验收](skills/change-design/references/implementation.md)，新建或演进需求、维护看板时再读取 [需求演进与索引](skills/change-design/references/requirement-lifecycle.md)。每个实施增量按“选择结果 → 确定验证方法 → 实现 → 验证 → 记录证据 → 下一项”推进，在已有授权内连续工作。实际结果附环境及对应版本或工作区范围，命令和 PR 链接本身不代表通过；局部验证后仍按影响补充整体验收。

评审时可以直接说「把导出范围改成当前筛选结果」，AI 更新同一份设计并指出受影响的验收项。决定实施时说「按这份设计实现」。换会话时可以描述功能，AI 查找已有设计，从已确认的方案、验收项和关联任务继续。实现后把测试结果写回，PR 引用设计。

后续调整直接描述想改的行为，AI 先查项目概览、需求索引、关联设计和代码。同一业务能力在原需求下追加实施增量，并根据已生效的规则更新本次设计。较长的描述先按独立业务结果拆解，明确前置依赖和关联需求。

每个需求目录配一份 [任务看板](skills/change-design/assets/tasks.md)，按增量记录本次计划、实际改动和证据。总看板显示当前任务、已完成增量、需求关系和阻塞原因。隔离测试与正式数据验收可以单独交付时，分别记录进度。

采用本模板的项目可用 [看板工具](skills/change-design/scripts/requirements.py) 刷新或检查 `docs/design/README.md`。例如把 Skill 放进目标仓库的 `.agents/skills/` 后，从目标仓库根目录执行以下命令。辅助脚本使用 Python 3.9 或更新版本。

```sh
python .agents/skills/change-design/scripts/requirements.py --write
python .agents/skills/change-design/scripts/requirements.py --check
```

评审指定需求时，可运行 `python .agents/skills/change-design/scripts/requirements.py --review "Req-YYYYMMDD-需求名称"`。它检查「需求与验收」中的每条编号是否有关联任务或书面验证安排。覆盖缺口只输出提示，验收结果由实际验证和评审确认。

## 更新工作流

按 [同步参考](skills/project-onboard/references/workflow-update.md) 在目标项目的 `.ai-workflow.json` 登记上游、启用的 Skill、源提交、文件摘要和验证命令，在 `AGENTS.md` 保留更新入口。以后可说「更新工作流」，让 AI 获取确定版本并使用更新工具预览和应用。出现冲突时保持原状，验证失败时回退，强制中断后可恢复。目标项目继续维护自己的开发规范、构建配置和需求记录。

## 验证接入包

AI 任务效果使用 [真实任务评测](evals/README.md)，提供 Python CLI、续做、Maven/Spring、Gradle＋Node 的隔离场景和外部验收，可比较原有项目指令、当前版和候选版。脚本测试通过与 AI 任务效果分别记录。

设计深度、图示选择与续做行为另用 [设计工作流评审场景](evals/design-review.md) 检查，评审实际产物和过程，不用标题或图的数量代替质量。

在本仓库根目录运行 `python -B -m unittest discover -s tests`。测试覆盖看板生成、编号与引用校验、Markdown 格式容忍、验收安排提示，以及 Maven 参数和 JDK 环境的传递。更新工具使用隔离 Git 仓库验证预览、定制保留、冲突、回退和中断恢复。运行测试需要 Python 和 Git，无需访问网络。
