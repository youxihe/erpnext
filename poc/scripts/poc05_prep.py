# -*- coding: utf-8 -*-
"""POC-05 生产准备（幂等）：工序、工作站、员工、BOM、原料初始库存。

运行：
  docker cp poc05_prep.py poc-frappe:/tmp/poc05_prep.py
  docker exec -w /workspace/development/frappe-bench poc-frappe \\
      /workspace/development/frappe-bench/env/bin/python /tmp/poc05_prep.py
"""
import frappe
from datetime import date

frappe.init(site="erpnext-poc.localhost",
            sites_path="/workspace/development/frappe-bench/sites")
frappe.connect()
frappe.set_user("Administrator")

COMPANY = "昆山启程智能设备有限公司"


def step(m):
    print(">>", m)


def wh(name):
    return frappe.db.get_value("Warehouse",
                               {"warehouse_name": name, "company": COMPANY}, "name")


def ensure_operation(name, workst):
    if frappe.db.exists("Operation", name):
        step(f"工序已存在: {name}")
        return
    doc = frappe.new_doc("Operation")
    doc.name = name
    doc.operation = name
    if frappe.get_meta("Operation").has_field("workstation"):
        doc.workstation = workst
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    step(f"工序创建: {name}")


def ensure_workstation(name):
    if frappe.db.exists("Workstation", name):
        step(f"工作站已存在: {name}")
        return
    doc = frappe.new_doc("Workstation")
    doc.name = name
    if frappe.get_meta("Workstation").has_field("workstation_name"):
        doc.workstation_name = name
    doc.company = COMPANY
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    step(f"工作站创建: {name}")


def ensure_employee(emp_name, user_email):
    if frappe.db.exists("Employee", {"user_id": user_email}):
        step(f"员工已存在: {emp_name}")
        return frappe.db.get_value("Employee", {"user_id": user_email}, "name")
    doc = frappe.new_doc("Employee")
    doc.employee_name = emp_name
    doc.first_name = emp_name
    doc.user_id = user_email
    doc.company = COMPANY
    doc.status = "Active"
    doc.gender = "Male"
    doc.date_of_birth = "1990-01-01"
    doc.date_of_joining = "2026-01-01"
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    step(f"员工创建: {doc.name} ({emp_name})")
    return doc.name


def ensure_raw_stock(item_code, qty, valuation):
    wh_raw = wh("原材料仓")
    if frappe.db.exists("Bin", {"item_code": item_code, "warehouse": wh_raw}):
        step(f"原料库存已存在: {item_code}="
             f"{frappe.db.get_value('Bin', {'item_code': item_code, 'warehouse': wh_raw}, 'actual_qty')}")
        return
    if qty <= 0:
        step(f"原料初始为0，跳过: {item_code}")
        return
    sr = frappe.new_doc("Stock Reconciliation")
    sr.purpose = "Stock Reconciliation"
    sr.company = COMPANY
    sr.posting_date = date.today()
    sr.expense_account = "临时开账 - QC"
    sr.append("items", {"item_code": item_code, "qty": qty,
                        "valuation_rate": valuation, "warehouse": wh_raw})
    sr.insert(ignore_permissions=True)
    sr.submit()
    frappe.db.commit()
    step(f"原料初始库存: {item_code} x{qty} @ 原材料仓 ({sr.name})")


def ensure_bom():
    if frappe.db.exists("BOM", {"item": "ASSY-X1", "is_active": 1, "docstatus": 1}):
        b = frappe.db.get_value("BOM", {"item": "ASSY-X1", "is_active": 1,
                                        "docstatus": 1}, "name")
        step(f"BOM 已存在: {b}")
        return b
    rates = {}
    for code in ["RACK", "SENSOR", "FASTENER"]:
        rates[code] = frappe.db.get_value("Item", code, "valuation_rate") or 0
    bom = frappe.new_doc("BOM")
    bom.item = "ASSY-X1"
    bom.quantity = 1
    bom.uom = "台"
    bom.company = COMPANY
    bom.with_operations = 1
    for code, qty in [("RACK", 2), ("SENSOR", 1), ("FASTENER", 4)]:
        bom.append("items", {"item_code": code, "qty": qty, "rate": rates[code]})
    bom.append("operations", {"operation": "装配", "time_in_mins": 60,
                              "workstation": "装配工位"})
    bom.append("operations", {"operation": "检验", "time_in_mins": 30,
                              "workstation": "检验工位"})
    bom.insert(ignore_permissions=True)
    bom.submit()
    frappe.set_value("BOM", bom.name, "is_default", 1)
    frappe.db.commit()
    step(f"BOM 创建并提交: {bom.name}（每台 机架2/传感器1/紧固件4 + 装配/检验工序）")
    return bom.name


print("=== POC-05 生产准备 ===")
ensure_workstation("装配工位")
ensure_workstation("检验工位")
ensure_operation("装配", "装配工位")
ensure_operation("检验", "检验工位")
ensure_employee("李工", "ligong@erpnext-poc.localhost")
ensure_employee("张工", "zhanggong@erpnext-poc.localhost")
ensure_employee("刘工", "liugong@erpnext-poc.localhost")

# 初始原料库存（TEST_DATA：机架1、传感器0、紧固件12）→ 两台需求 4/2/8，机架缺3、传感器缺2
ensure_raw_stock("RACK", 1, 200)
ensure_raw_stock("SENSOR", 0, 300)
ensure_raw_stock("FASTENER", 12, 5)

bom = ensure_bom()
print("\n=== 准备完成 ===")
print("BOM:", bom)
for code in ["RACK", "SENSOR", "FASTENER"]:
    q = frappe.db.get_value("Bin", {"item_code": code, "warehouse": wh("原材料仓")}, "actual_qty")
    print(f"  原料 {code} 现量(原材料仓)={q}")
