# -*- coding: utf-8 -*-
"""BUILD-60 测试用 Excel 样本（容器内生成，openpyxl 可用）。

输出 /workspace/build60/*.xlsx，再由 docker cp 拷到宿主机供适配器本地宿主读取。
"""

import os

import frappe
from openpyxl import Workbook

frappe.init(site="erpnext-poc.localhost", sites_path="/workspace/development/frappe-bench/sites")
frappe.connect()
frappe.set_user("Administrator")

# 清理上一轮联调产生的测试报备单（Lead 无库存影响，可安全删除，保证脚本幂等）
for name in frappe.get_all(
    "Lead",
    filters={"company_name": ("like", "苏州新元精密%"), "status": "Open"},
    pluck="name",
):
    frappe.delete_doc("Lead", name, force=True, ignore_permissions=True)
frappe.db.commit()

OUT = "/workspace/build60"
SUP = "昆山精工零部件有限公司"
COLS = ["物料编码", "物料名称", "数量", "单位", "单价", "供应商", "仓库"]
os.makedirs(OUT, exist_ok=True)


def write(name, rows, header=True):
    wb = Workbook()
    ws = wb.active
    ws.title = "采购入库"
    if header:
        ws.append(COLS)
    for r in rows:
        ws.append(r)
    path = os.path.join(OUT, name)
    wb.save(path)
    print("wrote", path)


write("采购入库-有效.xlsx", [["SENSOR", "传感器", 5, "件", 300, SUP, "原材料仓 - QC"]])
write("采购入库-取消.xlsx", [["FASTENER", "紧固件", 3, "件", 5, SUP, "原材料仓 - QC"]])
write("采购入库-无效编码.xlsx", [["NOT-A-ITEM", "不存在的物料", 5, "件", 300, SUP, "原材料仓 - QC"]])
write("采购入库-数量为负.xlsx", [["SENSOR", "传感器", -3, "件", 300, SUP, "原材料仓 - QC"]])
write("采购入库-仓库无效.xlsx", [["SENSOR", "传感器", 5, "件", 300, SUP, "所有仓库 - QC"]])
write("采购入库-供应商无效.xlsx", [["SENSOR", "传感器", 5, "件", 300, "查无此供应商有限公司", "原材料仓 - QC"]])
write("采购入库-无表头.xlsx", [["随便写点什么", 1], ["再来一行", 2]])
