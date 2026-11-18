---
name: project-onboard
description: Create a Spring project, establish or repair project development guidance from actual repository evidence, or install, diagnose, and update workflow skills. Use for project initialization, onboarding existing Java, Python, Node, or mixed repositories, maintaining AGENTS.md and development guidance, and workflow installation or maintenance.
---

# 项目接入

让下一个开发者或 AI 找到代码入口、适用规范和可复现的验证命令，以项目已有约定、构建配置和 CI 为依据。探查或维护开发规范时参照 [基础开发规范](references/base-standards.md)；仅安装、检查或更新工作流时读取同步参考即可。

## 选择入口

- **创建项目**：区分目标目录和参考项目。目标目录已有业务工程时核对目标与范围。
- **接入已有项目**：按 [接入探查与交付](references/onboarding.md) 限定范围并取证，交付探查结论，按已确认的范围更新项目文档。
- **更新已安装工作流**：按 [同步参考](references/workflow-update.md) 使用登记清单和更新工具，先预览，再在无冲突时同步和验证。
- **安装或检查工作流**：按 [安装与检查](references/workflow-update.md) 使用 `--install` 一并安装和登记版本，使用 `--doctor` 离线检查接入状态。项目文档仍根据实际探查结果维护。
- 用户只要求设计或探查时，交付草案或报告。已明确要求创建或落地且范围清楚时，继续执行。只询问会实质影响结果的未决问题。

## 创建项目

1. 确认用途、目标目录和技术栈。新建 Spring 项目按 [Java / Spring 参考](references/java-spring.md) 确认项目名、包名、JDK、Spring Boot 及 Maven 或 Gradle 的兼容性。优先使用用户选择和团队基线，按首个场景引入依赖。其他技术栈沿用用户要求或团队的初始化方式。
2. 有参考项目时只读核对模块组织、依赖、测试和 CI，列出借鉴项及调整理由。参考项目的私有配置、业务数据和专属代码留在原项目。
3. 生成最小构建配置、应用或调用入口及基础测试。新建 Spring 项目用环境提供的 Maven 或 Gradle，交付前确认生成器未留下 Wrapper 文件和目录。
4. 用目标环境验证构建、测试和启动或调用，结束本次启动的进程。需要服务或凭据时使用隔离测试环境。记录未运行的验证及原因。
5. 写入项目入口与最小开发指引。项目维护者决定长期约定，AI 按现有项目决定、团队基线或工作流默认建议起草。任务包含 CI 时，复用团队配置或把实际验证命令接入现有 CI。

## 接入已有项目

1. 先核对仓库级入口、构建和 CI，再深入目标模块和一条代表性链路。依据需要读取 [Java / Spring](references/java-spring.md)、[Python](references/python.md) 或 [Node / 前端](references/node.md)。
2. 执行适用的项目验证，分别报告构建、实际执行的测试、跳过项和未覆盖环境。
3. 交付覆盖范围、证据、结果及文档去向。冲突、未决事项或分批接入需要持续跟踪时，用现有记录承载，缺少位置时按需建接入摘要。重复接入针对实际变化和缺口。

## 写入项目和交付

- 根 `AGENTS.md` 写项目定位、开发规范与需求索引、关键验证入口。模块有独立约定时，在模块的 `AGENTS.md` 或开发文档中记录差异，根入口链接过去。团队需要 Claude Code 入口时，可在 `CLAUDE.md` 引用 `AGENTS.md`。
- 优先沿用项目自己的开发规范。约定少、入口集中时，可在根 `AGENTS.md` 直接记录入口、工作目录、运行时和已验证命令。模块的代码入口、验证命令或环境要求需要分别说明时，用 [开发规范模板](assets/development.md) 补充 `docs/development.md`，由根入口链接。开发规范记长期约定，单次变更的方案、任务与验收存入需求记录。
- 在项目开发规范中说明轻量变更、功能设计和高风险评审的适用范围，以及已启用的看板命令。若项目要用「更新工作流」同步仓库内的 Skill，按 [同步参考](references/workflow-update.md) 建立版本清单，根入口只记录调用方式。
- 确认的工程约定归入开发规范。跨需求复用的业务概念和规则优先放在项目已有业务说明或契约，开发入口和需求按需引用。
