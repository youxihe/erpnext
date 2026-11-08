# -*- coding: utf-8 -*-
"""FLOW-97B：多订单需求 → 合并采购 → 入库 → 按工单领料的原生单据追溯（只读）。

设计约束（见 docs/product/tasks/FLOW-97.md）：
- 只复用 ERPNext 原生引用字段，不新建需求/分配表，不做 MRP 或库存预留；
- 每一条关联都必须能被原生字段证明，否则显式标注「来源不可证实」；
- 合并计划下的数量按 `Production Plan Item Reference` 的订单数量比例**估算**，
  明确标注为估算，不冒充原生分单；
- 库存是共享 Bin，不按订单锁定；本单已领/已耗来自对应工单的 Stock Entry。
"""

import frappe
from frappe import _

from cn_mfg_poc.order_execution import (
    FINANCE_ROLES,
    READ_ROLES,
    SOURCE_WAREHOUSE,
    _desk_url,
    _require,
    _roles,
)

PURCHASE_ROLES = {"Purchase User", "Purchase Manager", "Stock User", "Stock Manager",
                  "System Manager"}
SENIOR_ROLES = {"System Manager", "Manufacturing Manager", "Stock Manager",
                "Purchase Manager", "Accounts Manager", "Sales Manager"}

SOURCE_LABELS = {
    "direct": "直接引用",
    "via_mr": "经采购申请行",
    "via_plan": "经生产计划",
    "plan_shared": "计划共享（按订单数量比例估算）",
    "no_po": "无采购订单入库（来源不可证实）",
    "unverified": "来源不可证实（无原生引用）",
}


def _status_map(doctype, names):
    if not names:
        return {}
    rows = frappe.get_all(doctype, filters={"name": ["in", list(names)]},
                          fields=["name", "docstatus", "status"], limit=500)
    return {r["name"]: r for r in rows}


def _num(v):
    return round(float(v or 0), 4)


# --------------------------------------------------------------------- 计划上下文
def plan_context(sales_order, so_item_names):
    """本订单命中的 Production Plan 及「本单占比」。

    v16 的 `Production Plan Item Reference` 只有 sales_order / sales_order_item / qty，
    是唯一能证明「一张计划合并了哪几张订单」的原生表。
    """
    rows = frappe.get_all("Production Plan Item Reference",
                          filters={"sales_order": sales_order},
                          fields=["parent", "sales_order", "sales_order_item", "qty"],
                          limit=200)
    if so_item_names:
        seen = {(r["parent"], r["sales_order_item"]) for r in rows}
        for r in frappe.get_all("Production Plan Item Reference",
                                filters={"sales_order_item": ["in", list(so_item_names)]},
                                fields=["parent", "sales_order", "sales_order_item", "qty"],
                                limit=200):
            if (r["parent"], r["sales_order_item"]) not in seen:
                rows.append(r)
    plans = {}
    for r in rows:
        p = plans.setdefault(r["parent"], {"name": r["parent"], "my_qty": 0.0})
        p["my_qty"] += float(r["qty"] or 0)
    # 有些计划没有写订单引用表（手工建计划 / 早期单据），但 MR 行或工单上留了
    # production_plan；这类计划仍要展示，只是不能按比例分单，必须标「来源不可证实」。
    extra = {r["production_plan"] for r in frappe.get_all(
        "Material Request Item", filters={"sales_order": sales_order},
        fields=["production_plan"], limit=200) if r.get("production_plan")}
    extra |= {r["production_plan"] for r in frappe.get_all(
        "Work Order", filters={"sales_order": sales_order},
        fields=["production_plan"], limit=100) if r.get("production_plan")}
    for name in sorted(extra - set(plans)):
        plans[name] = {"name": name, "my_qty": 0.0, "refs_missing": True}
    for name, p in plans.items():
        head = frappe.db.get_value("Production Plan", name,
                                   ["docstatus", "status", "total_planned_qty"], as_dict=True) or {}
        refs = frappe.get_all("Production Plan Item Reference", filters={"parent": name},
                              fields=["sales_order", "sales_order_item", "qty"], limit=200)
        total = sum(float(x["qty"] or 0) for x in refs) or float(head.get("total_planned_qty") or 0)
        other = sorted({x["sales_order"] for x in refs
                        if x["sales_order"] and x["sales_order"] != sales_order})
        p.update({
            "url": _desk_url("Production Plan", name),
            "docstatus": head.get("docstatus"),
            "status": head.get("status"),
            "total_qty": _num(total),
            "refs": [{"sales_order": x["sales_order"], "qty": _num(x["qty"])} for x in refs],
            "other_orders": other,
            "shared": bool(other),
            "refs_missing": not refs,
            "share": (round(p["my_qty"] / total, 4) if (refs and total) else 1.0),
        })
    return plans


def _merge(rows, key="name"):
    out, seen = [], set()
    for r in rows:
        k = r.get(key)
        if k in seen:
            continue
        seen.add(k)
        out.append(r)
    return out


def _sources(so, mr_item_names, plan_names, doc):
    """判定一条子表行的来源类型（尽量用原生引用字段，不按 SKU/时间猜）。"""
    if doc.get("sales_order") == so:
        return "direct"
    if mr_item_names and doc.get("material_request_item") in mr_item_names:
        return "via_mr"
    if plan_names and doc.get("production_plan") in plan_names:
        return "via_plan"
    return "unverified"


# --------------------------------------------------------------------- 订单级追溯
@frappe.whitelist(methods=["GET"])
def order_material_trace(sales_order):
    """一张销售订单的「物料需求及采购履约」：需求 / 申请 / 下单 / 到货 / 领用 逐行可点。"""
    _require(_roles() & READ_ROLES, _("当前角色无权查看订单物料追溯"))
    so = frappe.db.get_value(
        "Sales Order", sales_order,
        ["name", "customer", "customer_name", "docstatus", "status", "transaction_date",
         "delivery_date", "project", "currency", "grand_total"], as_dict=True)
    _require(so, _("销售订单不存在：{0}").format(sales_order), frappe.ValidationError)
    _require(frappe.has_permission("Sales Order", "read", doc=sales_order)
             or (_roles() & SENIOR_ROLES) or _is_order_worker(sales_order),
             _("无权查看该销售订单"))

    finance = bool(_roles() & FINANCE_ROLES)
    items = frappe.get_all(
        "Sales Order Item",
        filters={"parent": sales_order, "parenttype": "Sales Order"},
        fields=["name", "idx", "item_code", "item_name", "qty", "delivered_qty", "bom_no",
                "custom_bom_confirmed", "warehouse", "delivery_date", "amount"],
        order_by="idx asc", limit=50)

    from cn_mfg_poc.bom_link import bom_confirm_state, bom_or_default, default_bom

    for r in items:
        state, confirmed = bom_confirm_state(r["item_code"], r.get("bom_no"),
                                             so["docstatus"], r.get("custom_bom_confirmed"))
        r["bom_state"] = state
        r["bom_confirmed"] = state == "explicit"
        r["bom_carried"] = r.get("bom_no") if state != "explicit" else None
        r["bom_no"] = confirmed
        r["default_bom"] = default_bom(r["item_code"])
        if not finance:
            r["amount"] = None
    so_item_names = [r["name"] for r in items]

    plans = plan_context(sales_order, so_item_names)
    plan_names = sorted(plans)

    # ---- 需求（MR）：直接归属 + 计划共享
    mr_fields = ["name", "parent", "idx", "item_code", "qty", "ordered_qty", "received_qty",
                 "warehouse", "sales_order", "production_plan", "material_request_plan_item"]
    mr_rows = frappe.get_all("Material Request Item", filters={"sales_order": sales_order},
                             fields=mr_fields, limit=300)
    if plan_names:
        mr_rows = _merge(mr_rows + frappe.get_all(
            "Material Request Item", filters={"production_plan": ["in", plan_names]},
            fields=mr_fields, limit=300))
    mr_item_names = {r["name"] for r in mr_rows}
    mr_docs = _status_map("Material Request", {r["parent"] for r in mr_rows})

    # ---- 采购（PO）：直接 / 经 MR 行 / 经计划
    po_fields = ["name", "parent", "idx", "item_code", "qty", "received_qty", "warehouse",
                 "sales_order", "material_request", "material_request_item", "production_plan",
                 "amount"]
    po_filters = [{"sales_order": sales_order}]
    if mr_item_names:
        po_filters.append({"material_request_item": ["in", list(mr_item_names)]})
    if plan_names:
        po_filters.append({"production_plan": ["in", plan_names]})
    po_rows = []
    for f in po_filters:
        po_rows += frappe.get_all("Purchase Order Item", filters=f, fields=po_fields, limit=300)
    po_rows = _merge(po_rows)
    po_item_names = {r["name"] for r in po_rows}
    po_names = {r["parent"] for r in po_rows}
    po_docs = _status_map("Purchase Order", po_names)
    # 共享计划下的采购行整行属于计划，入库行要按同一比例展示，否则会把计划总量当成单订单量
    mr_plan_of_item = {m["name"]: m.get("production_plan") for m in mr_rows}
    po_share = {}
    for r in po_rows:
        plan = r.get("production_plan") or mr_plan_of_item.get(r.get("material_request_item"))
        if plan in plans and not plans[plan].get("refs_missing"):
            po_share[r["parent"]] = plans[plan]["share"]

    # ---- 入库（PR）：经 PO 行 / PO / MR 行 / 直接挂订单
    pr_fields = ["name", "parent", "idx", "item_code", "qty", "warehouse", "sales_order",
                 "purchase_order", "purchase_order_item", "material_request_item"]
    pr_filters = [{"sales_order": sales_order}]
    if po_names:
        pr_filters.append({"purchase_order": ["in", list(po_names)]})
    if po_item_names:
        pr_filters.append({"purchase_order_item": ["in", list(po_item_names)]})
    if mr_item_names:
        pr_filters.append({"material_request_item": ["in", list(mr_item_names)]})
    pr_rows = []
    for f in pr_filters:
        pr_rows += frappe.get_all("Purchase Receipt Item", filters=f, fields=pr_fields, limit=300)
    pr_rows = _merge(pr_rows)
    pr_docs = _status_map("Purchase Receipt", {r["parent"] for r in pr_rows})

    # ---- 工单 + 领料/耗用
    wo_fields = ["name", "docstatus", "status", "production_item", "qty", "produced_qty",
                 "sales_order", "production_plan", "sales_order_item"]
    wo_rows = frappe.get_all("Work Order", filters={"sales_order": sales_order},
                             fields=wo_fields, limit=100)
    if plan_names:
        wo_rows = _merge(wo_rows + frappe.get_all(
            "Work Order", filters={"production_plan": ["in", plan_names]},
            fields=wo_fields, limit=100))
    wo_names = [w["name"] for w in wo_rows]
    se_rows = frappe.get_all(
        "Stock Entry", filters={"work_order": ["in", wo_names or ["__none__"]], "docstatus": 1},
        fields=["name", "purpose", "work_order", "posting_date"], limit=200) if wo_names else []
    se_names = [s["name"] for s in se_rows]
    se_items = frappe.get_all(
        "Stock Entry Detail",
        filters={"parent": ["in", se_names or ["__none__"]], "parenttype": "Stock Entry"},
        fields=["parent", "item_code", "qty", "s_warehouse", "t_warehouse"], limit=600
    ) if se_names else []
    se_purpose = {s["name"]: s["purpose"] for s in se_rows}
    wo_shared = {w["name"]: (not w.get("sales_order") and w.get("production_plan") in plans)
                 for w in wo_rows}

    # ---- 组件（以本单 BOM 为准）
    components = []
    for row in items:
        bom_no, bom_source = bom_or_default(row["item_code"], row.get("bom_no"))
        if not bom_no or not frappe.db.exists("BOM", bom_no):
            continue
        bom = frappe.get_doc("BOM", bom_no)
        factor = float(row["qty"] or 0) / (float(bom.quantity or 1) or 1)
        for b in bom.items:
            components.append({
                "item_code": b.item_code,
                "item_name": b.get("item_name") or b.item_code,
                "warehouse": b.get("source_warehouse") or SOURCE_WAREHOUSE,
                "required_qty": _num(float(b.qty or 0) * factor),
                "bom": bom_no,
                "bom_source": bom_source,
            })
    components = _merge(components, key="item_code")

    def share_of(doc):
        plan = doc.get("production_plan")
        return plans[plan]["share"] if plan in plans else 1.0

    for c in components:
        code = c["item_code"]

        demand, purchase, receipt = [], [], []
        for r in mr_rows:
            if r["item_code"] != code:
                continue
            src = "direct" if r.get("sales_order") == sales_order else (
                "plan_shared" if (r.get("production_plan") in plans
                                  and not plans[r["production_plan"]].get("refs_missing"))
                else "unverified")
            doc = mr_docs.get(r["parent"], {})
            demand.append({
                "doc": r["parent"], "url": _desk_url("Material Request", r["parent"]),
                "line": r.get("idx"), "qty": _num(r["qty"]),
                "estimated_qty": _num(float(r["qty"] or 0) * share_of(r)),
                "ordered_qty": _num(r.get("ordered_qty")),
                "received_qty": _num(r.get("received_qty")),
                "docstatus": doc.get("docstatus"), "status": doc.get("status"),
                "plan": r.get("production_plan"), "source": src,
                "source_label": SOURCE_LABELS[src],
            })
        for r in po_rows:
            if r["item_code"] != code:
                continue
            src = _sources(sales_order, mr_item_names, plan_names, r)
            doc = po_docs.get(r["parent"], {})
            qty = float(r["qty"] or 0)
            got = float(r["received_qty"] or 0)
            ratio = po_share.get(r["parent"], share_of(r))
            purchase.append({
                "doc": r["parent"], "url": _desk_url("Purchase Order", r["parent"]),
                "line": r.get("idx"), "qty": _num(qty), "received_qty": _num(got),
                "pending_qty": _num(max(0.0, qty - got)),
                "estimated_qty": _num(qty * ratio),
                "share": ratio,
                "docstatus": doc.get("docstatus"), "status": doc.get("status"),
                "mr": r.get("material_request"), "source": src,
                "source_label": SOURCE_LABELS[src],
                "amount": _num(r.get("amount")) if finance else None,
            })
        for r in pr_rows:
            if r["item_code"] != code:
                continue
            if r.get("purchase_order"):
                src = "via_mr" if r.get("material_request_item") in mr_item_names else "direct"
            else:
                src = "no_po"
            doc = pr_docs.get(r["parent"], {})
            ratio = po_share.get(r.get("purchase_order"), share_of(r))
            receipt.append({
                "doc": r["parent"], "url": _desk_url("Purchase Receipt", r["parent"]),
                "line": r.get("idx"), "qty": _num(r["qty"]),
                "estimated_qty": _num(float(r["qty"] or 0) * ratio),
                "share": ratio,
                "docstatus": doc.get("docstatus"), "status": doc.get("status"),
                "po": r.get("purchase_order"), "source": src,
                "source_label": SOURCE_LABELS[src],
            })

        issued = consumed = 0.0
        issued_est = consumed_est = 0.0
        for r in se_items:
            if r["item_code"] != code:
                continue
            purpose = se_purpose.get(r["parent"])
            qty = float(r["qty"] or 0)
            wo = next((w for w in wo_rows if w["name"] ==
                       next((s["work_order"] for s in se_rows if s["name"] == r["parent"]), None)), None)
            ratio = 1.0
            if wo and wo_shared.get(wo["name"]):
                ratio = plans[wo["production_plan"]]["share"] if wo.get("production_plan") in plans else 1.0
            if purpose == "Material Transfer for Manufacture":
                issued += qty
                issued_est += qty * ratio
            elif purpose == "Manufacture" and r.get("s_warehouse"):
                consumed += qty
                consumed_est += qty * ratio

        submitted_po = [p for p in purchase if p["docstatus"] == 1]
        submitted_pr = [r for r in receipt if r["docstatus"] == 1]
        pending = _num(sum(max(0.0, p["qty"] - p["received_qty"]) * p.get("share", 1.0)
                           for p in submitted_po))
        no_po_qty = _num(sum(r["estimated_qty"] for r in submitted_pr if r["source"] == "no_po"))
        got_from_po = _num(sum(r["estimated_qty"] for r in submitted_pr
                               if r["source"] != "no_po"))
        shared_wo = [w for w in wo_rows if wo_shared.get(w["name"])]
        # 工单既没直接挂本订单、计划又缺订单引用表 → 领料数量无法归属本单
        orphan_wo = [w for w in wo_rows
                     if not w.get("sales_order")
                     and (w.get("production_plan") not in plans
                          or plans[w["production_plan"]].get("refs_missing"))]

        warnings = []
        if pending > 0 and no_po_qty > 0:
            warnings.append(
                _("同一物料既有未收货采购订单（{0}）又有无采购订单的入库（{1}）："
                  "若按 PO 继续收货会重复到货，请先核对是否同一批。").format(pending, no_po_qty))
        if demand and all(d["source"] == "unverified" for d in demand):
            warnings.append(_("采购申请行没有指向本订单，也不是本订单的生产计划生成，来源不可证实。"))
        if not purchase and receipt:
            warnings.append(_("有入库但没有采购订单，无法追溯到采购来源。"))
        if orphan_wo and (issued or consumed):
            warnings.append(_("对应工单既未直接挂本订单，生产计划也缺订单引用表，"
                              "领料/耗用数量无法按订单拆分。"))
        if shared_wo and (issued or consumed):
            others = sorted({o for p in plans.values() for o in p["other_orders"]})
            warnings.append(_("本单与 {0} 共用一张工单（{1}），领料/耗用按计划订单数量比例估算，"
                              "实际是整张工单一起领。").format(
                                  "、".join(others) or _("其它订单"),
                                  "、".join(w["name"] for w in shared_wo)))

        c.update({
            "demand": demand,
            "purchase": purchase,
            "receipt": receipt,
            "requested_qty": _num(sum(d["qty"] for d in demand if d["docstatus"] == 1
                                      and d["source"] == "direct")
                                  + sum(d["estimated_qty"] for d in demand if d["docstatus"] == 1
                                        and d["source"] == "plan_shared")),
            "ordered_qty": _num(sum(p["estimated_qty"] for p in submitted_po)),
            "received_qty": _num(got_from_po + no_po_qty),
            "received_from_po": got_from_po,
            "received_without_po": no_po_qty,
            "pending_qty": pending,
            "issued_qty": _num(issued),
            "consumed_qty": _num(consumed),
            "issued_estimated": _num(issued_est),
            "consumed_estimated": _num(consumed_est),
            "issued_shared": bool(shared_wo),
            "available_now": _num(frappe.db.get_value(
                "Bin", {"item_code": code, "warehouse": c["warehouse"]}, "actual_qty")),
            "warnings": warnings,
            "unverifiable": bool(warnings) or any(
                x["source"] == "unverified" for x in purchase + receipt),
        })

    proof_count = sum(1 for c in components for x in c["purchase"] + c["receipt"]
                      if x["source"] != "unverified" and x["source"] != "no_po")
    unknown_count = sum(1 for c in components for x in c["purchase"] + c["receipt"]
                        if x["source"] in ("unverified", "no_po"))

    return {
        "sales_order": sales_order,
        "header": {
            "customer": so.get("customer_name") or so.get("customer"),
            "docstatus": so.get("docstatus"), "status": so.get("status"),
            "transaction_date": so.get("transaction_date"),
            "delivery_date": so.get("delivery_date"),
            "project": so.get("project"),
            "grand_total": so.get("grand_total") if finance else None,
            "currency": so.get("currency"),
        },
        "items": items,
        "plans": list(plans.values()),
        "components": components,
        "work_orders": [{
            "name": w["name"], "url": _desk_url("Work Order", w["name"]),
            "docstatus": w.get("docstatus"), "status": w.get("status"),
            "qty": _num(w.get("qty")), "produced_qty": _num(w.get("produced_qty")),
            "sales_order": w.get("sales_order"), "production_plan": w.get("production_plan"),
            "shared": wo_shared.get(w["name"], False),
        } for w in wo_rows],
        "stock_entries": [{
            "name": s["name"], "url": _desk_url("Stock Entry", s["name"]),
            "purpose": s["purpose"], "work_order": s.get("work_order"),
            "posting_date": s.get("posting_date"),
        } for s in se_rows],
        "summary": {
            "plans": plan_names,
            "shared_plan": any(p["shared"] for p in plans.values()),
            "shared_with": sorted({o for p in plans.values() for o in p["other_orders"]}),
            "proof_links": proof_count,
            "unverifiable_links": unknown_count,
            "all_proven": unknown_count == 0,
            "stock_note": _("列表里的「现存」是 BOM 发料仓的共享库存（Bin），不按订单锁定；"
                            "多张订单会看到同一个数字，也不是某张采购入库单的专属实物。"),
            "estimate_note": _("合并生产计划下的申请/采购/领料数量按 "
                               "Production Plan Item Reference 的订单数量比例估算，标为「计划共享」；"
                               "只有订单行直接引用或单订单计划时才是确切归属。"),
            "finance_visible": finance,
        },
    }


def _is_order_worker(sales_order):
    return bool(frappe.db.exists("Task", {
        "source_sales_order": sales_order,
        "production_owner": frappe.session.user,
        "status": ("not in", ["Template", "Cancelled"]),
    }))


# --------------------------------------------------------------------- 采购级反查
@frappe.whitelist(methods=["GET"])
def po_options(limit=20):
    """采购角色可选的采购订单（按权限过滤）。"""
    _require(_roles() & PURCHASE_ROLES, _("当前角色无权查看集中采购来源"))
    rows = frappe.get_all("Purchase Order",
                          filters={"docstatus": ["<", 2]},
                          fields=["name", "supplier", "supplier_name", "transaction_date",
                                  "status", "docstatus", "grand_total"],
                          order_by="transaction_date desc, name desc", limit=int(limit))
    out = []
    for r in rows:
        if not frappe.has_permission("Purchase Order", "read", doc=r["name"]):
            continue
        out.append({
            "name": r["name"], "url": _desk_url("Purchase Order", r["name"]),
            "supplier": r.get("supplier_name") or r.get("supplier"),
            "transaction_date": r.get("transaction_date"),
            "status": r.get("status"), "docstatus": r.get("docstatus"),
        })
    return {"purchase_orders": out, "count": len(out)}


@frappe.whitelist(methods=["GET"])
def purchase_trace(purchase_order):
    """一张采购订单的集中采购来源：PO 行 → MR 行 → 生产计划 → 各销售订单需求。"""
    _require(_roles() & PURCHASE_ROLES, _("当前角色无权查看集中采购来源"))
    _require(frappe.has_permission("Purchase Order", "read", doc=purchase_order),
             _("无权查看该采购订单"))
    finance = bool(_roles() & FINANCE_ROLES)
    po = frappe.db.get_value(
        "Purchase Order", purchase_order,
        ["name", "supplier", "supplier_name", "docstatus", "status", "transaction_date",
         "company", "currency", "grand_total", "per_received"], as_dict=True)
    _require(po, _("采购订单不存在：{0}").format(purchase_order), frappe.ValidationError)

    items = frappe.get_all(
        "Purchase Order Item",
        filters={"parent": purchase_order, "parenttype": "Purchase Order"},
        fields=["name", "idx", "item_code", "item_name", "qty", "received_qty", "warehouse",
                "sales_order", "sales_order_item", "material_request", "material_request_item",
                "production_plan", "amount", "schedule_date"],
        order_by="idx asc", limit=200)

    pr_rows = frappe.get_all(
        "Purchase Receipt Item", filters={"purchase_order": purchase_order},
        fields=["name", "parent", "idx", "item_code", "qty", "warehouse",
                "purchase_order_item"], limit=400)
    pr_docs = _status_map("Purchase Receipt", {r["parent"] for r in pr_rows})

    so_cache = {}

    def so_brief(name):
        if name not in so_cache:
            d = frappe.db.get_value("Sales Order", name,
                                    ["name", "customer_name", "customer", "status", "docstatus",
                                     "delivery_date"], as_dict=True) or {}
            so_cache[name] = {
                "name": name, "url": _desk_url("Sales Order", name),
                "customer": d.get("customer_name") or d.get("customer"),
                "status": d.get("status"), "docstatus": d.get("docstatus"),
                "delivery_date": d.get("delivery_date"),
            }
        return so_cache[name]

    out_items, all_sos, warnings = [], set(), []
    for r in items:
        mr_item = frappe.db.get_value(
            "Material Request Item", r.get("material_request_item"),
            ["parent", "idx", "qty", "ordered_qty", "received_qty", "sales_order",
             "production_plan", "material_request_plan_item"], as_dict=True) if r.get(
                "material_request_item") else None
        mr_doc = (_status_map("Material Request", {mr_item["parent"]}).get(mr_item["parent"])
                  if mr_item else None)

        plan = None
        plan_refs = []
        plan_name = (mr_item or {}).get("production_plan") or r.get("production_plan")
        planned_share = None
        if plan_name and frappe.db.exists("Production Plan", plan_name):
            head = frappe.db.get_value("Production Plan", plan_name,
                                       ["docstatus", "status", "total_planned_qty"], as_dict=True)
            refs = frappe.get_all("Production Plan Item Reference", filters={"parent": plan_name},
                                  fields=["sales_order", "qty"], limit=200)
            total = sum(float(x["qty"] or 0) for x in refs) or float(
                (head or {}).get("total_planned_qty") or 0)
            plan_refs = [dict(so_brief(x["sales_order"]), qty=_num(x["qty"]),
                              estimated_qty=_num(float(x["qty"] or 0) / total * float(r["qty"] or 0))
                              if total else _num(r["qty"])) for x in refs if x.get("sales_order")]
            for x in plan_refs:
                all_sos.add(x["name"])
            planned_share = plan_refs
            plan = {
                "name": plan_name, "url": _desk_url("Production Plan", plan_name),
                "docstatus": (head or {}).get("docstatus"), "status": (head or {}).get("status"),
                "total_qty": _num(total), "shared": len(refs) > 1,
            }

        direct_so = r.get("sales_order")
        if direct_so:
            all_sos.add(direct_so)

        if mr_item:
            source = "via_mr"
        elif plan:
            source = "via_plan"
        elif direct_so:
            source = "direct"
        else:
            source = "unverified"

        receipts = []
        for p in pr_rows:
            if p.get("purchase_order_item") != r["name"]:
                continue
            doc = pr_docs.get(p["parent"], {})
            receipts.append({
                "doc": p["parent"], "url": _desk_url("Purchase Receipt", p["parent"]),
                "line": p.get("idx"), "qty": _num(p["qty"]),
                "docstatus": doc.get("docstatus"), "status": doc.get("status"),
            })
        received = _num(sum(x["qty"] for x in receipts if x["docstatus"] == 1))

        out_items.append({
            "line": r.get("idx"), "item_code": r["item_code"],
            "item_name": r.get("item_name"), "qty": _num(r["qty"]),
            "received_qty": received,
            "pending_qty": _num(max(0.0, float(r["qty"] or 0) - received)),
            "warehouse": r.get("warehouse"),
            "amount": _num(r.get("amount")) if finance else None,
            "source": source, "source_label": SOURCE_LABELS[source],
            "material_request": {
                "name": mr_item["parent"], "url": _desk_url("Material Request", mr_item["parent"]),
                "line": mr_item.get("idx"), "qty": _num(mr_item.get("qty")),
                "docstatus": (mr_doc or {}).get("docstatus"),
                "status": (mr_doc or {}).get("status"),
            } if mr_item else None,
            "plan": plan,
            "plan_orders": plan_refs,
            "direct_order": so_brief(direct_so) if direct_so else None,
            "receipts": receipts,
        })
        if source == "unverified":
            warnings.append(_("第 {0} 行 {1} 没有采购申请或生产计划引用，无法证明对应哪张销售订单。").format(
                r.get("idx"), r["item_code"]))

    # 收货行里没有 PO 引用的（直接挂订单的采购入库）单独提示
    return {
        "purchase_order": purchase_order,
        "header": {
            "supplier": po.get("supplier_name") or po.get("supplier"),
            "docstatus": po.get("docstatus"), "status": po.get("status"),
            "transaction_date": po.get("transaction_date"),
            "per_received": po.get("per_received"),
            "grand_total": po.get("grand_total") if finance else None,
            "currency": po.get("currency"),
        },
        "items": out_items,
        "orders": [so_brief(n) for n in sorted(all_sos)],
        "warnings": warnings,
        "summary": {
            "unverifiable_lines": sum(1 for i in out_items if i["source"] == "unverified"),
            "shared_plan_lines": sum(1 for i in out_items if i["plan"] and i["plan"]["shared"]),
            "orders": sorted(all_sos),
            "note": _("一张采购订单可以拉多张采购申请的多行；同一 SKU 被压成一行时，"
                      "原生 material_request_item 只能记一个来源，其余来源不可证实。"),
            "source_note": _("来源字段：material_request_item / production_plan / sales_order"),
            "finance_visible": finance,
        },
    }
