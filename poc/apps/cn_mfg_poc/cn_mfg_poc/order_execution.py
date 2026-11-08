# -*- coding: utf-8 -*-
"""BUILD-92/93：订单执行概览与缺料契约（只读，聚合真实 ERPNext 原生单据）。

不新建业务权威数据、不写库；所有数量/状态来自 Sales Order、BOM、Material Request、
Purchase Order/Receipt、Work Order、Stock Entry、Delivery Note、Sales Invoice、
Payment Entry、Project/Task 的真实记录。财务字段按角色开放。
"""

import re
from urllib.parse import quote

import frappe
from frappe import _

READ_ROLES = {
    "Sales User", "Sales Manager", "Purchase User", "Purchase Manager",
    "Stock User", "Stock Manager", "Manufacturing User", "Manufacturing Manager",
    "Accounts User", "Accounts Manager", "System Manager",
}
FINANCE_ROLES = {"Accounts User", "Accounts Manager", "System Manager"}
SOURCE_WAREHOUSE = "原材料仓 - QC"


def _roles():
    return set(frappe.get_roles())


def _require(cond, msg, exc=frappe.PermissionError):
    if not cond:
        frappe.throw(msg, exc)


def _desk_url(doctype, name=None):
    """生成相对 Desk 路由，供 /cn_portal iframe 内页和原生新窗口共用。"""
    slug = re.sub(r"[^a-z0-9]+", "-", (doctype or "").lower()).strip("-")
    return "/desk/" + slug + ("/" + quote(str(name), safe="") if name else "")


def _linked(doctype, child_doctype, so_name, field="sales_order", fields=None):
    """按子表订单引用定位原生单据，返回父单据行 + 可点击链接。"""
    rows = frappe.get_all(child_doctype, filters={field: so_name},
                          fields=list({*(fields or ["name", "docstatus", "status"]), "parent"}),
                          limit=200)
    parents = []
    for r in rows:
        if r.get("parent") and r["parent"] not in parents:
            parents.append(r["parent"])
    docs = []
    meta = frappe.get_meta(doctype)
    extra = [f for f in ("docstatus", "status", "posting_date", "supplier", "grand_total", "purpose")
             if meta.has_field(f)]
    for name in parents:
        info = {"name": name, "url": _desk_url(doctype, name)}
        if extra:
            values = frappe.db.get_value(doctype, name, extra, as_dict=True) or {}
            info.update(values)
        docs.append(info)
    return docs, rows


def _sum_qty(rows, item_code=None, field="qty"):
    return sum(float(r.get(field) or 0) for r in rows
               if item_code is None or r.get("item_code") == item_code)


def _shortage_formula():
    return "max(0, required - available_now - received_qty - issued_net)"


def _progress(project):
    """只读聚合九阶段任务，不依赖 order_progress 的额外角色门槛。"""
    from cn_mfg_poc.production import due_state
    rows = frappe.get_all(
        "Task", filters={"project": project, "status": ("not in", ["Template", "Cancelled"])},
        fields=["name", "subject", "production_status", "status", "exp_end_date"], limit=100,
    )
    states = []
    for r in rows:
        d = dict(r)
        d["production_status"] = d.get("production_status") or "待开始"
        states.append(due_state(d))
    return {
        "started": True, "total": len(rows),
        "completed": sum(1 for s in states if s == "已完成"),
        "overdue": sum(1 for s in states if s == "逾期"),
        "due_soon": sum(1 for s in states if s == "临期"),
    }


@frappe.whitelist(methods=["GET"])
def order_summary(sales_order):
    """一张生产类销售订单的执行概览：真实单据链 + 物料覆盖 + 任务进度 + 财务（按权限）。"""
    _require(_roles() & READ_ROLES, _("当前角色无权查看订单执行概览"))
    so = frappe.db.get_value(
        "Sales Order", sales_order,
        ["name", "customer", "customer_name", "company", "status", "docstatus", "business_type",
         "transaction_date", "delivery_date", "grand_total", "per_delivered", "per_billed",
         "project", "currency"], as_dict=True,
    )
    _require(so, _("销售订单不存在：{0}").format(sales_order), frappe.ValidationError)
    _require(frappe.has_permission("Sales Order", "read", doc=sales_order)
             or (_roles() & {"System Manager", "Manufacturing Manager", "Stock Manager",
                             "Purchase Manager", "Accounts Manager"}),
             _("无权查看该销售订单"))

    finance = bool(_roles() & FINANCE_ROLES)
    so_items = frappe.get_all(
        "Sales Order Item",
        filters={"parent": sales_order, "parenttype": "Sales Order"},
        fields=["item_code", "item_name", "qty", "rate", "amount", "warehouse", "bom_no",
                "delivered_qty", "billed_amt", "delivery_date"], limit=50,
    )
    for r in so_items:
        if not finance:
            r["rate"] = r["amount"] = r["billed_amt"] = None

    # ---- 物料覆盖（订单选用 BOM 为准）
    components = []
    bom_names = []
    for row in so_items:
        bom_no = row.get("bom_no")
        if not bom_no:
            bom_no = frappe.db.get_value("BOM", {"item": row["item_code"], "is_active": 1,
                                                 "docstatus": 1, "is_default": 1}, "name")
        if not bom_no or not frappe.db.exists("BOM", bom_no):
            continue
        bom_names.append(bom_no)
        bom = frappe.get_doc("BOM", bom_no)
        factor = float(row["qty"] or 0) / (float(bom.quantity or 1) or 1)
        for b in bom.items:
            components.append({
                "item_code": b.item_code, "required_qty": float(b.qty or 0) * factor,
                "warehouse": b.get("source_warehouse") or SOURCE_WAREHOUSE,
                "bom": bom_no, "bom_url": _desk_url("BOM", bom_no),
            })

    mr_docs, mr_rows = _linked("Material Request", "Material Request Item", sales_order,
                               fields=["name", "item_code", "qty", "warehouse"])
    po_docs, po_rows = _linked("Purchase Order", "Purchase Order Item", sales_order,
                               fields=["name", "item_code", "qty", "warehouse", "received_qty"])
    pr_docs, pr_rows = _linked("Purchase Receipt", "Purchase Receipt Item", sales_order,
                               fields=["name", "item_code", "qty", "warehouse"])
    dn_docs, dn_rows = _linked("Delivery Note", "Delivery Note Item", sales_order,
                               field="against_sales_order",
                               fields=["name", "item_code", "qty", "warehouse"])
    si_docs, si_rows = _linked("Sales Invoice", "Sales Invoice Item", sales_order,
                               fields=["name", "item_code", "qty", "rate"])

    # 非财务角色连单据行里的金额也不能带出，只保留单据号/状态/日期用于追溯。
    if not finance:
        for group in (mr_docs, po_docs, pr_docs, dn_docs, si_docs):
            for d in group:
                d.pop("grand_total", None)

    wo_rows = frappe.get_all("Work Order", filters={"sales_order": sales_order},
                             fields=["name", "docstatus", "status", "production_item", "qty",
                                     "produced_qty", "bom_no", "skip_transfer", "wip_warehouse",
                                     "fg_warehouse", "source_warehouse"], limit=50)
    for w in wo_rows:
        w["url"] = _desk_url("Work Order", w["name"])
    wo_names = [w["name"] for w in wo_rows]
    se_rows = frappe.get_all("Stock Entry",
                             filters={"work_order": ["in", wo_names or ["__none__"]], "docstatus": 1},
                             fields=["name", "purpose", "work_order", "posting_date", "docstatus"],
                             limit=100) if wo_names else []
    for s in se_rows:
        s["url"] = _desk_url("Stock Entry", s["name"])
    se_names = [s["name"] for s in se_rows]
    se_items = frappe.get_all("Stock Entry Detail",
                              filters={"parent": ["in", se_names or ["__none__"]],
                                       "parenttype": "Stock Entry"},
                              fields=["parent", "item_code", "qty", "s_warehouse", "t_warehouse"],
                              limit=300) if se_names else []

    issued_rows = [r for r in se_items if r["parent"] in {
        s["name"] for s in se_rows if s["purpose"] == "Material Transfer for Manufacture"}]
    consumed_rows = [r for r in se_items if r["parent"] in {
        s["name"] for s in se_rows if s["purpose"] == "Manufacture"}]

    for c in components:
        code = c["item_code"]
        c["available_now"] = frappe.db.get_value(
            "Bin", {"item_code": code, "warehouse": c["warehouse"]}, "actual_qty") or 0
        c["purchased_qty"] = _sum_qty(po_rows, code)
        c["received_qty"] = _sum_qty(pr_rows, code)
        c["issued_qty"] = _sum_qty([r for r in issued_rows if r.get("item_code") == code])
        c["consumed_qty"] = _sum_qty([r for r in consumed_rows
                                      if r.get("item_code") == code and r.get("s_warehouse")])
        c["issued_net"] = max(0.0, c["issued_qty"] - c["consumed_qty"])
        c["shortage"] = max(0.0, c["required_qty"] - c["available_now"]
                            - c["received_qty"] - c["issued_net"])
        c["requested_qty"] = _sum_qty(mr_rows, code)

    # ---- 项目进度（BUILD-91 的 Project/Task，直接读同一份真实记录）
    project = frappe.db.get_value("Project", {"sales_order": sales_order}, "name")
    progress = _progress(project) if project else {"started": False}

    # ---- 财务（仅财务/系统角色）
    pe_docs = []
    if si_docs:
        refs = frappe.get_all("Payment Entry Reference",
                              filters={"reference_doctype": "Sales Invoice",
                                       "reference_name": ["in", [d["name"] for d in si_docs]]},
                              fields=["parent", "allocated_amount"], limit=100)
        for name in sorted({r["parent"] for r in refs}):
            pe_docs.append({"name": name, "url": _desk_url("Payment Entry", name),
                            "docstatus": frappe.db.get_value("Payment Entry", name, "docstatus"),
                            "paid_amount": (frappe.db.get_value("Payment Entry", name, "paid_amount")
                                            if finance else None)})
    si_outstanding = None
    if finance and si_docs:
        si_outstanding = sum(float(frappe.db.get_value("Sales Invoice", d["name"],
                                                       "outstanding_amount") or 0)
                             for d in si_docs)

    delivered_qty = _sum_qty(dn_rows)
    produced_qty = sum(float(w.get("produced_qty") or 0) for w in wo_rows)
    return {
        "user": frappe.session.user,
        "finance_visible": finance,
        "order": {
            "name": sales_order, "url": _desk_url("Sales Order", sales_order),
            "customer": so["customer"], "customer_name": so["customer_name"],
            "company": so["company"], "status": so["status"], "docstatus": so["docstatus"],
            "business_type": so["business_type"],
            "transaction_date": str(so["transaction_date"]),
            "delivery_date": str(so["delivery_date"]),
            "grand_total": so["grand_total"] if finance else None,
            "currency": so["currency"], "per_delivered": so["per_delivered"],
            "per_billed": so["per_billed"],
        },
        "items": so_items,
        "boms": [{"name": n, "url": _desk_url("BOM", n)} for n in sorted(set(bom_names))],
        "materials": {
            "components": components,
            "shortage_formula": _shortage_formula(),
            "total_shortage": sum(c["shortage"] for c in components),
        },
        "documents": {
            "material_request": mr_docs, "purchase_order": po_docs, "purchase_receipt": pr_docs,
            "work_order": wo_rows, "stock_entry": se_rows, "delivery_note": dn_docs,
            "sales_invoice": si_docs, "payment_entry": pe_docs,
        },
        "progress": {
            "project": project,
            "project_url": _desk_url("Project", project) if project else None,
            "started": progress.get("started"),
            "total": progress.get("total"), "completed": progress.get("completed"),
            "overdue": progress.get("overdue"), "due_soon": progress.get("due_soon"),
        },
        "physical": {
            "produced_qty": produced_qty,
            "delivered_qty": delivered_qty,
            "once_delivery": len(dn_docs) == 1,
            "job_cards": frappe.db.count("Job Card", {"work_order": ["in", wo_names or ["__none__"]]})
            if wo_names else 0,
        },
        "finance": ({
            "sales_invoice_total": sum(float(frappe.db.get_value("Sales Invoice", d["name"],
                                                                  "grand_total") or 0)
                                       for d in si_docs),
            "outstanding_amount": si_outstanding,
            "paid_amount": sum(float(d.get("paid_amount") or 0) for d in pe_docs),
        } if finance else None),
    }


@frappe.whitelist(methods=["GET"])
def materials_shortage(limit=20):
    """BUILD-93 轻量契约：未完成生产订单的 BOM 缺料清单（真实单据来源）。"""
    _require(_roles() & READ_ROLES, _("当前角色无权查看缺料"))
    orders = frappe.get_all(
        "Sales Order", filters={"business_type": "生产", "docstatus": 1,
                                "status": ("not in", ["Completed", "Cancelled", "Closed"])},
        fields=["name", "delivery_date", "customer_name"], order_by="delivery_date", limit=int(limit),
    )
    result = []
    for o in orders:
        try:
            summary = order_summary(o["name"])
        except Exception:
            continue
        shortage = [c for c in summary["materials"]["components"] if c["shortage"] > 0]
        if shortage:
            result.append({"sales_order": o["name"], "url": summary["order"]["url"],
                           "delivery_date": str(o["delivery_date"]),
                           "customer": o["customer_name"], "shortages": shortage})
    return {"user": frappe.session.user, "count": len(result), "orders": result,
            "shortage_formula": _shortage_formula()}
