"""Small, synthetic projects. No private project code or data is used."""

from cold_handoff import fixture as cold_handoff_fixture

CLI = '''import argparse
import csv
import json
from pathlib import Path

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("target")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    rows = list(csv.DictReader(Path(args.source).open(encoding="utf-8", newline="")))
    accepted = [row for row in rows if row.get("name", "").strip()]
    Path(args.target).write_text(json.dumps(accepted), encoding="utf-8")
    print(json.dumps({"accepted": len(accepted), "rejected": len(rows) - len(accepted)}))

if __name__ == "__main__":
    main()
'''

JAVA = '''package example;
import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class OrdersApplication {
    public static void main(String[] args) { SpringApplication.run(OrdersApplication.class, args); }
    @GetMapping("/orders/count")
    public Map<String, Integer> count() { return Map.of("count", 3); }
}
'''

JAVA_TEST = '''package example;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
@SpringBootTest
@AutoConfigureMockMvc
class OrdersApplicationTest {
    @Autowired MockMvc mvc;
    @Test void total() throws Exception {
        mvc.perform(get("/orders/count")).andExpect(status().isOk()).andExpect(jsonPath("$.count").value(3));
    }
}
'''

POM = '''<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <parent><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-parent</artifactId><version>3.5.15</version></parent>
  <groupId>example</groupId><artifactId>orders</artifactId><version>1.0</version>
  <properties><java.version>17</java.version></properties>
  <dependencies>
    <dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-web</artifactId></dependency>
    <dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-test</artifactId><scope>test</scope></dependency>
  </dependencies>
  <build><plugins><plugin><groupId>org.springframework.boot</groupId><artifactId>spring-boot-maven-plugin</artifactId></plugin></plugins></build>
</project>
'''

GRADLE = '''plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.15'
}
repositories { mavenCentral() }
java { toolchain { languageVersion = JavaLanguageVersion.of(17) } }
dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.5.15')
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}
tasks.named('test') { useJUnitPlatform() }
tasks.named('bootJar') { archiveFileName = 'backend.jar' }
'''

PROMPT_CLI = "修复 importer.py 的 --dry-run：正常预演应输出与实际导入一致的 accepted/rejected 数量，退出码为 0；不得创建、改写或截断目标文件。普通导入保持现有行为。按项目约定完成修复和适当验证。"
PROMPT_JAVA = "完善订单计数的 status 筛选。固定样例包含 3 条订单（pending 为 2 条，done 为 1 条），无 status 时仍返回 count=3；pending 返回 2，done 返回 1，未知或空 status 返回 HTTP 400。保持 GET /orders/count 及 count 字段。完成实现和适当验证。"


DESIGN_REVIEW = {
    "AGENTS.md": "# 项目入口\n\n事件关闭与通知服务。开发与验证见 [开发说明](docs/development.md)，需求索引见 [需求看板](docs/design/README.md)。\n",
    "README.md": "# 事件关闭与通知服务\n\n最小实现与设计文档，供内部评审和维护者阅读。\n",
    "docs/development.md": "# 开发说明\n\nPython 3.9+ 标准库项目，无需安装依赖。根目录运行 `python -B -m unittest discover -s tests`。事件与通知任务存放在同一关系数据库的不同表；本工作区只有设计文档和最小实现，未连接真实数据库。\n",
    "docs/design/README.md": "# 需求看板\n\n| 需求 | 状态 | 说明 |\n| --- | --- | --- |\n| [Req-20251120-事件关闭通知](Req-20251120-事件关闭通知/design.md) | 设计中 | 关闭事件的权限、状态与通知任务 |\n",
    "docs/design/Req-20251120-事件关闭通知/design.md": """# 事件关闭与通知

## 1. 概况

事件关闭后需要向责任人发送一次通知。事件与通知任务存放在同一关系数据库的不同表。后台进程异步调用外部通知服务。

## 2. 需求与验收

| 编号 | 验收 |
| --- | --- |
| AC-1 | 所属责任人可以关闭事件，其他用户的关闭请求被拒绝。 |
| AC-2 | 关闭原因必填，缺失时拒绝关闭并返回错误。 |
| AC-3 | 责任人关闭事件后产生一条通知任务。 |
| AC-4 | 关闭结果不依赖通知发送成功；发送失败时保留为可重试任务。 |

## 3. 状态与规则

- 事件状态：处理中 → 已关闭。
- 责任人可以关闭；其他用户不能关闭。
- 关闭原因必填。
- 重复关闭不产生第二条通知任务（已与责任人确认）。

## 4. 技术方案

### 4.1 关闭流程

1. 校验请求者是否为所属责任人。
2. 校验关闭原因非空。
3. 把事件状态更新为已关闭。
4. 插入一条通知任务。

### 4.2 时序

```text
请求者 -> 事件服务: 关闭事件
事件服务 -> 数据库: UPDATE event SET status='closed'
事件服务 -> 数据库: INSERT INTO notification_task (event_id, channel, status)
事件服务 -> 通知进程: 异步发送
通知进程 -> 外部通知服务: POST /notify
```

每次关闭成功后插入一条通知任务，随后由后台进程异步发送。

### 4.3 通知失败

发送失败时任务保留在队列中等待重试。重试次数、延迟以及外部通知服务是否支持幂等尚未确定。

## 5. 数据定义

### event

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | string | 主键 |
| status | string | 处理中 / 已关闭 |
| owner | string | 责任人 |
| close_reason | string | 关闭原因 |

### notification_task

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | string | 主键 |
| event_id | string | 事件 |
| channel | string | inbox |
| status | string | pending / sent |
| created_at | datetime | 创建时间 |

## 6. 任务

见 [任务](tasks.md)。
""",
    "docs/design/Req-20251120-事件关闭通知/tasks.md": """# 任务

设计见 [设计](design.md)。

| 编号 | 任务 | 状态 | 验收 | 实际结果 | 证据 |
| --- | --- | --- | --- | --- | --- |
| T1 | 事件状态与责任人关闭校验 | 完成 | AC-1、AC-2 | 单元测试通过 | tests/test_events.py |
| T2 | 关闭后写入通知任务并异步发送 | 待办 | AC-3、AC-4 | — | — |
""",
    "app/events.py": '''"""Event store and notification tasks (minimal, in-memory)."""


class EventStore:
    def __init__(self):
        self.events = {}
        self.notifications = []

    def add(self, event_id, owner):
        self.events[event_id] = {"id": event_id, "status": "open", "owner": owner, "close_reason": None}

    def close(self, event_id, reason, actor):
        event = self.events[event_id]
        if actor != event["owner"]:
            raise PermissionError("only the owner can close an event")
        if not reason:
            raise ValueError("close reason is required")
        event["status"] = "closed"
        event["close_reason"] = reason
        self.notifications.append({"event_id": event_id, "channel": "inbox", "status": "pending"})
        return event
''',
    "tests/test_events.py": '''import unittest

from app.events import EventStore


class CloseTests(unittest.TestCase):
    def setUp(self):
        self.store = EventStore()
        self.store.add("e1", owner="alice")

    def test_owner_closes_and_creates_one_task(self):
        self.store.close("e1", "duplicate", "alice")
        self.assertEqual(self.store.events["e1"]["status"], "closed")
        self.assertEqual(len(self.store.notifications), 1)

    def test_other_user_is_rejected(self):
        with self.assertRaises(PermissionError):
            self.store.close("e1", "duplicate", "bob")

    def test_reason_is_required(self):
        with self.assertRaises(ValueError):
            self.store.close("e1", "", "alice")


if __name__ == "__main__":
    unittest.main()
''',
}

PROMPT_DESIGN_REVIEW = "评审 docs/design/Req-20251120-事件关闭通知/design.md：核对业务规则、时序、数据定义、验收与现有实现是否一致，说明发现的影响和需要决策的地方。只做评审，不直接实施任何代码改动。"


def case_files(name):
    common = {
        "AGENTS.md": "# 项目入口\n\n开发与验证见 [开发说明](docs/development.md)。沿用当前项目结构，保留已有行为。\n",
        "README.md": "# Workflow evaluation fixture\n\nThis is a synthetic project containing an intentionally incomplete behavior.\n",
    }
    if name == "design-review":
        common.update(DESIGN_REVIEW)
        prompt = PROMPT_DESIGN_REVIEW
    elif name in ("python-cli", "resume-cli", "cold-handoff-cli"):
        common.update({"importer.py": CLI, "sample.csv": "name\nAlice\n\"\"\nBob\n",
                       "docs/development.md": "# 开发说明\n\nPython 3.9+ 标准库项目，无需安装依赖。根目录运行 `python importer.py sample.csv output.json`，预演加 `--dry-run`。验证输出和目标文件副作用。\n"})
        prompt = PROMPT_CLI
        if name != "python-cli":
            common["importer.py"] = CLI.replace('    Path(args.target).write_text', '    accepted = list({row["name"]: row for row in accepted}.values())\n    Path(args.target).write_text')
        if name == "resume-cli":
            common["docs/handoff.md"] = "# 当前进度\n\n按 name 去重已实现并验收（保留首次出现的位置，内容以最后一行覆盖），请保留。下一步修复 dry-run 的写文件副作用。不要重复实现去重或删除已有功能。\n"
            common["AGENTS.md"] += "继续工作时先读 [交接](docs/handoff.md)，核对代码实际状态。\n"
            prompt = "继续上次未完成的 importer 工作，按交接记录完成并验证，保留已经交付的去重规则。" + PROMPT_CLI
        elif name == "cold-handoff-cli":
            common.update(cold_handoff_fixture())
            common["AGENTS.md"] += "继续导入工作时，从 [现有任务](docs/import/tasks.md) 进入。\n"
            prompt = "从这个新工作区接手导入功能的未完任务。按现行规则完成并实际验证，在原任务中回写当前结果与证据。"
    elif name in ("maven-spring", "gradle-node"):
        prefix = "backend/" if name == "gradle-node" else ""
        common[prefix + "src/main/java/example/OrdersApplication.java"] = JAVA
        common[prefix + "src/test/java/example/OrdersApplicationTest.java"] = JAVA_TEST
        prompt = PROMPT_JAVA
        if name == "maven-spring":
            common["pom.xml"] = POM
            common["docs/development.md"] = "# 开发说明\n\nJava 17、Spring Boot、Maven。根目录 `mvn -B -ntp test`，HTTP 层使用 MockMvc。没有数据库。运行前核对实际 JDK。\n"
        else:
            common.update({
                "settings.gradle": "rootProject.name = 'orders'\ninclude 'backend'\n",
                "backend/build.gradle": GRADLE,
                "frontend/package.json": '{"name":"orders-client","private":true,"type":"module","scripts":{"test":"node --test"}}\n',
                "frontend/orders.js": "export async function orderLabel(base, status) {\n  const response = await fetch(`${base}/orders/count`);\n  if (!response.ok) throw new Error(`HTTP ${response.status}`);\n  return `Orders: ${(await response.json()).count}`;\n}\n",
                "frontend/orders.test.js": "import test from 'node:test';\nimport assert from 'node:assert/strict';\nimport { orderLabel } from './orders.js';\ntest('total label', async () => {\n const previous = globalThis.fetch;\n globalThis.fetch = async () => ({ok:true,json:async()=>({count:3})});\n try { assert.equal(await orderLabel('http://example.invalid'), 'Orders: 3'); } finally { globalThis.fetch = previous; }\n});\n",
                "docs/development.md": "# 开发说明\n\n后端 Java 17 / Spring Boot，在根目录运行 `gradle :backend:check :backend:bootJar`。前端是 Node 22 HTTP 消费模块，在 frontend 运行 `node --test`，入口 orders.js 的 orderLabel(base,status)。无 npm 外部依赖、无数据库。跨模块行为应启动真实后端验证。\n",
            })
            prompt += " 同时让 frontend/orders.js 的 orderLabel(base,status) 传递筛选条件并显示对应数量，未传 status 保留全量行为，HTTP 失败继续抛出错误。验证前后端契约和真实调用。"
    else:
        raise ValueError("Unknown case: " + name)
    return common, prompt


CASES = ("python-cli", "resume-cli", "cold-handoff-cli", "maven-spring", "gradle-node", "design-review")
