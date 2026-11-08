# -*- coding: utf-8 -*-
"""BUILD-92 前置：BOM、SO Item 字段、供应商、仓库、原生建单函数。"""
import json

import frappe

frappe.init(site="erpnext-poc.localhost", sites_path="/workspace/development/frappe-bench/sites")
frappe.connect()
frappe.set_user("Administrator")

out = {}
out["boms"] = frappe.get_all("BOM", fields=["name", "item", "quantity", "is_active", "is_default",
                                            "docstatus", "with_operations", "company"], limit=50)
out["bom_detail"] = {}
for b in out["boms"][:8]:
    doc = frappe.get_doc("BOM", b["name"])
    out["bom_detail"][b["name"]] = {
        "items": [{"item_code": r.item_code, "qty": r.qty, "uom": r.uom,
                   "source_warehouse": r.get("source_warehouse")} for r in doc.items],
        "operations": len(doc.get("operations") or []),
        "raw_material_cost": doc.get("raw_material_cost"),
    }

so_meta = frappe.get_meta("Sales Order Item")
out["so_item_bom_fields"] = [f.fieldname for f in so_meta.fields
                             if "bom" in f.fieldname.lower() or "production" in f.fieldname.lower()
                             or "warehouse" in f.fieldname.lower()]
out["so_item_fields_sample"] = [f.fieldname for f in so_meta.fields][:60]

out["suppliers"] = frappe.get_all("Supplier", fields=["name", "supplier_name", "supplier_group"], limit=20)
out["items_for_sale"] = frappe.get_all("Item", filters={"is_sales_item": 1, "disabled": 0},
                                       fields=["name", "item_name", "item_group", "is_stock_item",
                                               "stock_uom", "standard_rate"], limit=40)
for code in ["LM90-FG", "LM90-RM", "ASSY-X1", "RACK", "SENSOR"]:
    if frappe.db.exists("Item", code):
        d = frappe.get_doc("Item", code)
        out.setdefault("item_detail", {})[code] = {
            "item_name": d.item_name, "is_stock_item": d.is_stock_item,
            "standard_rate": d.get("standard_rate"), "valuation_rate": d.get("valuation_rate"),
            "item_defaults": [{"company": x.company, "default_warehouse": x.get("default_warehouse"),
                               "buying_cost_center": x.get("buying_cost_center")}
                              for x in (d.get("item_defaults") or [])],
        }

out["company"] = frappe.get_all("Company", fields=["name", "default_currency", "default_warehouse",
                                                    "stock_adjustment_account", "default_expense_account"], limit=10)
out["work_order_status"] = frappe.get_all("Work Order", fields=["name", "status", "docstatus",
                                                                 "production_item", "qty", "produced_qty",
                                                                 "bom_no", "skip_transfer", "sales_order"],
                                          order_by="creation desc", limit=20)
out["stock_entry_purposes"] = frappe.get_all("Stock Entry", fields=["name", "purpose", "docstatus",
                                                                     "work_order"], order_by="creation desc", limit=25)

# 原生建单 helper 是否存在
import importlib
out["helpers"] = {}
for mod, fn in [
    ("erpnext.selling.doctype.sales_order.sales_order", "make_delivery_note"),
    ("erpnext.selling.doctype.sales_order.sales_order", "make_sales_invoice"),
    ("erpnext.manufacturing.doctype.work_order.work_order", "make_stock_entry"),
    ("erpnext.manufacturing.doctype.work_order.work_order", "make_stock_return_entry"),
    ("erpnext.stock.doctype.material_request.material_request", "make_purchase_order"),
    ("erpnext.buying.doctype.purchase_order.purchase_order", "make_purchase_receipt"),
    ("erpnext.accounts.doctype.sales_invoice.sales_invoice", "make_payment_entry"),
]:
    try:
        m = importlib.import_module(mod)
        out["helpers"][mod.split(".")[-1] + "." + fn] = callable(getattr(m, fn, None))
    except Exception as e:
        out["helpers"][mod.split(".")[-1] + "." + fn] = "ERR " + str(e)[:80]

print(json.dumps(out, ensure_ascii=False, indent=1, default=str))
