# 更新项目内的工作流

收到「更新工作流」时，使用 [更新工具](../scripts/workflow_update.py)。它只同步项目中登记的 `.agents/skills/<名称>` 或 `.claude/skills/<名称>`，保留项目开发规范、需求和构建文件。需要 Python 3.9+ 和 Git。

当前支持本仓库使用的普通文件（Git `100644`），Python 脚本通过解释器运行。链接、可执行文件模式、仅大小写改名，以及文件与目录相互转换需要人工处理，工具在写入前报告错误。

## 首次安装与检查

新项目可以直接安装选定提交，无需手工查文件摘要。从目标项目根目录运行：

```sh
python <上游副本>/skills/project-onboard/scripts/workflow_update.py --source <上游副本> --revision <提交或标签> --install project-onboard change-design
python <上游副本>/skills/project-onboard/scripts/workflow_update.py --doctor
```

加 `--dry-run` 可先预览安装，Claude Code 项目加 `--tool claude`。工具从 Git 对象取原始内容，避免检出换行转换，安装与版本登记一起提交或一起回退。已有内容相同的文件可复用，内容不同则整次停止。重复安装同一版本会保留本地修改，已登记的不同版本应走更新。

安装会保留原有 AGENTS.md 并追加工作流入口；Claude Code 另在 CLAUDE.md 追加引用。默认配置工作流脚本的启动检查，识别到本工具生成的需求看板时增加看板检查。启动检查只证明脚本能运行，项目验收命令仍按实际约定补充，可用 `--checks-file` 提供完整检查数组。

项目将安装的 Skill 提交到 Git 时，按登记目录保留文件原始字节，避免 Windows 检出时的换行转换被识别为定制。可沿用项目现有属性，或在 `.gitattributes` 中为已启用的目录加 `.agents/skills/** -text` 或 `.claude/skills/** -text`。在一次新检出后用 `--doctor` 核对登记文件。

`--doctor` 默认离线且不执行清单命令，输出 JSON，报告源版本、缺失文件、已修改文件、验证命令是否配置以及中断恢复记录。定制是提示，缺失文件或恢复未完成是错误。它不会访问远端，也不证明版本最新或业务测试通过。无错误退出 0，有错误退出 1。

## 已有安装首次登记

项目根目录的 `.ai-workflow.json` 保存上游地址、每个 Skill 的目标目录、源提交、上游文件 SHA-256，以及验证命令。该文件随项目提交。`AGENTS.md` 只保留更新入口，避免重复维护版本号。

1. 获取可信上游的独立 Git 副本，核对 remote 和目标提交。默认上游为 `https://github.com/lz1219/ai-workflow-starter`。凭据交给 Git 凭据管理，不写进 remote、清单或日志。工具读取 Git 对象，不读取副本中尚未提交的修改，也不会自行联网。 更新时使用已检出的目标版本里的更新工具。对于 GitHub 的 HTTPS 仓库地址，末尾可带或省略 `.git`，登记的所有者和仓库名仍需匹配。
2. 找到已安装 Skill 的准确源提交，用下面的命令登记。首次登记要求上游文件与已安装文件逐字节一致，额外的项目文件可保留。换行差异也会被报告。存在定制或源版本不明时先核对差异和历史，不把最新提交猜作旧基线。需要重装基线时先另存定制，准确安装后登记，再恢复已审阅的定制。从 Git 导出提交内容可避免检出时的换行转换。
3. 在清单的 `checks` 中填写已验证的只读检查命令。也可通过 `--checks-file <JSON文件>` 在登记时导入命令数组。没有验证命令时工具允许预览，但拒绝应用更新。

以下示例从目标项目根目录运行。`<上游副本>` 是独立 Git 副本的实际路径，`<已安装源SHA>` 是旧版本提交。

```sh
python <上游副本>/skills/project-onboard/scripts/workflow_update.py --source <上游副本> --revision <已安装源SHA> --register change-design
```

默认目标为 `.agents/skills/change-design`。Claude Code 项目加 `--target .claude/skills/change-design`。其他 Skill 分别登记，目前每个名称只登记一个目标目录。

采用需求看板的项目可在清单中设置：

```json
"checks": [
  {
    "cwd": ".",
    "argv": ["{python}", ".agents/skills/change-design/scripts/requirements.py", "--check"],
    "timeout": 120
  }
]
```

这是清单中的字段片段。`--checks-file` 接收其数组部分。`{python}` 使用运行更新工具的 Python。命令以参数数组直接执行，不经 shell，工作目录相对于目标项目。未采用看板时填写实际启用的检查。检查应验证工作流与现有项目记录的兼容性，不能用 `--write` 修复数据或执行发布、迁移等有副作用的命令。工具只能恢复管理范围内的文件，不能撤销外部命令造成的其他副作用。

## 每次更新

1. 读取清单和 Git 状态，获取约定分支或标签，解析为确定的提交 SHA。核对上游变更，尤其是将要运行的脚本。使用独立副本中的更新工具，以便目标项目中的工具本身也能更新。
2. 运行预览。工具按旧上游摘要、本地内容和新上游内容比较，输出新增、修改、删除和保留定制的文件。上游与本地同时修改且内容不同，或上游删除了本地已修改文件时，整次更新停止，所有已登记 Skill 保持原状。人工解决冲突后重新预览。
3. 用户已要求更新且范围明确时，继续用同一个确定 SHA 执行 `--apply`，无需另行确认。工具在写入前创建恢复记录，修改完成后运行清单检查，全部通过才登记新版本。验证失败或普通写入异常时恢复本次修改和旧清单。
4. 记录更新结果、检查结果和保留的定制，按项目流程提交。不要将“更新工具成功”描述为业务功能验收通过。

```sh
python <上游副本>/skills/project-onboard/scripts/workflow_update.py --source <上游副本> --revision <目标SHA>
python <上游副本>/skills/project-onboard/scripts/workflow_update.py --source <上游副本> --revision <目标SHA> --apply
```

项目目录可用 `--project <项目根目录>` 指定。重复更新到同一提交且无新变化时不写文件。

## 中断恢复

写入过程中有 `.ai-workflow-transaction.json` 恢复记录。成功或回退完成后自动移除，不提交该文件。若进程被强制终止，下次更新会停止并提示恢复：

```sh
python <上游副本>/skills/project-onboard/scripts/workflow_update.py --rollback
```

恢复前会核对所有涉及文件。若中断后有人修改了这些文件，工具保留记录和文件并报告冲突，避免覆盖后来的修改。先审阅并另存需要保留的内容，再恢复。同步期间避免其他进程编辑同一 Skill。回退可能留下空目录，不影响文件内容或登记版本。

## 项目入口示例

```md
收到「更新工作流」时，读取根目录 .ai-workflow.json，从登记上游的 main
获取确定提交，使用独立上游副本中的 workflow_update.py 预览差异。
无冲突时应用同一提交并运行清单检查，失败则恢复本次修改。
有中断恢复记录时先恢复。交付更新版本、保留定制和验证结果。
```
