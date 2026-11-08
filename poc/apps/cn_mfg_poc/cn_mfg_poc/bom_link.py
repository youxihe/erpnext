# -*- coding: utf-8 -*-
"""UX-96B：销售订单 ↔ BOM 的显式选用与双向追溯。

原则：
- 唯一权威是原生 ``Sales Order Item.bom_no``（行级 Link），不新增业务表、不复制 BOM。
- ``BOM.item`` 的默认 BOM 只是**建议**，不等于"本单已确认"，展示时必须分开。
- 已提交订单不允许直接改 bom_no：ERPNext 原生 allow_on_submit=0，这里再用
  validate 对 DB 旧值做二次兜底，避免 API/db_set 绕过表单。
- 反向查询只返回当前用户有权限查看的 Sales Order / Work Order。
"""

import frappe
from frappe import _

READ_ROLES = {
    "Sales User", "Sales Manager", "Purchase User", "Purchase Manager",
    "Stock User", "Stock Manager", "Manufacturing User", "Manufacturing Manager",
    "Accounts User", "Accounts Manager", "System Manager",
}

BOM_READ_ROLES = {
    "Manufacturing User", "Manufacturing Manager", "Stock User", "Stock Manager",
    "System Manager", "Item Manager",
}

# 人工确认标记：ERPNext 原生 get_item_details() 会把 Item.default_bom 自动写进
# Sales Order Item.bom_no，因此「bom_no 有值」不能等同于「本单已确认」。
# 只有人工动作（界面选择 / 改动 bom_no）或已提交订单才算确认。
CONFIRM_FIELD = "custom_bom_confirmed"


def _roles():
    return set(frappe.get_roles())


def _require(cond, msg, exc=frappe.PermissionError):
    if not cond:
        frappe.throw(msg, exc)


def _desk_url(doctype, name=None):
    import re
    from urllib.parse import quote

    slug = re.sub(r"[^a-z0-9]+", "-", (doctype or "").lower()).strip("-")
    return "/desk/" + slug + ("/" + quote(str(name), safe="") if name else "")


def default_bom(item_code):
    """产品默认建议 BOM（未提交/失效则返回 None）。仅作建议，不代表订单已选用。"""
    if not item_code:
        return None
    return frappe.db.get_value(
        "BOM", {"item": item_code, "is_active": 1, "docstatus": 1, "is_default": 1}, "name"
    )


def bom_or_default(item_code, bom_no):
    """返回 (实际用于物料展开的 BOM, 来源 explicit/default/none)。"""
    if bom_no:
        return bom_no, "explicit"
    d = default_bom(item_code)
    return (d, "default") if d else (None, "none")


def bom_confirm_state(item_code, bom_no, so_docstatus=0, confirmed_flag=0):
    """判断一行订单 BOM 的真实状态，返回 (state, confirmed_bom)。

    state:
      explicit          —— 本单已确认，confirmed_bom 为本单 BOM
      default_suggested —— 未确认；仅产品默认 BOM 可作建议（bom_no 可能是系统自动带入的）
      none              —— 该物料没有可用 BOM（服务/非标）

    判定顺序（草稿）：
      1. 人工确认标记 = 1 → 已确认
      2. 产品没有默认 BOM，或 bom_no 与默认不同 → 只能是人工选的 → 已确认
      3. 否则 bom_no 只是 ERPNext 自动带入的默认值 → 仍未确认
    已提交订单：bom_no 有值即视为确认（提交动作即锁定，生产已按它排程）。
    """
    default = default_bom(item_code)
    if not bom_no:
        return ("default_suggested" if default else "none"), None
    if int(so_docstatus or 0) == 1:
        return "explicit", bom_no
    if int(confirmed_flag or 0):
        return "explicit", bom_no
    if not default or bom_no != default:
        return "explicit", bom_no
    return "default_suggested", None


def validate_sales_order_bom(doc, method=None):
    """Sales Order validate：行级 BOM 必须与行物料一致、已提交且有效。

    同时拦截"已提交订单被直接改写 bom_no"，提示走受控变更流程。
    """
    old_values = {}
    if not doc.is_new():
        old_values = {
            r.name: r.bom_no
            for r in frappe.get_all(
                "Sales Order Item", filters={"parent": doc.name, "parenttype": "Sales Order"},
                fields=["name", "bom_no"], limit=200,
            )
        }

    for row in doc.get("items") or []:
        bom_no = (row.get("bom_no") or "").strip()
        if not bom_no:
            continue  # 允许不选：物料覆盖按默认建议展示，并明确标注未确认

        bom = frappe.db.get_value(
            "BOM", bom_no,
            ["name", "item", "docstatus", "is_active", "quantity"], as_dict=True,
        )
        if not bom:
            frappe.throw(_("第 {0} 行所选 BOM 不存在：{1}").format(row.idx, bom_no),
                         frappe.ValidationError)
        if int(bom["docstatus"]) != 1 or not int(bom["is_active"] or 0):
            frappe.throw(_("第 {0} 行所选 BOM {1} 未提交或已停用，不能选用").format(row.idx, bom_no),
                         frappe.ValidationError)
        if bom["item"] != row.get("item_code"):
            frappe.throw(
                _("第 {0} 行物料 {1} 与所选 BOM {2} 的产品 {3} 不一致").format(
                    row.idx, row.get("item_code"), bom_no, bom["item"]
                ),
                frappe.ValidationError,
            )
        if row.name in old_values and old_values.get(row.name) not in (None, "", bom_no) \
                and doc.docstatus == 1:
            frappe.throw(
                _("Sales Order {0} 已提交，不能直接把第 {1} 行 BOM 从 {2} 改为 {3}；"
                  "请走受控变更（取消/修订订单，或在新版本 BOM 上调整后续工单）").format(
                    doc.name, row.idx, old_values.get(row.name), bom_no),
                frappe.ValidationError,
            )

    if doc.docstatus == 0:
        _mark_confirmed_flags(doc, old_values)


def _mark_confirmed_flags(doc, old_values):
    """草稿阶段落「人工确认」标记，供展示与反查区分默认带入值。

    已提交订单不写（提交即视为确认，且字段不允许提交后变更）。
    """
    for row in doc.get("items") or []:
        bom_no = (row.get("bom_no") or "").strip()
        if not bom_no:
            if row.get(CONFIRM_FIELD):
                row.set(CONFIRM_FIELD, 0)
            continue
        default = default_bom(row.get("item_code"))
        old = old_values.get(row.name) if row.name in old_values else None
        changed_by_human = row.name in old_values and (old or "") != bom_no
        explicit = bool(row.get(CONFIRM_FIELD)) or changed_by_human \
            or (not default) or (bom_no != default)
        row.set(CONFIRM_FIELD, 1 if explicit else 0)


@frappe.whitelist(methods=["GET"])
def bom_options(item_code):
    """草稿订单行可选的 BOM：同产品、已提交、未停用；标出默认建议。"""
    _require(_roles() & READ_ROLES, _("当前角色无权查看 BOM 选项"))
    _require(item_code, _("缺少物料编码"), frappe.ValidationError)
    rows = frappe.get_all(
        "BOM",
        filters={"item": item_code, "docstatus": 1, "is_active": 1},
        fields=["name", "quantity", "is_default", "currency", "company", "creation"],
        order_by="is_default desc, creation desc", limit=50,
    )
    default = next((r["name"] for r in rows if int(r["is_default"] or 0)), None)
    return {
        "item_code": item_code,
        "default_bom": default,
        "options": [
            {
                "bom": r["name"],
                "quantity": float(r["quantity"] or 0),
                "is_default": bool(int(r["is_default"] or 0)),
                "currency": r.get("currency"),
                "company": r.get("company"),
                "label": "%s（基准 %s%s）" % (
                    r["name"], float(r["quantity"] or 0),
                    " · 默认" if int(r["is_default"] or 0) else "",
                ),
            }
            for r in rows
        ],
        "note": _("默认 BOM 只是建议；只有写进订单行的 bom_no 才代表本单已确认"),
    }


@frappe.whitelist(methods=["GET"])
def bom_references(bom):
    """反向追溯：显式引用本 BOM 的 Sales Order Item 与 Work Order（按查看者权限过滤）。"""
    _require(_roles() & READ_ROLES, _("当前角色无权查看 BOM 引用"))
    meta = frappe.db.get_value("BOM", bom, ["name", "item", "quantity", "docstatus", "is_active"],
                               as_dict=True)
    _require(meta, _("BOM 不存在：{0}").format(bom), frappe.ValidationError)

    so_rows = frappe.get_all(
        "Sales Order Item",
        filters={"bom_no": bom, "parenttype": "Sales Order"},
        fields=["parent", "item_code", "qty", "idx", "delivery_date", CONFIRM_FIELD],
        order_by="parent desc, idx", limit=200,
    )
    orders, seen = [], set()
    for r in so_rows:
        if r["parent"] in seen:
            continue
        if not frappe.has_permission("Sales Order", "read", doc=r["parent"]):
            continue
        so = frappe.db.get_value(
            "Sales Order", r["parent"],
            ["name", "customer", "customer_name", "status", "docstatus", "transaction_date",
             "delivery_date"], as_dict=True,
        )
        if not so:
            continue
        # 只算真正「显式引用」：默认 BOM 被系统自动带入的行不算引用
        state, _confirmed = bom_confirm_state(
            r["item_code"], bom, so["docstatus"], r.get(CONFIRM_FIELD))
        if state != "explicit":
            continue
        seen.add(r["parent"])
        orders.append({
            "sales_order": so["name"],
            "url": _desk_url("Sales Order", so["name"]),
            "customer": so["customer_name"] or so["customer"],
            "status": so["status"],
            "docstatus": so["docstatus"],
            "transaction_date": str(so["transaction_date"]) if so["transaction_date"] else None,
            "delivery_date": str(so["delivery_date"]) if so["delivery_date"] else None,
            "item_code": r["item_code"],
            "qty": float(r["qty"] or 0),
            "line_idx": r["idx"],
        })

    wo_rows = frappe.get_all(
        "Work Order",
        filters={"bom_no": bom},
        fields=["name", "production_item", "qty", "produced_qty", "status", "docstatus",
                "sales_order", "planned_start_date"],
        order_by="name desc", limit=200,
    )
    work_orders = []
    for r in wo_rows:
        if not frappe.has_permission("Work Order", "read", doc=r["name"]):
            continue
        work_orders.append({
            "work_order": r["name"],
            "url": _desk_url("Work Order", r["name"]),
            "production_item": r["production_item"],
            "qty": float(r["qty"] or 0),
            "produced_qty": float(r["produced_qty"] or 0),
            "status": r["status"],
            "docstatus": r["docstatus"],
            "sales_order": r.get("sales_order"),
            "planned_start_date": str(r["planned_start_date"]) if r.get("planned_start_date") else None,
        })

    return {
        "bom": bom,
        "item_code": meta["item"],
        "quantity": float(meta["quantity"] or 0),
        "url": _desk_url("BOM", bom),
        "sales_orders": orders,
        "work_orders": work_orders,
        "counts": {"sales_orders": len(orders), "work_orders": len(work_orders)},
        "explicit_only_note": _("只有订单行真正确认使用本 BOM 才计入；新建订单行时系统"
                                "自动带入的产品默认 BOM 不算引用，草稿里尚未确认的默认值也不算。"),
        "scope_note": _("仅显示当前账号有权限查看的订单与工单，已按数据权限过滤。"),
    }
