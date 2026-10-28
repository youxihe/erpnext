# -*- coding: utf-8 -*-
"""BUILD-00 现状复核探针：只读，不改数据。"""
import frappe, json

frappe.init(site="erpnext-poc.localhost", sites_path="/workspace/development/frappe-bench/sites")
frappe.connect()
frappe.set_user("Administrator")

out = {}

# 1. 基础版本与环境
out["versions"] = {
    "frappe": frappe.__version__,
    "erpnext": frappe.get_attr("erpnext.__version__") if hasattr(__import__("erpnext"), "__version__") else None,
    "python": __import__("sys").version.split()[0],
    "site": frappe.local.site,
}
out["installed_apps"] = frappe.get_installed_apps()
out["company"] = frappe.get_all("Company", fields=["name", "abbr", "default_currency", "country"])

# 2. 用户与角色
users = []
for u in frappe.get_all("User", filters={"enabled": 1}, fields=["name", "full_name", "user_type"], order_by="name"):
    roles = [r.role for r in frappe.get_all("Has Role", filters={"parent": u["name"], "parenttype": "User"}, fields=["role"])]
    users.append({"email": u["name"], "full_name": u.get("full_name"), "type": u["user_type"], "roles": roles})
out["users"] = users
out["roles"] = [r["name"] for r in frappe.get_all("Role", filters={"disabled": 0}, fields=["name"], order_by="name")]

# 3. 中文工作台（导航）
ws = []
for w in frappe.get_all("Workspace", fields=["name", "module", "public"], order_by="name"):
    d = frappe.get_doc("Workspace", w["name"])
    links = [l.label for l in getattr(d, "links", [])][:40]
    ws.append({"name": w["name"], "module": w["module"], "public": w["public"], "roles": [r.role for r in d.roles], "link_count": len(d.links), "links_sample": links})
out["workspaces"] = ws

# 4. 单据存量
doc_types = ["Customer", "Sales Order", "Sales Invoice", "Delivery Note", "Payment Entry",
             "BOM", "Production Plan", "Work Order", "Job Card", "Workstation", "Operation",
             "Material Request", "Supplier", "Purchase Order", "Purchase Receipt",
             "Stock Entry", "Warehouse", "Item", "Bin", "Stock Ledger Entry", "GL Entry",
             "Employee", "User"]
out["doc_counts"] = {dt: frappe.db.count(dt) for dt in doc_types}

# 5. 四类订单抽样
orders = []
for so in frappe.get_all("Sales Order", filters={"docstatus": 1}, fields=["name", "customer", "grand_total", "status", "per_delivered", "per_billed"], order_by="name"):
    d = frappe.get_doc("Sales Order", so["name"])
    orders.append({
        "name": d.name,
        "customer": d.customer,
        "business_type": d.get("business_type"),
        "items": [{"item_code": i.item_code, "qty": i.qty, "rate": i.rate, "delivered_qty": i.delivered_qty} for i in d.items],
        "grand_total": d.grand_total,
        "status": d.status,
        "per_delivered": d.per_delivered,
        "per_billed": d.per_billed,
    })
out["sales_orders"] = orders

# 6. 生产链路抽样
chain = {}
for dt, fields in [
    ("Production Plan", ["name", "docstatus", "status"]),
    ("Work Order", ["name", "production_item", "qty", "produced_qty", "status", "docstatus"]),
    ("Job Card", ["name", "operation", "workstation", "status", "total_completed_qty", "for_quantity", "work_order"]),
    ("BOM", ["name", "item", "is_default", "docstatus"]),
    ("Stock Entry", ["name", "purpose", "docstatus"]),
]:
    chain[dt] = frappe.get_all(dt, fields=fields, order_by="name", limit=20)
out["production_chain"] = chain

# 7. 库存现状
out["stock"] = frappe.db.sql("""
    select b.item_code, b.warehouse, b.actual_qty, b.stock_value
    from tabBin b where b.actual_qty <> 0 order by b.item_code, b.warehouse
""", as_dict=1)
out["warehouses"] = frappe.get_all("Warehouse", fields=["name", "company"], order_by="name")

# 8. 自定义字段 / 业务类型
out["custom_fields"] = [
    {"dt": c.dt, "fieldname": c.fieldname, "label": c.label, "fieldtype": c.fieldtype}
    for c in frappe.get_all("Custom Field", fields=["dt", "fieldname", "label", "fieldtype"], filters={"dt": ["in", ["Sales Order", "Item", "Customer"]]})
]

# 9. 现有自有 App 接口面（是否有 api 模块 / 白名单函数）
try:
    import cn_mfg_poc
    out["own_app_path"] = cn_mfg_poc.__file__
except Exception as e:
    out["own_app_path"] = f"导入失败: {e}"
out["whitelisted_own"] = frappe.db.sql("""
    select name from `tabDocType` where module = 'CN MFG POC'
""", as_dict=1)

# 10. 站点 REST 可用性基线（不鉴权调用）
out["site_config_keys"] = sorted(frappe.conf.keys())[:20] if hasattr(frappe, "conf") else []

print(json.dumps(out, ensure_ascii=False, indent=1, default=str))
