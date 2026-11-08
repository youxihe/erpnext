# -*- coding: utf-8 -*-
"""BUILD-92 只读审计：订单 / BOM / 原生单据链 / 库存 / 角色，避免重复造数。"""
import json

import frappe

frappe.init(site="erpnext-poc.localhost", sites_path="/workspace/development/frappe-bench/sites")
frappe.connect()
frappe.set_user("Administrator")

out = {"errors": []}
SO = "SAL-ORD-2026-00005"


def safe_all(doctype, filters=None, fields=None, limit=30, order_by="creation"):
    try:
        return frappe.get_all(doctype, filters=filters or {}, fields=fields or ["name", "docstatus", "status"],
                              order_by=order_by, limit=limit)
    except Exception as e:
        out["errors"].append("%s: %s" % (doctype, str(e)[:200]))
        return []


so = frappe.get_doc("Sales Order", SO)
out["sales_order"] = {
    "name": so.name, "customer": so.customer, "status": so.status, "docstatus": so.docstatus,
    "business_type": so.business_type, "project": so.project,
    "transaction_date": str(so.transaction_date), "delivery_date": str(so.delivery_date),
    "grand_total": so.grand_total, "per_delivered": so.per_delivered, "per_billed": so.per_billed,
    "items": [{
        "item_code": r.item_code, "item_name": r.item_name, "qty": r.qty,
        "rate": r.rate, "delivery_date": str(r.delivery_date),
        "warehouse": r.get("warehouse"), "bom": r.get("bom_no") or r.get("bom"),
        "delivered_qty": r.get("delivered_qty"),
    } for r in so.items],
}

item_codes = sorted({r.item_code for r in so.items})
out["items"] = {}
for code in item_codes:
    doc = frappe.get_doc("Item", code)
    info = {
        "item": {k: doc.get(k) for k in ("name", "item_name", "is_stock_item", "stock_uom",
                                         "has_batch_no", "is_purchase_item", "is_sales_item")},
        "active_boms": safe_all("BOM", {"item": code, "is_active": 1, "docstatus": 1},
                                ["name", "item", "quantity", "with_operations", "default"]),
    }
    if info["active_boms"]:
        bom = frappe.get_doc("BOM", info["active_boms"][0]["name"])
        info["bom_items"] = [{
            "item_code": r.item_code, "qty": r.qty, "uom": r.uom,
            "source_warehouse": r.get("source_warehouse"),
        } for r in bom.items]
    out["items"][code] = info

out["linked"] = {
    "material_request": safe_all("Material Request", {"sales_order": SO},
                                 ["name", "docstatus", "status", "material_request_type"]),
    "material_request_items": safe_all("Material Request Item", {"sales_order": SO},
                                       ["parent", "item_code", "qty", "warehouse"]),
    "purchase_order": safe_all("Purchase Order", {"sales_order": SO},
                               ["name", "docstatus", "status", "supplier", "grand_total"]),
    "purchase_order_items": safe_all("Purchase Order Item", {"sales_order": SO},
                                     ["parent", "item_code", "qty", "received_qty"]),
    "purchase_receipt_items": safe_all("Purchase Receipt Item", {"sales_order": SO},
                                       ["parent", "item_code", "qty", "warehouse"]),
    "work_order": safe_all("Work Order", {"sales_order": SO},
                           ["name", "docstatus", "status", "production_item", "qty",
                            "produced_qty", "bom_no", "skip_transfer"]),
    "delivery_note_items": safe_all("Delivery Note Item", {"against_sales_order": SO},
                                    ["parent", "item_code", "qty", "warehouse"]),
    "sales_invoice": safe_all("Sales Invoice", {"sales_order": SO},
                              ["name", "docstatus", "status", "grand_total", "outstanding_amount"]),
    "sales_invoice_items": safe_all("Sales Invoice Item", {"sales_order": SO},
                                    ["parent", "item_code", "qty"]),
    "payment_entries": safe_all("Payment Entry", None,
                                ["name", "docstatus", "payment_type", "paid_amount", "party"], 30),
    "production_plan": safe_all("Production Plan", None,
                                ["name", "docstatus", "status", "posting_date"], 20),
}

out["warehouses"] = safe_all("Warehouse", {"is_group": 0}, ["name", "warehouse_name", "company"], 50)
out["bins"] = safe_all("Bin", None, ["item_code", "warehouse", "actual_qty", "ordered_qty",
                                     "reserved_qty", "valuation_rate"], 200)
out["sle_count"] = frappe.db.count("Stock Ledger Entry")
out["stock_entries_recent"] = safe_all("Stock Entry", None,
                                       ["name", "docstatus", "purpose", "work_order", "posting_date"],
                                       20, order_by="creation desc")

out["orders_by_type"] = {}
for t in ["生产", "耗材", "零部件", "服务"]:
    out["orders_by_type"][t] = safe_all("Sales Order", {"business_type": t},
                                        ["name", "status", "docstatus", "per_delivered", "per_billed"], 20)

out["users"] = {}
for u in frappe.get_all("User", filters={"enabled": 1, "name": ("not in", ["Administrator", "Guest"])},
                        pluck="name", limit=40):
    out["users"][u] = sorted(r for r in frappe.get_roles(u) if r not in ("All", "Guest", "Desk User"))

print(json.dumps(out, ensure_ascii=False, indent=1, default=str))
