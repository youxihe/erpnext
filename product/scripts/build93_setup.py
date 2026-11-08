# -*- coding: utf-8 -*-
"""BUILD-93 幂等准备：让 H5 / Bot / PC 能看到同一批真实任务与真实缺料。

做三件事（可重复执行）：
1. 新开一张「已确认、尚未采购」的生产订单 SAL-ORD（po_no=BUILD93-DEMO），
   配订单专属无工序 BOM，用于演示真实 BOM 缺料（RACK 当前为 0）。
2. 为该订单建九阶段生产进度项目。
3. 把前三个工序分派给企微绑定账号「李工 ligong」，其余留给生产经理「刘工」。
"""
import json

import frappe
from frappe.utils import add_days, getdate, today

frappe.init(site="erpnext-poc.localhost", sites_path="/workspace/development/frappe-bench/sites")
frappe.connect()

from cn_mfg_poc import production  # noqa: E402

MARK = "BUILD93-DEMO"
CUSTOMER = "苏州华新装备有限公司"
COMPANY = "昆山启程智能设备有限公司"
FG = "ASSY-X1"
FGWH = "产成品仓 - QC"
BOM_SRC = "BOM-ASSY-X1-002"
MANAGER = "liugong@erpnext-poc.localhost"
MEMBER = "ligong@erpnext-poc.localhost"
SALES = "wangming@erpnext-poc.localhost"
ASSIGN_SUBJECTS = ["机加工件加工", "内钣金焊接", "电控板组装"]

out = {"created": {}, "assigned": [], "skipped": [], "summary": {}, "errors": []}

try:
    frappe.set_user("Administrator")
    so_name = frappe.db.get_value("Sales Order", {"po_no": MARK}, "name")

    # ---------------------------------------------------------- 1. 订单专属无工序 BOM
    if not so_name:
        src = frappe.get_doc("BOM", BOM_SRC)
        bom = frappe.copy_doc(src)
        bom.company = COMPANY
        bom.is_default = 0
        bom.is_active = 1
        bom.insert(ignore_permissions=True)
        bom.submit()
        out["created"]["bom"] = bom.name

        frappe.set_user(SALES)
        so = frappe.new_doc("Sales Order")
        so.customer = CUSTOMER
        so.company = COMPANY
        so.po_no = MARK
        so.transaction_date = today()
        so.delivery_date = add_days(getdate(today()), 14)
        so.business_type = "生产"
        so.append("items", {
            "item_code": FG, "qty": 1, "rate": 5000,
            "delivery_date": so.delivery_date, "warehouse": FGWH, "bom_no": bom.name,
        })
        so.flags.ignore_permissions = True
        so.insert()
        so.submit()
        so_name = so.name
        frappe.db.commit()
        out["created"]["sales_order"] = so_name
    else:
        out["skipped"].append({"sales_order": so_name, "reason": "已存在"})
        bom = frappe.get_doc("BOM", frappe.db.get_value("Sales Order Item",
                                                        {"parent": so_name}, "bom_no"))

    # ---------------------------------------------------------- 2. 九阶段生产项目
    frappe.set_user(MANAGER)
    proj = production.create_project(so_name)
    out["created"]["project"] = proj["project"]
    out["created"]["task_count"] = len(proj["tasks"])

    # ---------------------------------------------------------- 3. 分派给李工
    rows = frappe.get_all(
        "Task", filters={"source_sales_order": so_name,
                         "status": ("not in", ["Template", "Cancelled"])},
        fields=["name", "subject", "production_owner"], order_by="exp_start_date, name",
    )
    for r in rows:
        if r["subject"] not in ASSIGN_SUBJECTS:
            continue
        if r["production_owner"] == MEMBER:
            out["skipped"].append({"task": r["name"], "reason": "已是李工"})
            continue
        production.assign_task(r["name"], MEMBER)
        out["assigned"].append({"task": r["name"], "subject": r["subject"]})

    # ---------------------------------------------------------- 4. 三入口视角核对
    frappe.set_user(MEMBER)
    mine = production.tasks_mine(limit=100)
    from cn_mfg_poc import api
    short = api.materials_shortage(limit=20)
    out["member_view"] = {
        "user": MEMBER, "total": mine["summary"]["total"],
        "tasks": [{"name": t["name"], "subject": t["subject"],
                   "sales_order": t.get("source_sales_order"),
                   "due_state": t["due_state"], "status": t["production_status"]}
                  for t in mine["tasks"]],
    }
    out["shortage_view"] = {"user": MEMBER, "count": short["count"],
                            "orders": [{"so": o["sales_order"],
                                        "items": [(c["item_code"], c["shortage"])
                                                  for c in o["shortages"]]}
                                       for o in short["orders"]]}
    out["summary"] = {
        "sales_order": so_name, "bom": bom.name, "project": proj["project"],
        "assigned": len(out["assigned"]), "member_tasks": mine["summary"]["total"],
        "shortage_orders": short["count"],
    }
except Exception as e:
    frappe.db.rollback()
    out["errors"].append(repr(e))

frappe.set_user("Administrator")
print(json.dumps(out, ensure_ascii=False, indent=1, default=str))
with open("/hostshare/build93-setup.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1, default=str)
