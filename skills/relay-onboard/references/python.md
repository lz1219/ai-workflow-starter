# Python 接入参考

- 从 `pyproject.toml`、锁文件、`requirements*.txt`、`.python-version` 和 CI 确认 Python 版本、依赖工具及测试环境。存在多个配置时，以实际入口和 CI 为证据。项目可用 uv、Poetry、pip 或其他已配置的工具。
- 从 `[project.scripts]`、`__main__.py`、任务入口、服务启动配置或公开包入口定位真实调用方式。结合测试找一条代表性链路。对 CLI 核对退出码及文件副作用，对数据任务核对样例、重跑和输出。
- 记录从哪个目录、在哪个环境执行项目的命令。例如 CI 使用 `uv run pytest` 就记录该命令，标准库项目可直接沿用 `python -m unittest discover -s tests`。按需记录项目已有的格式、类型、打包或端到端检查。
