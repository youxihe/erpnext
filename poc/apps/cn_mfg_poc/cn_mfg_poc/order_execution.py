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
# 缺料属于生产/仓库/采购职能；销售按单看进度即可，不开放全局缺料清单。
SHORTAGE_ROLES = {
    "Manufacturing User", "Manufacturing Manager", "Stock User", "Stock Manager",
    "Purchase User", "Purchase Manager", "System Manager",
}
SENIOR_ROLES = {"System Manager", "Manufacturing Manager", "Stock Manager",
                "Purchase Manager", "Accounts Manager", "Sales Manager"}
SOURCE_WAREHOUSE = "原材料仓 - QC"


def _roles():
    return set(frappe.get_roles())


def _is_order_worker(sales_order):
    """当前用户是否是这张订单上某个生产任务的负责人（生产人员按单看进度）。"""
    return bool(frappe.db.exists("Task", {
        "source_sales_order": sales_order,
        "production_owner": frappe.session.user,
        "status": ("not in", ["Template", "Cancelled"]),
    }))


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
    # docstatus 是标准字段，meta.has_field() 可能返回 False，必须固定带出，否则数量汇总会把
    # 草稿/已取消单据当成已提交（RELEASE-95 回归中发现）。
    extra = ["docstatus"] + [f for f in ("status", "posting_date", "supplier", "grand_total", "purpose")
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


def _submitted_rows(rows, docs):
    """只统计已提交（docstatus=1）的单据行；草稿/已取消单据仅留作追溯展示。"""
    ok = {d["name"] for d in docs if int(d.get("docstatus") or 0) == 1}
    return [r for r in rows if r.get("parent") in ok]


SHORTAGE_BASIS = (
    "剩余需求 = BOM 需求 × (1 - 已完工比例)；"
    "当前可用 = 该物料在 BOM 发料仓的 Bin 实际库存（已含采购入库，不再重复扣 received_qty）；"
    "已领未耗 = 本单领料到在制仓但尚未在 Manufacture 消耗的数量；"
    "缺料 = max(0, 剩余需求 - 当前可用 - 已领未耗)。"
    "未做库存预留，仅按源仓可用量估算；同仓多单共用同一批库存时以交期先后顺序分配，"
    "因此属于受控的保守估算，不等于最终采购建议。"
)


def compute_shortage(required_qty, produced_factor=0.0, available_now=0.0, issued_net=0.0):
    """RELEASE-95 P0-1：缺料纯函数（无 DB 依赖，便于单元测试）。

    修正点：`available_now` 来自 Bin 实时库存，采购入库已体现在其中，
    旧实现再减一次 `received_qty` 会重复计入已收货、低报缺料。
    已完成生产的部分不再计入需求，避免完工订单继续显示大量缺料。
    """
    factor = min(1.0, max(0.0, float(produced_factor or 0.0)))
    remaining = max(0.0, float(required_qty or 0.0) * (1.0 - factor))
    shortage = remaining - max(0.0, float(available_now or 0.0)) - max(0.0, float(issued_net or 0.0))
    return round(max(0.0, shortage), 4)


def _shortage_formula():
    return "max(0, required*(1-produced_ratio) - available_now(bin) - issued_net)"


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
             or (_roles() & SENIOR_ROLES) or _is_order_worker(sales_order),
             _("无权查看该销售订单"))

    finance = bool(_roles() & FINANCE_ROLES)
    so_items = frappe.get_all(
        "Sales Order Item",
        filters={"parent": sales_order, "parenttype": "Sales Order"},
        fields=["item_code", "item_name", "qty", "rate", "amount", "warehouse", "bom_no",
                "delivered_qty", "billed_amt", "delivery_date"], limit=50,
    )
    from cn_mfg_poc.bom_link import bom_or_default, default_bom

    for r in so_items:
        # UX-96B：把「本单已确认 BOM」和「产品默认建议 BOM」分成两个字段，禁止互相冒充
        r["default_bom"] = default_bom(r["item_code"])
        r["bom_confirmed"] = bool(r.get("bom_no"))
        r["bom_state"] = ("explicit" if r.get("bom_no")
                          else ("default_suggested" if r["default_bom"] else "none"))
        if not finance:
            r["rate"] = r["amount"] = r["billed_amt"] = None

    # ---- 物料覆盖（订单选用 BOM 为准）
    components = []
    bom_names = []
    suggested_names = []
    for row in so_items:
        bom_no, source = bom_or_default(row["item_code"], row.get("bom_no"))
        if source == "default" and bom_no:
            suggested_names.append(bom_no)
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
                "bom_source": source,
                # 用于按“已完工比例”折算剩余需求，不对外暴露内部键
                "_order_item": row["item_code"], "_order_qty": float(row["qty"] or 0) or 1.0,
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

    # 已完成生产的数量（按产品行汇总 Work Order 的 produced_qty），用于折算剩余需求
    produced_by_item = {}
    for w in wo_rows:
        key = w.get("production_item")
        produced_by_item[key] = produced_by_item.get(key, 0.0) + float(w.get("produced_qty") or 0)

    for c in components:
        code = c["item_code"]
        order_item = c.pop("_order_item", None)
        order_qty = c.pop("_order_qty", 1.0)
        produced = min(order_qty, produced_by_item.get(order_item, 0.0))
        c["produced_factor"] = round(produced / order_qty, 4) if order_qty else 0.0
        c["remaining_qty"] = round(float(c["required_qty"]) * (1.0 - c["produced_factor"]), 4)
        c["available_now"] = float(frappe.db.get_value(
            "Bin", {"item_code": code, "warehouse": c["warehouse"]}, "actual_qty") or 0)
        c["stock_all_warehouses"] = float(frappe.db.sql(
            "select coalesce(sum(actual_qty), 0) from tabBin where item_code=%s", code)[0][0] or 0)
        c["purchased_qty"] = _sum_qty(_submitted_rows(po_rows, po_docs), code)
        # 仅作展示/追溯；已包含在 available_now 里，不再参与缺料扣减（P0-1）
        c["received_qty"] = _sum_qty(_submitted_rows(pr_rows, pr_docs), code)
        c["issued_qty"] = _sum_qty([r for r in issued_rows if r.get("item_code") == code])
        c["consumed_qty"] = _sum_qty([r for r in consumed_rows
                                      if r.get("item_code") == code and r.get("s_warehouse")])
        c["issued_net"] = max(0.0, c["issued_qty"] - c["consumed_qty"])
        c["shortage"] = compute_shortage(c["remaining_qty"], 0, c["available_now"], c["issued_net"])
        c["requested_qty"] = _sum_qty(_submitted_rows(mr_rows, mr_docs), code)

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

    delivered_qty = _sum_qty(_submitted_rows(dn_rows, dn_docs))
    produced_qty = sum(float(w.get("produced_qty") or 0) for w in wo_rows)

    # UX-96B：显式选用 vs 默认建议，两个集合绝不合并成一个模糊的“BOM”
    explicit_boms = sorted({r["bom_no"] for r in so_items if r.get("bom_no")})
    suggested_boms = sorted({r["default_bom"] for r in so_items
                             if not r.get("bom_no") and r.get("default_bom")})
    unconfirmed_items = [r["item_code"] for r in so_items if not r.get("bom_no")]
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
        "boms": [{"name": n, "url": _desk_url("BOM", n),
                  "source": "explicit" if n in explicit_boms else "suggested"}
                 for n in sorted(set(bom_names))],
        "bom_summary": {
            "explicit_boms": [{"name": n, "url": _desk_url("BOM", n)} for n in explicit_boms],
            "suggested_boms": [{"name": n, "url": _desk_url("BOM", n)} for n in suggested_boms],
            "unconfirmed_items": unconfirmed_items,
            "all_confirmed": not unconfirmed_items,
            "note": ("“本单 BOM”= 订单行显式选用的 bom_no，是采购/生产的确认依据；"
                     "“默认建议 BOM”= 该产品当前默认 BOM，仅用于预览物料需求，"
                     "不代表本单已确认。"),
        },
        "materials": {
            "components": components,
            "shortage_formula": _shortage_formula(),
            "shortage_basis": SHORTAGE_BASIS,
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
    """BUILD-93 轻量契约：未完成生产订单的 BOM 缺料清单（真实单据来源）。

    仅生产/仓库/采购/系统角色可用；普通生产人员只看到自己有任务的订单，
    避免用一条命令扫出全公司订单的物料缺口。
    """
    _require(_roles() & SHORTAGE_ROLES, _("当前角色无权查看缺料（生产/仓库/采购职能）"))
    orders = frappe.get_all(
        "Sales Order", filters={"business_type": "生产", "docstatus": 1,
                                "status": ("not in", ["Completed", "Cancelled", "Closed"])},
        fields=["name", "delivery_date", "customer_name"], order_by="delivery_date", limit=int(limit),
    )
    senior = bool(_roles() & SENIOR_ROLES)
    result = []
    # 同仓多单共用同一批库存：按交期先后顺序分配，避免每张单都把同一批库存算成自己的可用量
    pool = {}
    for o in orders:
        if not senior and not _is_order_worker(o["name"]):
            continue
        try:
            summary = order_summary(o["name"])
        except Exception:
            continue
        shortage = []
        for c in summary["materials"]["components"]:
            key = (c["item_code"], c["warehouse"])
            if key not in pool:
                pool[key] = float(c["available_now"] or 0)
            need = max(0.0, float(c["remaining_qty"]) - float(c["issued_net"]))
            take = min(pool[key], need)
            pool[key] = round(pool[key] - take, 4)
            c["available_for_order"] = round(take, 4)   # 本单按交期顺序分到的库存
            c["allocated_from_stock"] = round(take, 4)
            c["shortage"] = compute_shortage(need, 0, take, 0)
            if c["shortage"] > 0:
                shortage.append(c)
        if shortage:
            result.append({"sales_order": o["name"], "url": summary["order"]["url"],
                           "delivery_date": str(o["delivery_date"]),
                           "customer": o["customer_name"], "shortages": shortage})
    return {"user": frappe.session.user, "count": len(result), "orders": result,
            "shortage_formula": _shortage_formula(), "shortage_basis": SHORTAGE_BASIS,
            "allocation": "按销售订单交期先后顺序分配同仓库存（无预留关系）"}
