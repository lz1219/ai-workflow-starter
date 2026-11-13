# 更新项目内的工作流

项目需要按自然语言更新时，在目标仓库的 `AGENTS.md` 写明约定。记录上游仓库和分支或标签、启用的 Skill 及目标目录、每个目录当前对应的源提交、同步后要运行的项目验证。默认上游为 [ai-workflow-starter](https://github.com/lz1219/ai-workflow-starter)。

例如只启用需求设计的 Codex 项目，可在 `AGENTS.md` 添加一段，并填写实际版本。

```md
## 更新工作流

收到「更新工作流」时，从 https://github.com/lz1219/ai-workflow-starter 的 main
同步 skills/change-design 到 .agents/skills/change-design。当前源提交填写为实际提交 SHA。
先检查项目改动和上游差异，保留冲突文件。同步后从仓库根目录运行
python .agents/skills/change-design/scripts/requirements.py --check，
验证通过后更新源提交并报告结果。
```

收到「更新工作流」后执行以下步骤。

1. 获取约定的上游版本并解析出提交。从登记的源提交比较上游变化和目标目录中的改动，包括已经提交的项目定制。对两边同时改动且无法合并的文件，列出路径并保留项目版本。缺少源提交时，先比较差异，标明需要判断归属的文件。
2. 同步已登记的 Skill 目录及其模板、参考和脚本。上游删除的文件只有在确认仍等同于旧上游文件时才一同删除。项目维护自己的开发规范、需求历史和构建配置。
3. 运行登记的验证。例如采用本仓库看板模板的项目运行 `python .agents/skills/change-design/scripts/requirements.py --check`，按需用 `--review <需求目录名>` 检查当前需求。验证通过后在同步记录更新源提交，报告改动、验证结果和待合并项。部分更新时保留旧源提交，并列出已同步的文件。
