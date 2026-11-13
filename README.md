# Java / Spring AI 项目接入

`project-onboard` 帮助开发者从零创建 Java / Spring 项目，或探查已有项目并整理开发规范。接入后，团队从仓库里的 `AGENTS.md` 找到开发文档和验证命令，继续使用项目自己的构建和 CI。

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

- **创建项目**：确定技术选择，按需借鉴用户提供的参考项目，生成构建配置、应用入口和基础测试，使用环境提供的 Maven 或 Gradle 验证。新项目无需 Wrapper。
- **接入已有项目**：读现有文档、配置、构建和 CI，沿一条真实业务链核对约定，记录证据和验证结果。已有文档原地引用，缺少项目开发规范时默认使用 `docs/development.md`。

基础开发规范与 Java / Spring 参考随接入 Skill 分发。接入方案见 [第一版设计](DESIGN.md)。

Maven 项目可从 Skill 目录运行 `python scripts/maven_preflight.py --project <项目根目录> --java-version 17`，核对实际 JDK。可加 `--verify` 运行完整构建，或在 `--` 后传入项目自己的 Maven 参数。例如 `-- -B -Dtest=ExampleTest test` 可在选定的 JDK 下运行指定测试。

## 从需求到实现

把 [change-design](skills/change-design/) 按上表放入同一技能目录，在目标项目里直接描述需求，例如「给看板增加按部门筛选和导出，先出设计」。

AI 从 `AGENTS.md` 进入，核对现有代码、接口和数据，再用 [设计模板](skills/change-design/assets/design.md) 创建或更新一份设计。项目已有约定就沿用，默认建立 `docs/design/Req-YYYYMMDD-需求名称/design.md`。已有工单编号记录在文档顶部。文档保留业务规则、验收、时序图、ER 图、表结构、接口、待确认问题与评审决定。

评审时可以直接说「把导出范围改成当前筛选结果」，AI 更新同一份设计并指出受影响的验收项。决定实施时说「按这份设计实现」。换会话时可以描述功能，AI 查找已有设计，从已确认的方案、验收项和关联任务继续。实现后把测试结果写回，PR 引用设计。

后续调整直接描述想改的行为，AI 先查项目概览、需求索引、关联设计和代码。同一业务能力在原需求下追加实施增量，并根据已生效的规则更新本次设计。较长的描述先按独立业务结果拆解，明确前置依赖和关联需求。

每个需求目录配一份 [任务看板](skills/change-design/assets/tasks.md)，按增量记录本次计划、实际改动和证据。总看板显示当前任务、已完成增量、需求关系和阻塞原因。隔离测试与正式数据验收可以单独交付时，分别记录进度。

采用本模板的项目可用 [看板工具](skills/change-design/scripts/requirements.py) 刷新或检查 `docs/design/README.md`。例如把 Skill 放进目标仓库的 `.agents/skills/` 后，从目标仓库根目录执行以下命令。两个脚本均使用 Python 3.9 或更新版本。

```sh
python .agents/skills/change-design/scripts/requirements.py --write
python .agents/skills/change-design/scripts/requirements.py --check
```

## 验证接入包

在本仓库根目录运行 `python -B -m unittest discover -s tests`。测试覆盖看板生成、阻塞记录、路径校验，以及 Maven 参数和 JDK 环境的传递。运行这些测试只需要 Python。
