---
name: project-onboard
description: Create a Java or Spring project from scratch, optionally using a reference repository, or onboard an existing Java or Spring project by inspecting its code, documentation, build and CI. Use for project initialization, project discovery and onboarding, or drafting project development standards and AGENTS.md. 项目初始化、旧项目探查、开发规范接入时使用。
---

# Java / Spring 项目接入

目标是让下一个开发者或 AI 知道到哪里改、遵循哪些约定、怎么验证。读取 [基础开发规范](references/base-standards.md) 和 [Java / Spring 参考](references/java-spring.md)。项目已有的约定和构建配置决定具体做法，冲突时把证据和需要确认的问题列出来。

## 选择入口

- **创建项目**：用户要初始化一个新工程。确认目标目录，把它和用户提供的参考项目区分开。目标目录已有业务工程时，说明冲突并确认目标。
- **接入已有项目**：用户要摸底、梳理现有项目或补项目开发规范。先只读探查，再提交草案，按已确认的范围更新文件。
- 用户只要求设计或探查时，交付草案或报告。用户已经明确要求创建或落地，且影响范围清楚时，继续执行。只询问会实质影响目标、技术选择或现有规则的未决问题。

## 创建项目

1. 确认用途、目标目录、项目名和包名、JDK、Spring Boot 版本、Maven 或 Gradle。优先使用用户选择和团队基线，结合环境给出剩余默认值。核实 JDK、构建工具和 Spring Boot 的兼容性。数据库和外部依赖按首个场景引入。
2. 若有参考项目，按 Java / Spring 参考中的清单只读检查。简要说明准备沿用的结构、依赖管理、测试方式和 CI 约定，并指出需要按目标项目调整的地方。保护参考项目中的代码、配置和敏感数据。
3. 生成构建配置、应用入口及基础测试。使用环境或 CI 提供的 Maven 或 Gradle。新项目不生成 Wrapper，也不从参考项目复制 Wrapper。采用项目生成器时，确认交付文件不含 `mvnw`、`mvnw.cmd`、`.mvn/wrapper/`、`gradlew`、`gradlew.bat` 和 `gradle/wrapper/`，构建和 CI 命令使用 `mvn` 或 `gradle`。
4. 先做环境预检，再运行构建、测试和启动验证。若已明确并授权首个功能，可用该功能做真实验证。启动验证用可退出的本地环境，并结束本次启动的进程。缺少 JDK、构建工具或服务时记录所缺条件和未验证项。
5. 写入项目入口和开发规范。CI 平台已明确且接入任务包含 CI 时，沿用团队配置或为同一条已验证命令提供最小任务。

## 接入已有项目

1. 读仓库根目录和目标模块的 `AGENTS.md`、`CLAUDE.md`、README、贡献指南及其链接。需要补充时再找项目实际存在的文档目录、模块文档、接口契约和 Wiki。记录文档用途、适用范围和路径。外部资料无法读取时标为待确认。
2. 检查构建文件、JDK、启动模块、应用配置、测试和 CI。选一个代表性模块，沿一条 HTTP、消息或任务链定位业务逻辑、权限、事务、数据访问与对应测试。覆盖范围按任务扩展。
3. 用路径、符号、配置或测试结果支持结论，标注已证实、待确认或存在冲突。把代码表现和文档约定分别记清。出现冲突时，列出双方证据和待决定的问题。
4. 先做环境预检，再运行现有验证命令。选用本地或隔离的测试资源，记录基线提交、工作目录、命令和结果。项目已有 Wrapper、构建配置和 CI 照常使用。
5. 给出接入草案，包括探查覆盖范围、验证结果、计划复用或更新的文件、待确认事项。已有开发文档原地引用或补充。重复接入只补实际缺口。

## 环境预检

- 从项目构建配置或用户要求确定目标 Java 版本。核对构建工具实际使用的 JDK，优先使用项目指定版本和已有构建入口。
- Maven 可运行 [预检脚本](scripts/maven_preflight.py)，例如 `python scripts/maven_preflight.py --project <项目根目录> --java-version 17`。脚本先报告当前 Maven 的 JDK，再从本机查找目标版本，可用 `--java-home` 显式指定。加 `--verify` 可在选定的 JDK 下跑完整构建。项目使用自定义命令时，在 `--` 后传入 Maven 参数，例如 `-- -B -Dtest=ExampleTest test`，可沿用项目的 profile、模块和测试选择。
- Gradle 从项目入口运行 `--version`，按项目配置核对 launcher、daemon 或 toolchain，再运行项目规定的验证任务。
- 构建验证前先确认测试 profile、依赖仓库及所需服务。区分 JDK 或 Maven 不可用、依赖解析失败、测试失败和环境未准备。记录实际命令和结果。验证用的 JDK 或临时镜像配置按本次执行作用域设置。

## 写入项目和交付

- `AGENTS.md` 保持短小，写项目定位、启动模块、文档索引、已验证的命令和高风险设计触发条件。索引链接到项目已有开发、架构、契约和发布文档。已有入口做局部修改。项目需要 Claude Code 入口且缺失时，可加入 `@AGENTS.md`。
- 开发规范优先沿用项目自己的位置。缺失时使用 [开发规范模板](assets/development.md) 创建 `docs/development.md`。选择适用的基础规则，写成该项目具体能执行的约定，附真实参考代码或配置。团队必须遵守的规则写进仓库，或引用团队可访问的固定版本。
- 在项目开发规范中说明需求设计入口和评审方式。若项目启用 `change-design` 并在仓库维护需求看板，记录队友从仓库根目录刷新和检查看板的实际命令。项目依赖同一份脚本时，可把 Skill 随目标仓库分发。高风险改动应明确方案、验证和恢复，请相关维护者评审。
- 最后列出新增和复用的文档、实际执行的命令及其结果、待确认事项。把详细探查证据放在接入草案或接入 PR。缺少环境而未执行的检查单独标明。
