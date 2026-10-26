# -*- coding: utf-8 -*-
"""POC-05 阶段1：Production Plan(展开BOM+缺料) → Material Request → Purchase Order → Purchase Receipt。

缺料按 BOM×计划量 - 原材料仓现存量 计算（显式、可追溯），物料请求类型=Purchase。
"""
import frappe
from datetime import date, timedelta

frappe.init(site="erpnext-poc.localhost",
            sites_path="/workspace/development/frappe-bench/sites")
frappe.connect()
frappe.set_user("Administrator")

COMPANY = "昆山启程智能设备有限公司"
SUPP = "昆山精工零部件有限公司"
SO = "SAL-ORD-2026-00001"
BOM = "BOM-ASSY-X1-001"

from erpnext.stock.doctype.material_request.material_request import make_purchase_order
from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_receipt


def wh(name):
    return frappe.db.get_value("Warehouse",
                               {"warehouse_name": name, "company": COMPANY}, "name")


wh_raw = wh("原材料仓")

# ---- 0. 已经有正确 mr_items 的 PP 就复用，否则清理重建 ----
reusable = None
for (name,) in frappe.db.sql(
        "select pp.name from `tabProduction Plan` pp "
        "join `tabProduction Plan Sales Order` s on s.parent=pp.name "
        "where s.sales_order=%s and pp.docstatus=1", SO):
    rows = frappe.get_all("Material Request Plan Item", filters={"parent": name},
                          fields=["item_code", "quantity", "material_request_type",
                                  "from_warehouse"])
    if rows and all(r.material_request_type == "Purchase" and not r.from_warehouse
                    for r in rows):
        reusable = name
        break
    d = frappe.get_doc("Production Plan", name)
    d.cancel()
    frappe.delete_doc("Production Plan", name, force=1, ignore_permissions=True)
    print(f"[清理] 旧 Production Plan {name}（含无效调拨行）")
frappe.db.commit()

if reusable:
    pp = frappe.get_doc("Production Plan", reusable)
    print(f"[复用] Production Plan: {pp.name}")
else:
    pp = frappe.new_doc("Production Plan")
    pp.company = COMPANY
    pp.get_items_from = "Sales Order"
    pp.posting_date = date.today()
    pp.append("sales_orders", {"sales_order": SO})
    pp.flags.ignore_permissions = True
    pp.get_items()                              # po_items
    planned = sum(it.planned_qty for it in pp.po_items)
    # 显式缺料：BOM×计划量 - 原材料仓现量
    for bi in frappe.get_all("BOM Item", filters={"parent": BOM},
                             fields=["item_code", "qty", "uom"]):
        req = bi.qty * planned
        avail = frappe.db.get_value("Bin", {"item_code": bi.item_code,
                                            "warehouse": wh_raw}, "actual_qty") or 0
        short = req - avail
        print(f"  缺料计算 {bi.item_code}: 需求 {req} - 现量 {avail} = 缺 {short}")
        if short > 0:
            pp.append("mr_items", {
                "item_code": bi.item_code,
                "quantity": short,
                "required_bom_qty": req,
                "actual_qty": avail,
                "material_request_type": "Purchase",
                "warehouse": wh_raw,
                "sales_order": SO,
                "schedule_date": date.today() + timedelta(days=7),
                "uom": bi.uom,
            })
    pp.insert()
    pp.submit()
    frappe.db.commit()
    print(f"[创建] Production Plan: {pp.name}")

print("  po_items:", [(it.item_code, it.planned_qty, it.bom_no) for it in pp.po_items])
print("  mr_items:", [(it.item_code, it.quantity, it.material_request_type)
                      for it in pp.mr_items])

# ---- 1. MR（直接按 PP 缺料行建采购型 MR，保留 production_plan 引用）----
mr_names = [r[0] for r in frappe.db.sql(
    "select distinct parent from `tabMaterial Request Item` "
    "where production_plan=%s and docstatus=1", pp.name)]
if mr_names:
    print(f"[跳过] 已存在 MR: {mr_names}")
else:
    mr = frappe.new_doc("Material Request")
    mr.company = COMPANY
    mr.material_request_type = "Purchase"
    mr.transaction_date = date.today()
    mr.flags.ignore_permissions = True
    for row in pp.mr_items:
        mr.append("items", {
            "item_code": row.item_code,
            "qty": row.quantity,
            "uom": row.uom or frappe.db.get_value("Item", row.item_code, "stock_uom"),
            "warehouse": wh_raw,
            "schedule_date": date.today() + timedelta(days=7),
            "sales_order": SO,
            "production_plan": pp.name,
            "material_request_plan_item": row.name,
        })
    mr.insert()
    mr.submit()
    frappe.db.commit()
    mr_names = [mr.name]
    print(f"[创建] Material Request: {mr.name} type={mr.material_request_type} "
          f"items={[(i.item_code, i.qty) for i in mr.items]}")

# ---- 2. PO ----
po_names = []
for mr_name in mr_names:
    existed = frappe.db.get_value("Purchase Order Item", {"material_request": mr_name},
                                  "parent")
    if existed:
        po_names.append(existed)
        print(f"[跳过] PO {existed} 已由 MR {mr_name} 生成")
        continue
    po = make_purchase_order(mr_name)
    po.supplier = SUPP
    po.company = COMPANY
    po.flags.ignore_permissions = True
    for it in po.items:
        it.supplier = SUPP
    po.insert()
    po.submit()
    po_names.append(po.name)
    print(f"[创建] Purchase Order: {po.name} 供应商={po.supplier} "
          f"items={[(i.item_code, i.qty) for i in po.items]}")

# ---- 3. PR ----
for po_name in po_names:
    existed = frappe.db.get_value("Purchase Receipt Item", {"purchase_order": po_name},
                                  "parent")
    if existed:
        print(f"[跳过] Purchase Receipt {existed} 已由 PO {po_name} 生成")
        continue
    pr = make_purchase_receipt(po_name)
    pr.flags.ignore_permissions = True
    pr.insert()
    pr.submit()
    print(f"[创建] Purchase Receipt: {pr.name} "
          f"items={[(i.item_code, i.qty) for i in pr.items]}")

frappe.db.commit()
print("\n=== 阶段1完成，原料现量(原材料仓) ===")
for code in ["RACK", "SENSOR", "FASTENER"]:
    q = frappe.db.get_value("Bin", {"item_code": code, "warehouse": wh_raw}, "actual_qty")
    print(f"  {code}: {q}")
print("PP:", pp.name, "| MR:", mr_names, "| PO:", po_names)
