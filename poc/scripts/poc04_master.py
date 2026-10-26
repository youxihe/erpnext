# -*- coding: utf-8 -*-
"""POC-04 主数据建设（幂等，含分段提交）。

创建：业务类型自定义字段、计量单位、物料组、仓库、物料、客户、供应商。
（工序/工作站/员工归入 POC-05 生产准备脚本。）

运行：
  docker cp poc04_master.py poc-frappe:/tmp/poc04_master.py
  docker exec -w /workspace/development/frappe-bench poc-frappe \\
      /workspace/development/frappe-bench/env/bin/python /tmp/poc04_master.py
"""
import frappe

frappe.init(site="erpnext-poc.localhost",
            sites_path="/workspace/development/frappe-bench/sites")
frappe.connect()
frappe.set_user("Administrator")

COMPANY = "昆山启程智能设备有限公司"
CUST = "苏州华新装备有限公司"
SUPP = "昆山精工零部件有限公司"


def step(msg):
    print(">>", msg)


def ensure_uom(name):
    if not frappe.db.exists("UOM", name):
        frappe.get_doc({"doctype": "UOM", "name": name, "uom_name": name}).insert(
            ignore_permissions=True)
        frappe.db.commit()
        step(f"UOM 创建: {name}")
    else:
        step(f"UOM 已存在: {name}")


def ensure_item_group(name):
    if not frappe.db.exists("Item Group", name):
        frappe.get_doc({"doctype": "Item Group", "item_group_name": name,
                        "is_group": 0}).insert(ignore_permissions=True)
        frappe.db.commit()
        step(f"物料组 创建: {name}")
    else:
        step(f"物料组 已存在: {name}")


def ensure_warehouse(name):
    full = frappe.db.get_value("Warehouse",
                               {"warehouse_name": name, "company": COMPANY}, "name")
    if full:
        step(f"仓库 已存在: {full}")
        return full
    doc = frappe.new_doc("Warehouse")
    doc.warehouse_name = name
    doc.company = COMPANY
    try:
        doc.insert(ignore_permissions=True)
    except Exception:
        doc.parent_warehouse = "所有仓库 - QC"
        doc.insert(ignore_permissions=True)
    frappe.db.commit()
    step(f"仓库 创建: {doc.name}")
    return doc.name


def ensure_customer(name):
    if frappe.db.exists("Customer", name):
        step(f"客户 已存在: {name}")
        return
    doc = frappe.new_doc("Customer")
    doc.customer_name = name
    doc.customer_type = "Company"
    doc.default_currency = "CNY"
    doc.append("accounts", {"company": COMPANY})
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    step(f"客户 创建: {name}")


def ensure_supplier(name):
    if frappe.db.exists("Supplier", name):
        step(f"供应商 已存在: {name}")
        return
    doc = frappe.new_doc("Supplier")
    doc.supplier_name = name
    doc.supplier_type = "Company"
    doc.append("accounts", {"company": COMPANY})
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    step(f"供应商 创建: {name}")


def ensure_item(code, name, group, uom, is_stock, valuation, wh):
    if frappe.db.exists("Item", code):
        step(f"物料 已存在: {code}")
        return
    doc = frappe.new_doc("Item")
    doc.item_code = code
    doc.item_name = name
    doc.item_group = group
    doc.stock_uom = uom
    doc.is_stock_item = 1 if is_stock else 0
    if valuation:
        doc.valuation_rate = valuation
    doc.append("item_defaults", {
        "company": COMPANY,
        "default_warehouse": wh,
        "buying_price_list": "Standard Buying",
        "selling_price_list": "Standard Selling",
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    step(f"物料 创建: {code} / {name}")


# ---------- 1. 业务类型自定义字段 ----------
if not frappe.db.exists("Custom Field", {"dt": "Sales Order", "fieldname": "business_type"}):
    cf = frappe.new_doc("Custom Field")
    cf.dt = "Sales Order"
    cf.fieldname = "business_type"
    cf.label = "业务类型"
    cf.fieldtype = "Select"
    cf.options = "生产\n耗材\n零部件\n服务"
    cf.insert_after = "order_type" if frappe.db.exists("DocField",
        {"parent": "Sales Order", "fieldname": "order_type"}) else "naming_series"
    cf.insert(ignore_permissions=True)
    frappe.db.commit()
    step("自定义字段 创建: Sales Order.business_type")
else:
    step("自定义字段 已存在: Sales Order.business_type")

# ---------- 2. 计量单位 ----------
for u in ["件", "台", "包", "次"]:
    ensure_uom(u)

# ---------- 3. 物料组 ----------
for g in ["Raw Material", "Products", "Services", "Sub Assemblies", "Consumable"]:
    ensure_item_group(g)

# ---------- 4. 仓库 ----------
wh_raw = ensure_warehouse("原材料仓")
wh_wip = ensure_warehouse("生产在制仓")
wh_fg = ensure_warehouse("产成品仓")
wh_trade = ensure_warehouse("贸易品仓")

# ---------- 5. 客户/供应商 ----------
ensure_customer(CUST)
ensure_supplier(SUPP)

# ---------- 6. 物料 ----------
ensure_item("ASSY-X1", "设备装配 X1", "Sub Assemblies", "台", True, 5000, wh_fg)
ensure_item("RACK", "机架", "Raw Material", "件", True, 200, wh_raw)
ensure_item("SENSOR", "传感器", "Raw Material", "件", True, 300, wh_raw)
ensure_item("FASTENER", "紧固件", "Raw Material", "件", True, 5, wh_raw)
ensure_item("FILTER-KIT", "过滤耗材包", "Consumable", "包", True, 50, wh_trade)
ensure_item("FLANGE-ASSY", "替换法兰组件", "Products", "件", True, 120, wh_trade)
ensure_item("INSTALL-SVC", "设备安装服务", "Services", "次", False, 0, wh_fg)

print("\n=== POC-04 主数据建设完成 ===")
print("仓库:", wh_raw, "|", wh_wip, "|", wh_fg, "|", wh_trade)
print("客户:", CUST, "供应商:", SUPP)
print("物料: ASSY-X1, RACK, SENSOR, FASTENER, FILTER-KIT, FLANGE-ASSY, INSTALL-SVC")
