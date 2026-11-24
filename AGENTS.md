# AI 工作流开发入口

本仓库是这套 AI 协作工作流的**源仓库**，不是业务应用：产出是两个可安装到目标项目的 Skill（[project-onboard](skills/project-onboard/SKILL.md)、[change-design](skills/change-design/SKILL.md)），以及验证它们的评测设施。在目标项目里怎么用见 [README 的使用一节](README.md)；为什么这样设计见 [DESIGN](DESIGN.md)。

## 定位

| 要改什么 | 去哪里 |
| --- | --- |
| Skill 的行为、入口判断 | `skills/<name>/SKILL.md`。按它的「选择入口」只读需要的 references，不要全部加载。 |
| 探查、规范、图示等参考 | `skills/<name>/references/` |
| 设计、任务、开发规范模板 | `skills/change-design/assets/{design.md,tasks.md}`、`skills/project-onboard/assets/development.md` |
| 脚本 | `skills/project-onboard/scripts/{maven_preflight.py,workflow_update.py}`、`skills/change-design/scripts/requirements.py` |
| 评测场景与评分器 | `evals/{cases.py,grade.py,run.py,cold_handoff.py}`，历史结论与边界在 [evals/VALIDATION.md](evals/VALIDATION.md) |
| 端到端教学样例 | [examples/quarterly-report/](examples/quarterly-report/)（自带 `AGENTS.md`、设计与任务记录） |
| 回归用例 | `tests/`，4 个文件、53 个用例 |

约定少、入口集中，因此不单列 `docs/development.md`：长期约定写在本文件，单次改动写进提交说明或 PR。受跟踪文件只有源码、文档、测试与 CI 配置，没有构建产物。

## 规范

- 文档以中文为主，术语、路径、代码保持英文。编号稳定：验收 `AC-*`、任务 `T*`；替换已交付的规则时保留历史编号和证据。
- 区分**已证实 / 待确认 / 存在冲突**。命令跑通不等于验收通过，局部验证不能替代整体验收。这是本仓库的核心立场，评审改动时按它逐条检查。
- 新增规则的门槛：先有一个实际失败案例，再补一个能暴露该失败的任务，最后对照验证改进。不为增加规则而改判据。
- 两个 `SKILL.md` 是安装单元：`---` 开头的 front matter 必须保留 `name` / `description`，`name` 与目录名一致（`workflow_update.py` 依赖它定位 Skill）。
- `SKILL.md` 的 description 用于选择入口，正文保留范围判断、授权边界与完成标准；细节放 references 按需读取，不要复制进正文。
- 参考与模板要能被目标项目直接复制：不写本仓库专属路径，不承诺未验证的能力。
- Python 3.9+、只用标准库。新增第三方依赖会破坏「无需网络即可跑测试」这一前提，先讨论再动。

## 验证

工作目录为仓库根。运行时 Python 3.9+（本机 3.13.2），Git 必需，不联网。全量回归复核于 2026-11-24。

| 目的 | 命令 | 实测 |
| --- | --- | --- |
| 全量回归 | `python -X utf8 -B -m unittest discover -s tests` | 53 项通过，约 145 s |
| 单文件回归 | `python -X utf8 -B -m unittest discover -s tests -p test_requirements.py` | 15 项通过，约 12 s |
| 示例交付物 | 在 `examples/quarterly-report` 下 `python -B -m unittest -v test_export` | 需 openpyxl 3.1.5 |

Windows 控制台是 GBK，不带 `-X utf8` 时脚本的中文帮助与报错会乱码。

评测流程可以在没有 AI 运行器的情况下走通到评分段：

```sh
python evals/run.py prepare --case python-cli --variant baseline --trial <新目录>
python evals/run.py grade --trial <新目录>                  # 未修复的样例应返回 1，5 项检查中 2 项失败
python evals/run.py report <基线试验目录> <候选试验目录> --output <结果.json>
```

`evals/run.py run` 需要外部 runner（如本机 Codex CLI），本仓库不内置也不附凭据。Java 场景另需 JDK 17、Maven 或 Gradle、Node 22。试验目录放系统临时目录，一次一目录，不要复用。

## 协作

- 常规改动（参考文档、模板措辞、测试）直接实施并跑全量回归；按影响范围补单项验证。
- 触及 Skill 语义、评分判据、`.ai-workflow.json` 清单格式或安装/回滚行为时，先明确要解决的目标失败案例；改后除回归测试外，还要跑一次真实流程（`prepare → grade`，或 `install → --doctor`），把实际结果写进 PR。
- 高风险改动按 [DESIGN 第 4 节](DESIGN.md) 出设计并评审：更换判据、破坏已登记项目的可升级性、改变安装/回滚语义、涉及真实项目代码或凭据。样例、数据、地址只用合成内容。
- 不要把试验副本塞进工作区：演练工程、`__pycache__/`、评测 trial 目录都不入版本控制。历史上 `.local-trials/` 曾累积 3.5 GB、16 万个文件，使全库检索几乎不可用。
- `.local-trials` 的历史副本已移到工作区同一级的隔离目录（`.local-trials-quarantine-20261123`，附清单与还原命令）。它是这个项目早期迭代的原始记录，`VALIDATION.md` 里大量结论要靠它复查，**不要当临时文件清理**。
- 交付前确认 `git status` 干净，且受跟踪文件仍只有源码、文档、测试与 CI 配置。
