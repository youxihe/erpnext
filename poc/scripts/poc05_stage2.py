# -*- coding: utf-8 -*-
"""POC-05 阶段2：Work Order ×2 台（带 BOM 工序）→ 生成 Job Card（装配/检验）。"""
import frappe
from datetime import date

frappe.init(site="erpnext-poc.localhost",
            sites_path="/workspace/development/frappe-bench/sites")
frappe.connect()
frappe.set_user("Administrator")

# 关闭产能排程：WO 提交时仍自动建 Job Card，但跳过 schedule_time_logs
# （该方法在无工作时段/计划时间时对 datetime 对象不健壮，属上游缺陷）。
frappe.db.set_single_value("Manufacturing Settings", "disable_capacity_planning", 1)
frappe.db.commit()

COMPANY = "昆山启程智能设备有限公司"
SO = "SAL-ORD-2026-00001"
BOM = "BOM-ASSY-X1-001"


def wh(name):
    return frappe.db.get_value("Warehouse",
                               {"warehouse_name": name, "company": COMPANY}, "name")


wh_raw, wh_wip, wh_fg = wh("原材料仓"), wh("生产在制仓"), wh("产成品仓")

wo_name = None
for (n,) in frappe.db.sql(
        "select name from `tabWork Order` where production_item='ASSY-X1' and docstatus=1"):
    if frappe.db.count("Work Order Operation", {"parent": n}) > 0:
        wo_name = n
        break

if wo_name:
    wo = frappe.get_doc("Work Order", wo_name)
    print(f"[复用] Work Order（带工序）: {wo.name}")
else:
    # 取消并删除所有旧 WO（草稿或无工序已提交单），保证可重放
    for (n,) in frappe.db.sql("select name from `tabWork Order` "
                              "where production_item='ASSY-X1'"):
        d = frappe.get_doc("Work Order", n)
        if d.docstatus == 1:
            d.cancel()
        frappe.delete_doc("Work Order", n, force=1, ignore_permissions=True)
        print(f"[清理] 旧 WO {n}")
    frappe.db.commit()

    pp = frappe.get_doc("Production Plan", "MFG-PP-2026-00001")
    wo = frappe.new_doc("Work Order")
    wo.company = COMPANY
    wo.production_item = "ASSY-X1"
    wo.bom_no = BOM
    wo.qty = 2
    wo.sales_order = SO
    wo.production_plan = pp.name
    wo.production_plan_item = pp.po_items[0].name
    wo.source_warehouse = wh_raw
    wo.wip_warehouse = wh_wip
    wo.fg_warehouse = wh_fg
    wo.planned_start_date = date.today()
    wo.set_work_order_operations()          # 从 BOM 拉 装配/检验 工序
    _d = date.today()
    for op in wo.operations:                 # 计划时间（Datetime，Job Card 排程需要）
        op.planned_start_time = f"{_d} 09:00:00"
        op.planned_end_time = f"{_d} 10:00:00"
    wo.flags.ignore_permissions = True
    wo.insert()
    wo.submit()
    frappe.db.commit()
    print(f"[创建] Work Order: {wo.name} qty={wo.qty} bom={wo.bom_no}")

wo = frappe.get_doc("Work Order", wo.name)
print("  WO 状态:", wo.status, " docstatus:", wo.docstatus)
print("  源仓:", wo.source_warehouse, "| 在制仓:", wo.wip_warehouse, "| 成品仓:", wo.fg_warehouse)
print("  需要原料:", [(it.item_code, it.required_qty, it.get("source_warehouse"))
                    for it in wo.required_items])
print("  工序:", [(o.operation, o.get("workstation"), o.status) for o in wo.operations])

# ---- Job Card ----
jcs = frappe.get_all("Job Card", filters={"work_order": wo.name},
                     fields=["name", "operation", "status", "for_quantity", "workstation"])
if not jcs:
    from erpnext.manufacturing.doctype.work_order.work_order import create_job_card
    for op_row in wo.operations:
        jc = create_job_card(wo, op_row, auto_create=False)
        jc.flags.ignore_permissions = True
        jc.insert()
        jc.submit()
        print(f"[创建] Job Card: {jc.name} 工序={jc.operation}")
    frappe.db.commit()
    jcs = frappe.get_all("Job Card", filters={"work_order": wo.name},
                         fields=["name", "operation", "status", "for_quantity",
                                 "workstation"])
print("  Job Cards:", jcs)
print("WO:", wo.name)
