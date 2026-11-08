# -*- coding: utf-8 -*-
"""FLOW-97A 只读审计：销售订单 → 生产计划 → 采购申请 → 采购订单 → 入库 → 领料/发货。

严格只读：只调用 frappe.get_all / db.get_value / db.sql(SELECT)，不 insert/save/submit/cancel。
可在本地 POC 与线上站点运行：

    cd sites && ../env/bin/python /path/flow97_audit.py SAL-ORD-2026-00001 SAL-ORD-2026-00006

输出为可直接贴入证据文档的文本表格。
"""
import json
import os
import sys

import frappe

SITE = os.environ.get("FLOW97_SITE", "erpnext-poc.localhost")
SITES_PATH = os.environ.get("FLOW97_SITES", "/workspace/development/frappe-bench/sites")


def has(doctype, field):
    return frappe.get_meta(doctype).has_field(field)


def rows(doctype, filters, fields, order_by=None, limit=300):
    fields = [f for f in fields if f == "name" or has(doctype, f) or f in ("parent", "idx", "docstatus")]
    if not fields:
        return []
    return frappe.get_all(doctype, filters=filters, fields=fields,
                          order_by=order_by, limit=limit)


def doc(doctype, name, fields):
    fields = [f for f in fields if has(doctype, f) or f in ("name", "docstatus")]
    return frappe.db.get_value(doctype, name, fields, as_dict=True) or {}


def money(rows_):
    return round(sum(float(r.get("amount") or 0) for r in rows_), 2)


def audit(so_name):
    out = {"sales_order": so_name, "sections": {}}
    so = doc("Sales Order", so_name, [
        "name", "customer", "customer_name", "docstatus", "status", "business_type",
        "transaction_date", "delivery_date", "po_no", "project", "company", "currency",
        "grand_total", "per_delivered", "per_billed"])
    out["header"] = dict(so)

    items = rows("Sales Order Item", {"parent": so_name, "parenttype": "Sales Order"},
                 ["idx", "name", "item_code", "item_name", "qty", "delivered_qty", "bom_no",
                  "custom_bom_confirmed", "rate", "amount", "warehouse", "delivery_date"],
                 order_by="idx asc")
    from cn_mfg_poc.bom_link import bom_confirm_state, default_bom
    for r in items:
        state, confirmed = bom_confirm_state(r["item_code"], r.get("bom_no"),
                                             so.get("docstatus"), r.get("custom_bom_confirmed"))
        r["bom_state"] = state
        r["bom_confirmed_value"] = confirmed
        r["bom_raw"] = r.get("bom_no")
        r["default_bom"] = default_bom(r["item_code"])
    out["sections"]["items"] = items
    so_item_names = [r["name"] for r in items]
    so_item_codes = [r["item_code"] for r in items]

    # ---- 1. Production Plan（合并采购的源头；v16 引用表只有 sales_order / sales_order_item）
    pp_refs = rows("Production Plan Item Reference", {"sales_order": so_name},
                   ["parent", "idx", "sales_order", "sales_order_item", "qty", "item_reference"],
                   order_by="parent asc, idx asc")
    if so_item_names:
        seen = {(r["parent"], r["idx"]) for r in pp_refs}
        for r in rows("Production Plan Item Reference",
                      {"sales_order_item": ["in", so_item_names]},
                      ["parent", "idx", "sales_order", "sales_order_item", "qty", "item_reference"],
                      order_by="parent asc, idx asc"):
            if (r["parent"], r["idx"]) not in seen:
                pp_refs.append(r)
    out["sections"]["production_plan_refs"] = pp_refs
    pp_names = sorted({r["parent"] for r in pp_refs})

    pp_docs = []
    for p in pp_names:
        d = doc("Production Plan", p, ["name", "docstatus", "status", "company", "posting_date",
                                       "from_date", "to_date", "total_planned_qty",
                                       "total_produced_qty", "mr_generated", "po_generated"])
        pp_docs.append(d)
    out["sections"]["production_plans"] = pp_docs

    pp_items = []
    for p in pp_names:
        pp_items += rows("Production Plan Item", {"parent": p},
                         ["parent", "idx", "item_code", "bom_no", "planned_qty", "ordered_qty",
                          "produced_qty", "sales_order", "sales_order_item", "material_request",
                          "material_request_item", "warehouse"], order_by="idx asc")
    out["sections"]["production_plan_items"] = pp_items

    # 计划生成的采购申请（Production Plan Material Request 子表）
    pp_mrs = []
    for p in pp_names:
        pp_mrs += rows("Production Plan Material Request", {"parent": p},
                       ["parent", "idx", "material_request", "material_request_date"],
                       order_by="idx asc")
    out["sections"]["plan_material_requests"] = pp_mrs

    # 同一张计划里还有哪些销售订单（判断是否真的“合并”）
    pp_other_refs = []
    for p in pp_names:
        pp_other_refs += rows("Production Plan Item Reference", {"parent": p},
                              ["parent", "sales_order", "sales_order_item", "qty"])
    out["sections"]["plan_all_refs"] = pp_other_refs

    # ---- 2. Material Request（直接 sales_order + 经 Production Plan 间接）
    mr_direct = rows("Material Request Item", {"sales_order": so_name},
                     ["parent", "idx", "name", "item_code", "qty", "stock_qty", "warehouse",
                      "sales_order", "production_plan", "material_request_plan_item",
                      "ordered_qty", "received_qty", "docstatus"],
                     order_by="parent asc, idx asc")
    mr_indirect = []
    if pp_names:
        mr_indirect = rows("Material Request Item", {"production_plan": ["in", pp_names]},
                           ["parent", "idx", "name", "item_code", "qty", "warehouse",
                            "sales_order", "production_plan", "material_request_plan_item",
                            "ordered_qty", "received_qty", "docstatus"],
                           order_by="parent asc, idx asc")
    # 经计划生成的需求行（Production Plan.mr_items → Material Request Plan Item）
    mr_plan = []
    if pp_names:
        mr_plan = rows("Material Request Plan Item", {"parent": ["in", pp_names]},
                       ["parent", "idx", "name", "item_code", "quantity", "warehouse",
                        "sales_order", "material_request_type", "from_bom"],
                       order_by="parent asc, idx asc")
    out["sections"]["mr_direct_items"] = mr_direct
    out["sections"]["mr_via_plan_items"] = mr_indirect
    out["sections"]["mr_plan_items"] = mr_plan

    mr_names = sorted({r["parent"] for r in mr_direct + mr_indirect + mr_plan})
    out["sections"]["material_requests"] = [
        doc("Material Request", m, ["name", "docstatus", "status", "material_request_type",
                                    "transaction_date", "company", "per_ordered", "per_received"])
        for m in mr_names]
    mr_item_names = [r["name"] for r in mr_direct + mr_indirect + mr_plan if r.get("name")]

    # ---- 3. Purchase Order（直接 + 经 MR Item + 经 Production Plan）
    po_direct = rows("Purchase Order Item", {"sales_order": so_name},
                     ["parent", "idx", "name", "item_code", "qty", "received_qty", "billed_amt",
                      "amount", "warehouse", "sales_order", "material_request",
                      "material_request_item", "production_plan", "docstatus"],
                     order_by="parent asc, idx asc")
    po_via_mr = []
    if mr_item_names:
        po_via_mr = rows("Purchase Order Item", {"material_request_item": ["in", mr_item_names]},
                         ["parent", "idx", "name", "item_code", "qty", "received_qty",
                          "amount", "warehouse", "sales_order", "material_request",
                          "material_request_item", "production_plan", "docstatus"],
                         order_by="parent asc, idx asc")
    po_via_plan = []
    if pp_names:
        po_via_plan = rows("Purchase Order Item", {"production_plan": ["in", pp_names]},
                           ["parent", "idx", "name", "item_code", "qty", "received_qty",
                            "amount", "warehouse", "sales_order", "material_request",
                            "material_request_item", "production_plan", "docstatus"],
                           order_by="parent asc, idx asc")
    out["sections"]["po_direct_items"] = po_direct
    out["sections"]["po_via_mr_items"] = po_via_mr
    out["sections"]["po_via_plan_items"] = po_via_plan

    po_names = sorted({r["parent"] for r in po_direct + po_via_mr + po_via_plan})
    out["sections"]["purchase_orders"] = [
        doc("Purchase Order", p, ["name", "docstatus", "status", "supplier", "supplier_name",
                                  "transaction_date", "per_received", "per_billed", "grand_total",
                                  "currency", "company"])
        for p in po_names]
    po_item_names = [r["name"] for r in po_direct + po_via_mr + po_via_plan if r.get("name")]

    # ---- 4. Purchase Receipt（经 PO Item / PO / MR Item）
    pr_via_po_item, pr_via_po, pr_via_mr = [], [], []
    if po_item_names:
        pr_via_po_item = rows("Purchase Receipt Item", {"purchase_order_item": ["in", po_item_names]},
                              ["parent", "idx", "name", "item_code", "qty", "received_qty",
                               "warehouse", "purchase_order", "purchase_order_item",
                               "material_request", "material_request_item", "docstatus"],
                              order_by="parent asc, idx asc")
    if po_names:
        pr_via_po = rows("Purchase Receipt Item", {"purchase_order": ["in", po_names]},
                         ["parent", "idx", "name", "item_code", "qty", "warehouse",
                          "purchase_order", "purchase_order_item", "material_request",
                          "material_request_item", "docstatus"],
                         order_by="parent asc, idx asc")
    if mr_item_names:
        pr_via_mr = rows("Purchase Receipt Item", {"material_request_item": ["in", mr_item_names]},
                         ["parent", "idx", "name", "item_code", "qty", "warehouse",
                          "purchase_order", "purchase_order_item", "material_request",
                          "material_request_item", "docstatus"],
                         order_by="parent asc, idx asc")
    out["sections"]["pr_via_po_item"] = pr_via_po_item
    out["sections"]["pr_via_po"] = pr_via_po
    out["sections"]["pr_via_mr_item"] = pr_via_mr

    pr_names = sorted({r["parent"] for r in pr_via_po_item + pr_via_po + pr_via_mr})
    out["sections"]["purchase_receipts"] = [
        doc("Purchase Receipt", p, ["name", "docstatus", "status", "supplier", "posting_date",
                                    "per_billed", "company"])
        for p in pr_names]

    # ---- 5. Work Order（直接 + 经 Production Plan）
    wo_direct = rows("Work Order", {"sales_order": so_name},
                     ["name", "docstatus", "status", "production_item", "qty", "produced_qty",
                      "bom_no", "sales_order", "sales_order_item", "production_plan",
                      "material_transferred_for_manufacturing", "source_warehouse", "fg_warehouse",
                      "wip_warehouse", "planned_start_date", "planned_end_date"],
                     order_by="creation asc")
    wo_via_plan = []
    if pp_names:
        wo_via_plan = rows("Work Order", {"production_plan": ["in", pp_names]},
                           ["name", "docstatus", "status", "production_item", "qty", "produced_qty",
                            "bom_no", "sales_order", "sales_order_item", "production_plan",
                            "material_transferred_for_manufacturing", "source_warehouse",
                            "fg_warehouse", "wip_warehouse"],
                           order_by="creation asc")
    out["sections"]["work_orders_direct"] = wo_direct
    out["sections"]["work_orders_via_plan"] = wo_via_plan
    wo_names = sorted({w["name"] for w in wo_direct + wo_via_plan})

    # ---- 6. Stock Entry（按 Work Order）
    se_rows = rows("Stock Entry", {"work_order": ["in", wo_names or ["__none__"]]},
                   ["name", "docstatus", "status", "purpose", "work_order", "posting_date",
                    "from_warehouse", "to_warehouse", "total_outgoing_value"],
                   order_by="posting_date asc, creation asc")
    out["sections"]["stock_entries"] = se_rows
    se_names = [s["name"] for s in se_rows]
    se_items = rows("Stock Entry Detail", {"parent": ["in", se_names or ["__none__"]],
                                           "parenttype": "Stock Entry"},
                    ["parent", "idx", "item_code", "qty", "s_warehouse", "t_warehouse",
                     "against_stock_entry", "work_order"],
                    order_by="parent asc, idx asc", limit=600)
    out["sections"]["stock_entry_items"] = se_items

    # 按用途聚合（只算 docstatus=1）
    ok_se = {s["name"]: s for s in se_rows if int(s.get("docstatus") or 0) == 1}
    agg = {}
    for r in se_items:
        s = ok_se.get(r["parent"])
        if not s:
            continue
        key = (r["item_code"], s.get("purpose"))
        agg.setdefault(key, 0.0)
        agg[key] += float(r.get("qty") or 0)
    out["sections"]["issued_consumed_by_item"] = [
        {"item_code": k[0], "purpose": k[1], "qty": round(v, 4)} for k, v in sorted(agg.items())]

    # ---- 7. Delivery Note（真实发货）
    dn_items = rows("Delivery Note Item", {"against_sales_order": so_name},
                    ["parent", "idx", "item_code", "qty", "warehouse", "against_sales_order",
                     "so_detail", "docstatus"],
                    order_by="parent asc, idx asc")
    out["sections"]["delivery_note_items"] = dn_items
    dn_names = sorted({r["parent"] for r in dn_items})
    out["sections"]["delivery_notes"] = [
        doc("Delivery Note", d, ["name", "docstatus", "status", "posting_date", "customer",
                                 "per_billed"])
        for d in dn_names]

    # ---- 8. 库存快照（共享仓，不能当作本单独占）
    bins = []
    for code in sorted(set(so_item_codes) | {c["item_code"] for c in
                                             (pp_items or []) if c.get("item_code")}):
        bins += frappe.db.sql(
            "select item_code, warehouse, actual_qty, reserved_qty from tabBin "
            "where item_code=%s order by warehouse", code, as_dict=True)
    out["sections"]["bin_snapshot"] = [dict(b) for b in bins]

    # ---- 9. 结论辅助
    out["summary"] = {
        "sales_order": so_name,
        "so_items": [(r["item_code"], float(r["qty"] or 0), r["bom_state"]) for r in items],
        "production_plans": pp_names,
        "plan_contains_other_orders": sorted({
            r["sales_order"] for r in pp_other_refs
            if r.get("sales_order") and r.get("sales_order") != so_name}),
        "material_requests": mr_names,
        "purchase_orders": po_names,
        "purchase_receipts": pr_names,
        "work_orders": wo_names,
        "stock_entries": se_names,
        "delivery_notes": dn_names,
        "po_item_count": len(po_direct) + len(po_via_mr) + len(po_via_plan),
        "wo_sales_orders": sorted({w.get("sales_order") for w in wo_direct + wo_via_plan
                                   if w.get("sales_order")}),
    }
    return out


def main():
    os.chdir(SITES_PATH)
    frappe.init(site=SITE)
    frappe.connect()
    frappe.set_user(os.environ.get("FLOW97_USER", "Administrator"))
    targets = sys.argv[1:] or ["SAL-ORD-2026-00001", "SAL-ORD-2026-00006"]
    result = {"site": SITE, "orders": []}
    for so in targets:
        try:
            result["orders"].append(audit(so))
        except Exception as exc:  # noqa: BLE001
            result["orders"].append({"sales_order": so, "error": "%s: %s" % (
                type(exc).__name__, exc)})
    print("FLOW97_AUDIT_BEGIN")
    print(json.dumps(result, ensure_ascii=False, indent=1, default=str))
    print("FLOW97_AUDIT_END")


if __name__ == "__main__":
    main()
