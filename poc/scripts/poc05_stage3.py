#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""POC-05 Stage 3：工单执行 —— 领料(Material Transfer) → 报工(Job Card) → 完工入库(Manufacture)。

幂等策略：按 (work_order, purpose) 查已提交的 Stock Entry，存在则跳过；Job Card 已提交则跳过。
用法：docker exec -w /workspace/development/frappe-bench poc-frappe \
        /workspace/development/frappe-bench/env/bin/python /tmp/poc05_stage3.py
"""
import frappe
from frappe.utils import nowdate

SITE = "erpnext-poc.localhost"
frappe.init(site=SITE, sites_path="/workspace/development/frappe-bench/sites")
frappe.connect()
frappe.set_user("Administrator")

WO = "MFG-WO-2026-00001"
QTY = 2.0
TODAY = nowdate()

from erpnext.manufacturing.doctype.work_order.work_order import make_stock_entry


def build_se(wo, purpose, qty):
    """v16 的 make_stock_entry 返回 dict（stock_entry.as_dict()），需再包成 doc。"""
    data = make_stock_entry(wo, purpose, qty)
    return frappe.get_doc(data)


def existing_se(wo, purpose):
    rows = frappe.db.sql(
        """select name from `tabStock Entry`
           where work_order=%s and purpose=%s and docstatus=1 order by creation""",
        (wo, purpose), as_dict=1)
    return rows[0].name if rows else None


def submit(doc):
    doc.flags.ignore_permissions = True
    doc.insert()
    doc.submit()
    frappe.db.commit()
    return doc


# ---------------------------------------------------------------- 1. 领料
trf_name = se_name = existing_se(WO, "Material Transfer for Manufacture")
if se_name:
    print(f"[跳过] 领料单已存在: {se_name}")
else:
    se = build_se(WO, "Material Transfer for Manufacture", QTY)
    se = submit(se)
    se_name = trf_name = se.name
    print(f"[创建] 领料单(Material Transfer for Manufacture): {se_name}")
    for it in se.items:
        print(f"   {it.item_code} {it.qty} {it.s_warehouse} -> {it.t_warehouse}")

wo = frappe.get_doc("Work Order", WO)
print(f"  WO 状态: {wo.status} | 已领料 transferred_qty: {wo.material_transferred_for_manufacturing}")

# ---------------------------------------------------------------- 2. 报工
emp_map = {"装配": "HR-EMP-00001", "检验": "HR-EMP-00002"}  # 李工 / 张工
jcs = frappe.get_all("Job Card", filters={"work_order": WO}, fields=["name", "operation", "status", "docstatus"],
                     order_by="name")
print(f"  Job Card 数: {len(jcs)}")
for row in jcs:
    jc = frappe.get_doc("Job Card", row["name"])
    if jc.docstatus == 1:
        print(f"[跳过] Job Card 已提交: {jc.name} ({jc.operation})")
        continue
    emp = emp_map.get(jc.operation, "HR-EMP-00001")
    jc.append("time_logs", {
        "employee": emp,
        "from_time": f"{TODAY} 09:00:00" if jc.operation == "装配" else f"{TODAY} 10:30:00",
        "to_time": f"{TODAY} 10:00:00" if jc.operation == "装配" else f"{TODAY} 11:00:00",
        "completed_qty": QTY,
    })
    jc.total_completed_qty = QTY
    jc.save(ignore_permissions=True)
    jc.submit()
    frappe.db.commit()
    print(f"[报工] Job Card {jc.name} 工序={jc.operation} 员工={emp} 完成={QTY} 用时={jc.total_time_in_mins}min 状态={jc.status}")

# ---------------------------------------------------------------- 3. 完工入库
mfg_name = se_name = existing_se(WO, "Manufacture")
if se_name:
    print(f"[跳过] 完工入库单已存在: {se_name}")
else:
    se = build_se(WO, "Manufacture", QTY)
    se = submit(se)
    se_name = mfg_name = se.name
    print(f"[创建] 完工入库单(Manufacture): {se_name}")
    for it in se.items:
        print(f"   {it.item_code} {it.qty} {it.s_warehouse or '(消耗)'} -> {it.t_warehouse or '(无)'}")

wo.reload()
print(f"  WO 最终状态: {wo.status} | qty={wo.qty} produced_qty={wo.produced_qty} | docstatus={wo.docstatus}")
for op in wo.operations:
    print(f"   工序 {op.operation}: 完成 {op.completed_qty} / {op.actual_operation_time} min | 状态 {op.status}")

print("\n--- 库存 ---")
for b in frappe.db.sql("""select item_code, warehouse, actual_qty, stock_uom from tabBin
                          where actual_qty != 0 order by item_code, warehouse""", as_dict=1):
    print(f"  {b['item_code']:<12} {b['warehouse']:<18} {b['actual_qty']:>8} {b['stock_uom']}")

print("\n--- 单据链 ---")
print("  领料单:", trf_name)
print("  完工入库单:", mfg_name)
print("  Job Cards:", [r["name"] for r in jcs])
print("  WO:", WO)
