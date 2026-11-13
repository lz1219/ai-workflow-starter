# AI 项目接入与需求设计

`project-onboard` 接入已有的 Java、Python、Node 或混合技术栈项目，也可以从零创建 Spring 工程。团队通过 `AGENTS.md` 找到项目开发规范和各模块的实际验证命令。`change-design` 用一套需求设计和验收流程支持 Web、CLI、公共库、后台任务等项目。

## 使用

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

AI 从 `AGENTS.md` 进入，核对现有行为、调用入口和项目规范，再用 [设计模板](skills/change-design/assets/design.md) 创建或更新设计。默认位置为 `docs/design/Req-YYYYMMDD-需求名称/design.md`。设计记录业务规则、验收、技术方案和评审决定，按需补充 [技术章节](skills/change-design/references/design-sections.md)。前后端或多个仓库共同交付同一能力时，共用主设计和验收编号，各模块沿用自己的验证命令。

评审时可以直接说「把导出范围改成当前筛选结果」，AI 更新同一份设计并指出受影响的验收项。决定实施时说「按这份设计实现」。换会话时可以描述功能，AI 查找已有设计，从已确认的方案、验收项和关联任务继续。实现后把测试结果写回，PR 引用设计。

后续调整直接描述想改的行为，AI 先查项目概览、需求索引、关联设计和代码。同一业务能力在原需求下追加实施增量，并根据已生效的规则更新本次设计。较长的描述先按独立业务结果拆解，明确前置依赖和关联需求。

每个需求目录配一份 [任务看板](skills/change-design/assets/tasks.md)，按增量记录本次计划、实际改动和证据。总看板显示当前任务、已完成增量、需求关系和阻塞原因。隔离测试与正式数据验收可以单独交付时，分别记录进度。

采用本模板的项目可用 [看板工具](skills/change-design/scripts/requirements.py) 刷新或检查 `docs/design/README.md`。例如把 Skill 放进目标仓库的 `.agents/skills/` 后，从目标仓库根目录执行以下命令。两个脚本均使用 Python 3.9 或更新版本。

```sh
python .agents/skills/change-design/scripts/requirements.py --write
python .agents/skills/change-design/scripts/requirements.py --check
```

评审指定需求时，可运行 `python .agents/skills/change-design/scripts/requirements.py --review "Req-YYYYMMDD-需求名称"`。它检查「需求与验收」中的每条编号是否有关联任务或书面验证安排。覆盖缺口只输出提示，验收结果由实际验证和评审确认。

## 更新工作流

在目标项目的 `AGENTS.md` 按 [同步参考](skills/project-onboard/references/workflow-update.md) 登记上游、启用的 Skill、源提交和验证命令。以后可在目标项目里说「更新工作流」，让 AI 比较上游与本地、同步已登记的目录并验证。目标项目继续维护自己的开发规范、构建配置和需求记录。

## 验证接入包

在本仓库根目录运行 `python -B -m unittest discover -s tests`。测试覆盖看板生成、阻塞记录、验收覆盖提示、路径校验，以及 Maven 参数和 JDK 环境的传递。运行这些测试只需要 Python。
