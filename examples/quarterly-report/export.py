from openpyxl import Workbook


def amount_cell(sheet, row, value):
    cell = sheet.cell(row, 2, value)
    cell.number_format = "#,##0.00"


def export_quarter(records, target):
    """Export monthly amounts from a dict keyed by month number."""
    book = Workbook()
    sheet = book.active
    sheet.title = "月报"
    sheet.append(["月份", "金额"])

    quarter_months = (1, 2, 3)
    if all(month in quarter_months for month in records):
        monthly_amounts = ((month, records.get(month, 0)) for month in quarter_months)
    else:
        monthly_amounts = ((month, records[month]) for month in sorted(records))

    for row, (month, amount) in enumerate(monthly_amounts, 2):
        sheet.cell(row, 1, month)
        amount_cell(sheet, row, amount)

    sheet["D2"] = "=SUM(B2:B4)"
    sheet["D3"] = "=AVERAGE(B2:B4)"
    book.save(target)
