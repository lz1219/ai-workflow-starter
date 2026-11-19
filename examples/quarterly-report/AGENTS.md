# 月报项目开发入口

财务模板通过 `export_quarter(records, target)` 两个位置参数生成工作簿，现有调用依赖“月报”工作表及 B 列数值。金额单元格复用 `export.py` 的 `amount_cell`，由它统一保留两位小数。工作目录为本目录；示例使用 Python 3 和 openpyxl。修改时从使用者拿到的 XLSX 检查金额、公式及显示格式。

业务口径见 [季度月报设计](design.md)，已交付范围见 [任务记录](tasks.md)。
