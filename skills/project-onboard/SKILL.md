---
name: project-onboard
description: Onboard existing projects by identifying module entry points, tooling, CI, and verified commands, or scaffold a new Spring project with Maven or Gradle. Use for project initialization, repository discovery, or drafting AGENTS.md and project development guidance across Java, Python, Node, and mixed repositories.
---

# 项目接入

让下一个开发者或 AI 找到代码入口、适用规范和可复现的验证命令。参照 [基础开发规范](references/base-standards.md)，以项目已有约定、构建配置和 CI 为依据。

## 选择入口

- **创建项目**：区分目标目录和参考项目。目标目录已有业务工程时核对目标与范围。
- **接入已有项目**：先只读探查，再提交草案，按已确认的范围更新项目文档。
- 用户只要求设计或探查时，交付草案或报告。已明确要求创建或落地且范围清楚时，继续执行。只询问会实质影响结果的未决问题。

## 创建项目

1. 确认用途、目标目录和技术栈。新建 Spring 项目按 [Java / Spring 参考](references/java-spring.md) 确认项目名、包名、JDK、Spring Boot 及 Maven 或 Gradle 的兼容性。优先使用用户选择和团队基线，按首个场景引入依赖。其他技术栈沿用用户要求或团队的初始化方式。
2. 有参考项目时只读核对模块组织、依赖、测试和 CI，列出借鉴项及调整理由。参考项目的私有配置、业务数据和专属代码留在原项目。
3. 生成最小构建配置、应用或调用入口及基础测试。新建 Spring 项目用环境提供的 Maven 或 Gradle，交付前确认生成器未留下 Wrapper 文件和目录。
4. 用目标环境验证构建、测试和启动或调用，结束本次启动的进程。需要服务或凭据时使用隔离测试环境。记录未运行的验证及原因。
5. 写入项目入口和开发规范。任务包含 CI 时，复用团队配置或把实际验证命令接入现有 CI。

## 接入已有项目

1. 从根目录及目标模块的 `AGENTS.md`、`CLAUDE.md`、README、贡献指南和链接开始。把已有开发文档原地引用或补充。
2. 根据构建清单、模块声明、锁文件和 CI 的工作目录识别实际模块。按模块确认运行时、构建或依赖工具、应用或调用入口、快速检查和 CI 完整检查。工作区或多模块构建优先核对其统一入口。依据需要读取 [Java / Spring](references/java-spring.md)、[Python](references/python.md) 或 [Node / 前端](references/node.md)。
3. 沿代表性链路核对入口、业务规则和测试，例如界面操作、HTTP、CLI、公开库、消息或批处理。涉及多个模块时标出边界、共享契约和各自入口。记录路径、符号或配置等证据，注明事实、待确认和冲突。
4. 核对执行目录、运行时和测试资源后运行已有验证。保留项目已有 Wrapper、工具链和 CI 入口。记录基线、命令、结果与缺少的环境。区分依赖解析失败、环境未准备和测试失败。
5. 给出接入草案，列出覆盖范围、验证结果和拟复用或更新的文件。重复接入按现状补齐缺口。

## 写入项目和交付

- 根 `AGENTS.md` 写项目定位、开发规范与需求索引、关键验证入口。模块有独立约定时，在模块的 `AGENTS.md` 或开发文档中记录差异，根入口链接过去。团队需要 Claude Code 入口时，可在 `CLAUDE.md` 引用 `AGENTS.md`。
- 优先沿用项目自己的开发规范。缺失时用 [开发规范模板](assets/development.md) 创建 `docs/development.md`。记录各模块的入口、工作目录、运行时、实际命令、环境要求及代码参考。团队长期约定保存在项目内或引用固定版本。
- 在项目开发规范中说明设计入口、评审规则和看板命令。若项目要用「更新工作流」同步仓库内的 Skill，按 [同步参考](references/workflow-update.md) 记录来源、启用目录、当前源提交和验证命令。
- 交付时列出新增或复用的文档及验证结果。详细探查证据留在接入草案或接入 PR。
