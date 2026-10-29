# -*- coding: utf-8 -*-
"""BUILD-70 重启前后数据快照（容器内运行）。

用法：env/bin/python /workspace/build70_snapshot.py [before|after]
输出 JSON 一行，便于前后比对。
"""

import json
import sys

import frappe

frappe.init(site="erpnext-poc.localhost", sites_path="/workspace/development/frappe-bench/sites")
frappe.connect()
frappe.set_user("Administrator")

snap = {
    "sales_orders": frappe.get_all("Sales Order", pluck="name"),
    "leads": frappe.get_all("Lead", pluck="name"),
    "purchase_receipts": frappe.get_all("Purchase Receipt", pluck="name"),
    "work_orders": frappe.get_all("Work Order", pluck="name"),
    "job_cards": frappe.get_all("Job Card", pluck="name"),
    "sensor_bin": float(frappe.db.sql(
        "select sum(actual_qty) from `tabBin` where item_code=%s", "SENSOR")[0][0] or 0),
    "fastener_bin": float(frappe.db.sql(
        "select sum(actual_qty) from `tabBin` where item_code=%s", "FASTENER")[0][0] or 0),
    "bindings": frappe.get_all("WeCom User Binding", fields=["wecom_userid", "erp_user", "enabled"]),
    "job_card_qty": {
        r["name"]: r["total_completed_qty"]
        for r in frappe.get_all("Job Card", fields=["name", "total_completed_qty"])
    },
}
print(("SNAPSHOT " + (sys.argv[1] if len(sys.argv) > 1 else "?")))
print(json.dumps(snap, ensure_ascii=False, default=str))
