from openpyxl import Workbook


def amount_cell(sheet, row, value):
    cell = sheet.cell(row, 2, value)
    cell.number_format = "#,##0.00"


def export_quarter(records, target, *, show_reporting_status=False):
    """Export amounts and optionally label Q1 months present in the source."""
    book = Workbook()
    sheet = book.active
    sheet.title = "月报"
    sheet.append(["月份", "金额"])

    quarter_months = (1, 2, 3)
    if all(month in quarter_months for month in records):
        monthly_amounts = ((month, records.get(month, 0)) for month in quarter_months)
        if show_reporting_status:
            sheet.cell(1, 3, "填报状态")
            sheet.column_dimensions["C"].width = 14
    else:
        monthly_amounts = ((month, records[month]) for month in sorted(records))
        show_reporting_status = False

    for row, (month, amount) in enumerate(monthly_amounts, 2):
        sheet.cell(row, 1, month)
        amount_cell(sheet, row, amount)
        if show_reporting_status:
            sheet.cell(row, 3, "已上报" if month in records else "未上报")

    sheet["D2"] = "=SUM(B2:B4)"
    sheet["D3"] = "=AVERAGE(B2:B4)"
    book.save(target)
