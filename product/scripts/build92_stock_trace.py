# -*- coding: utf-8 -*-
"""BUILD-92 库存流水回溯：从不可变 SLE 凭证还原每张原生单据的真实增减。"""
import json

import frappe

frappe.init(site="erpnext-poc.localhost", sites_path="/workspace/development/frappe-bench/sites")
frappe.connect()
frappe.set_user("Administrator")

VOUCHERS = [
    ("Purchase Receipt", "MAT-PRE-2026-00016"),
    ("Stock Entry", "MAT-STE-2026-00010"),
    ("Stock Entry", "MAT-STE-2026-00011"),
    ("Delivery Note", "MAT-DN-2026-00005"),
]
out = {"vouchers": [], "task_gate": {}, "totals": {}}

for dtype, name in VOUCHERS:
    rows = frappe.db.sql(
        "select name, item_code, warehouse, actual_qty, qty_after_transaction, "
        "stock_value_difference, posting_date, voucher_type, voucher_no "
        "from `tabStock Ledger Entry` where voucher_type=%s and voucher_no=%s "
        "order by name", (dtype, name), as_dict=True)
    out["vouchers"].append({
        "voucher_type": dtype, "voucher_no": name,
        "sle_count": len(rows),
        "rows": [{"item_code": r["item_code"], "warehouse": r["warehouse"],
                  "actual_qty": r["actual_qty"], "qty_after": r["qty_after_transaction"],
                  "value_diff": r["stock_value_difference"], "date": str(r["posting_date"])}
                 for r in rows],
    })

out["totals"] = {
    "sle_total": frappe.db.count("Stock Ledger Entry"),
    "sle_for_build92_vouchers": sum(v["sle_count"] for v in out["vouchers"]),
    "bins": frappe.db.sql(
        "select item_code, warehouse, actual_qty, stock_value from tabBin "
        "where item_code in ('ASSY-X1','RACK','SENSOR','FASTENER') order by item_code, warehouse",
        as_dict=True),
    "work_order_produced_qty": frappe.db.get_value("Work Order", "MFG-WO-2026-00004", "produced_qty"),
    "sales_order_per_delivered": frappe.db.get_value("Sales Order", "SAL-ORD-2026-00006", "per_delivered"),
    "sales_order_per_billed": frappe.db.get_value("Sales Order", "SAL-ORD-2026-00006", "per_billed"),
}

# Task/Project 的修改时间区间内不应有任何 SLE：统计最后一条 SLE 与任务修改时间
last_sle = frappe.db.sql("select max(modified) from `tabStock Ledger Entry`")[0][0]
task_modified = frappe.db.get_value("Task", "TASK-2026-00028", "modified")
out["task_gate"] = {
    "task": "TASK-2026-00028",
    "task_modified": str(task_modified),
    "last_sle_modified": str(last_sle),
    "task_status": frappe.db.get_value("Task", "TASK-2026-00028", "status"),
    "production_status": frappe.db.get_value("Task", "TASK-2026-00028", "production_status"),
}
print(json.dumps(out, ensure_ascii=False, indent=1, default=str))
