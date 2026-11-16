# 真实任务评测

评测 AI 的实际交付结果。脚本单元测试仍在 `tests/`，这里提供独立项目、统一任务、外部验收及试验记录。项目和数据均为合成样例。

已执行的检查与局限见 [首轮验证记录](VALIDATION.md)。

| 场景 | 外部验收 |
|---|---|
| python-cli | dry-run 不创建或改写文件，数量与普通导入一致 |
| resume-cli | 完成 dry-run 修复，同时保留此前已交付的去重行为 |
| maven-spring | 通过真实 Spring MockMvc 验证计数、筛选和非法参数 |
| gradle-node | 后端 HTTP 验证，并启动真实应用核对 Node 消费端筛选与错误处理 |

## 准备试验

从本仓库根目录执行。每次试验使用新的目录，建议放在系统临时目录，不能复用已执行目录。

```sh
python evals/run.py prepare --case python-cli --variant baseline --trial <临时目录>/cli-baseline-1
python evals/run.py prepare --case python-cli --variant candidate --workflow <候选工作流仓库> --trial <临时目录>/cli-candidate-1
```

`baseline` 保留项目原有入口和规范。`current`、`candidate` 分别传入对应工作流副本，加入其 Skills 和入口链接。两种版本复制实际文件并计算摘要，包括尚未提交的修改。任务、原始项目、工作流、评分器和 runner 都有摘要，以便识别不同实验条件。宿主的全局 Skills、模型、环境变量和权限必须保持一致并另行记录，基线不意味着关闭宿主的所有内置能力。

## 运行 AI

使用自己的受信任 runner 配置。下面是 Codex CLI 示例，使用本机默认模型，不嵌入凭据：

```json
{
  "label": "codex-local-default",
  "environment": "填写模型、CLI版本、系统、运行时及全局Skills配置",
  "argv": ["codex", "exec", "--ephemeral", "--ignore-user-config", "--skip-git-repo-check", "--json", "--sandbox", "workspace-write", "-C", "{workspace}", "-o", "{response}", "-"]
}
```

```sh
python evals/run.py run --trial <试验目录> --runner <runner.json> --timeout 600
```

任务通过标准输入传入，参数数组直接执行。`{workspace}` 和 `{response}` 必须各占一个数组元素。runner 应读取标准输入，在限定工作区内执行任务。试验目录只是工作隔离，文件系统权限由所用 Agent 宿主或容器提供。不要将试验运行器连接到生产环境或赋予额外凭据。

原始过程保存在 `trace.jsonl`、`stderr.log` 和 `response.md`，执行状态在 `execution.json`。成功退出后运行外部验收，结果在 `grade.json` 和 `grade.log`。runner 成功退出不等于任务通过。退出码 0 表示验收通过，1 表示验收失败，2 表示运行器失败或明确的环境受阻。缺少评分器运行条件也返回 2。

Python 场景无需第三方包。Java 场景需要 JDK 17、Maven 或 Gradle，混合场景还需要 Node 22。可用 `EVAL_MAVEN`、`EVAL_GRADLE` 指定构建工具路径，`JAVA_HOME` 指定 JDK。构建依赖可能需要联网下载。应先在相同环境验证原始项目能够构建，再比较 AI 结果。被测程序删除文件、超时或输出错误属于任务失败。

## 评分与比较

```sh
python evals/run.py grade --trial <试验目录>
python evals/run.py report <基线试验目录> <候选试验目录> --output <结果.json>
```

评分器位于试验工作区之外。Python 直接观察命令行行为；Java 在独立临时副本中加入验收测试，并核对实际测试报告，避免只看构建退出码。混合场景还启动后端并从 Node 调用，结束后停止服务。`grade` 本身不证明有 AI 参与，手工修复的正例只能用于验证评分器。

报告按相同项目、任务、runner 和评分器分组，保留每次结果、耗时、文件改动和新增设计文件数量。token 只从运行器提供的事件读取，成本和人工纠正次数缺少可靠来源时为 null。新建设计文件数量只是观察指标，不能单独代表质量。

同一个任务每种配置建议至少重复三次，报告所有失败和受阻试验，不只挑成功结果。比较完成率、遗漏的验收、人工纠正、时间和成本，并人工抽查轨迹中的验证选择与多余工作。少量试验只能作为回归信号，不能据此宣称模型或工作流整体更优。

新规则先对应一个实际失败案例，新增能暴露该失败的任务，再对照验证改进。业务项目的私有代码、地址和数据不进入公共样例。

描述选择、设计深度、图与契约一致性及续做行为，可补充使用 [设计工作流评审场景](design-review.md)。这些场景需要独立检查产物和过程，尚未接入自动评分，不将图数量或标题匹配视为效果证据。
