# -*- coding: utf-8 -*-
"""BUILD-90 原生能力审计：只读，不改任何业务数据。

核对轻制造决策要求的最小原生能力：
- Project Template / Project / Task 能否按销售订单关联并生成固定任务
- BOM 无 Operations、无 Job Card 报工时，Work Order / Stock Entry 能否合法完工入库
- 是否存在把 Task 状态连到库存过账的 hook（必须为否）
输出 docs/product/evidence/build90-audit.json。
"""
import json

import frappe

frappe.init(site="erpnext-poc.localhost", sites_path="/workspace/development/frappe-bench/sites")
frappe.connect()
frappe.set_user("Administrator")

out = {}


def fields(dt):
    try:
        return [f.fieldname for f in frappe.get_meta(dt).fields]
    except Exception as e:
        return ["ERR:%s" % e]


def select_options(dt, fieldname):
    try:
        f = frappe.get_meta(dt).get_field(fieldname)
        return f.options if f else None
    except Exception:
        return None


def count(dt, filters=None):
    try:
        return frappe.db.count(dt, filters or {})
    except Exception as e:
        return "ERR:%s" % e


# ---------------------------------------------------------------- 1. 原生进度模型
PROGRESS_DTS = ["Project Template", "Project Template Task", "Project", "Task"]
out["progress_doctypes"] = {
    dt: {
        "exists": bool(frappe.db.exists("DocType", dt)),
        "count": count(dt),
        "fields": fields(dt) if frappe.db.exists("DocType", dt) else [],
    }
    for dt in PROGRESS_DTS
}
out["task_status_options"] = select_options("Task", "status")
out["project_fields_of_interest"] = {
    f: (f in out["progress_doctypes"]["Project"]["fields"])
    for f in ["project_template", "sales_order", "customer", "expected_start_date", "expected_end_date", "status", "is_active", "percent_complete"]
}
out["task_fields_of_interest"] = {
    f: (f in out["progress_doctypes"]["Task"]["fields"])
    for f in ["project", "subject", "status", "exp_start_date", "exp_end_date", "completed_on",
              "completed_by", "description", "_assign", "priority", "task_weight", "parent_task"]
}
out["project_template_tasks"] = {
    f: (f in out["progress_doctypes"]["Project Template Task"]["fields"])
    for f in ["subject", "start", "duration", "task_weight", "description"]
}
out["existing_templates"] = frappe.get_all(
    "Project Template", fields=["name"], order_by="name", limit=20
) if frappe.db.exists("DocType", "Project Template") else []

# ---------------------------------------------------------------- 2. 无工序制造能力
out["bom"] = {
    "fields_of_interest": {
        f: (f in fields("BOM")) for f in
        ["item", "quantity", "with_operations", "operations", "items", "is_active", "is_default", "project"]
    },
    "with_operations_options": select_options("BOM", "with_operations"),
    "records": [],
}
for b in frappe.get_all("BOM", fields=["name", "item", "quantity", "with_operations", "is_active", "docstatus"], order_by="name", limit=10):
    ops = frappe.db.count("BOM Operation", {"parent": b["name"], "parenttype": "BOM"}) if frappe.db.exists("DocType", "BOM Operation") else None
    b["operation_rows"] = ops
    out["bom"]["records"].append(b)

out["work_order"] = {
    "fields_of_interest": {
        f: (f in fields("Work Order")) for f in
        ["production_item", "bom_no", "qty", "produced_qty", "wip_warehouse", "fg_warehouse",
         "source_warehouse", "skip_transfer", "use_multi_level_bom", "operations", "required_items",
         "sales_order", "status", "project"]
    },
    "records": [],
}
for w in frappe.get_all(
    "Work Order",
    fields=["name", "production_item", "bom_no", "qty", "produced_qty", "status", "docstatus", "skip_transfer"],
    order_by="name", limit=10,
):
    w["operation_rows"] = frappe.db.count("Work Order Operation", {"parent": w["name"], "parenttype": "Work Order"}) if frappe.db.exists("DocType", "Work Order Operation") else None
    w["job_cards"] = count("Job Card", {"work_order": w["name"]})
    out["work_order"]["records"].append(w)

out["stock_entry"] = {
    "purpose_options": select_options("Stock Entry", "purpose"),
    "fields_of_interest": {
        f: (f in fields("Stock Entry")) for f in
        ["purpose", "work_order", "bom_no", "fg_completed_qty", "from_warehouse", "to_warehouse", "items"]
    },
    "manufacture_records": frappe.get_all(
        "Stock Entry",
        filters={"purpose": ["in", ["Manufacture", "Material Transfer for Manufacture"]]},
        fields=["name", "purpose", "work_order", "fg_completed_qty", "docstatus"],
        order_by="name", limit=20,
    ),
}
out["stock_entry_purposes"] = {
    "Manufacture": "Manufacture" in str(out["stock_entry"]["purpose_options"]),
    "Material Transfer for Manufacture": "Material Transfer for Manufacture" in str(out["stock_entry"]["purpose_options"]),
    "Material Issue": "Material Issue" in str(out["stock_entry"]["purpose_options"]),
}

# ---------------------------------------------------------------- 3. Task → 库存 解耦检查（Gate）
hooks = frappe.get_hooks("doc_events") or {}
out["task_stock_decoupling"] = {
    "task_doc_events": hooks.get("Task"),
    "project_doc_events": hooks.get("Project"),
    "any_task_hook": bool(hooks.get("Task") or hooks.get("Project")),
    "note": "Task/Project 不得挂任何会写 Stock Ledger Entry 的 doc_event",
}
out["installed_apps"] = frappe.get_installed_apps()
out["own_hooks_doc_events"] = {k: v for k, v in hooks.items() if k in ["Sales Order", "Task", "Project", "Stock Entry", "Work Order"]}

# ---------------------------------------------------------------- 4. 现有 API 面（BUILD-93 契约基线）
try:
    from cn_mfg_poc import api
    out["api_surface"] = sorted(
        n for n, v in vars(api).items()
        if callable(v) and getattr(v, "__module__", "") == api.__name__ and not n.startswith("_")
    )
except Exception as e:
    out["api_surface"] = "ERR:%s" % e
out["required_build93_contracts"] = {
    n: (n in out["api_surface"] if isinstance(out["api_surface"], list) else False)
    for n in ["orders_summary", "production_tasks_mine", "production_tasks_update", "materials_shortage"]
}

# ---------------------------------------------------------------- 5. 增量改造差异
out["existing_job_card_apis"] = [n for n in (out["api_surface"] if isinstance(out["api_surface"], list) else []) if "job" in n]
out["business_type_distribution"] = {
    t: count("Sales Order", {"business_type": t}) for t in ["生产", "耗材", "零部件", "服务"]
}

print(json.dumps(out, ensure_ascii=False, indent=1, default=str))
