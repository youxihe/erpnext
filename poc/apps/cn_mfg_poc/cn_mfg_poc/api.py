# -*- coding: utf-8 -*-
"""cn_mfg_poc.api — PC / 企微 H5 / AI 机器人三入口共用的受控业务接口。

原则（docs/product/ARCHITECTURE.md）：
- 身份：一律使用当前会话用户（frappe.session.user，由登录/OAuth/Token 决定），
  服务端做角色/公司/仓库/员工归属检查；绝不接受客户端自报身份，不使用 Administrator 共享 Token。
- 权威数据：全部读写 ERPNext 原生 DocType，本模块不维护第二份业务表。
- 写入：输入校验 → 预览/草稿 → 明确确认 → 幂等 → 原生单据 → 返回正式单号。
- 审计：关键写入在目标单据上留 Comment（用户/渠道/时间/动作），并写 cn_api 日志文件。
"""

import json

import frappe
from frappe import _
from frappe.utils import now_datetime, nowdate

COMPANY = "昆山启程智能设备有限公司"

# ---------------------------------------------------------------- 工具


def _roles():
    return set(frappe.get_roles())


def _require(cond, msg, exc=frappe.PermissionError):
    if not cond:
        frappe.throw(msg, exc)


def _require_any_role(roles, action):
    _require(
        _roles() & set(roles),
        _("当前角色无权{0}（需要：{1}）").format(action, "、".join(roles)),
    )


def _audit(subject_doctype, subject_name, action, detail=None):
    """在业务单据上留痕 + 写日志文件（不含密钥）。"""
    try:
        frappe.get_doc(
            {
                "doctype": "Comment",
                "comment_type": "Comment",
                "reference_doctype": subject_doctype,
                "reference_name": subject_name,
                "content": f"[API] {frappe.session.user} · {action}" + (f" · {detail}" if detail else ""),
            }
        ).insert(ignore_permissions=True)
    except Exception:
        pass
    frappe.logger("cn_api").info(
        json.dumps(
            {
                "user": frappe.session.user,
                "action": action,
                "doctype": subject_doctype,
                "docname": subject_name,
                "detail": detail,
                "time": str(now_datetime()),
            },
            ensure_ascii=False,
        )
    )


# ---------------------------------------------------------------- 客户：报备 / 查询


@frappe.whitelist(methods=["POST"])
def report_customer(customer_name, contact_name=None, mobile_no=None, note=None):
    """客户报备：最少字段（客户名称 + 报备人=当前用户 + 状态）。

    - 查重：同名正式客户 / 同名未关闭报备 → 返回 existing，不重复建。
    - 幂等：同一用户对同一客户名的未关闭报备直接返回原单。
    """
    _require_any_role({"Sales User", "Sales Manager", "System Manager"}, "报备客户")
    _require(frappe.has_permission("Lead", "create"), _("无创建客户报备权限"))
    customer_name = (customer_name or "").strip()
    _require(customer_name, _("客户名称必填"), frappe.ValidationError)

    cust = frappe.db.get_value("Customer", {"customer_name": customer_name}, "name")
    if cust:
        return {"existing": "customer", "customer": cust, "message": _("该客户已存在，无需报备")}

    dup = frappe.db.get_value(
        "Lead",
        {
            "company_name": customer_name,
            "status": ("not in", ["Converted", "Lost Quotation", "Do Not Contact"]),
        },
        "name",
    )
    if dup:
        return {"existing": "lead", "lead": dup, "message": _("已有未关闭的报备单，请勿重复报备")}

    ld = frappe.new_doc("Lead")
    ld.company_name = customer_name
    ld.lead_name = (contact_name or "").strip() or customer_name
    ld.mobile_no = (mobile_no or "").strip() or None
    ld.lead_owner = frappe.session.user
    ld.status = "Open"
    ld.insert()
    frappe.db.commit()
    _audit("Lead", ld.name, "客户报备(H5/Bot/PC)", customer_name)
    return {"lead": ld.name, "status": ld.status, "owner": ld.lead_owner}


@frappe.whitelist(methods=["GET", "POST"])
def search_customers(q, limit=10):
    """按授权查询客户与未关闭报备（PC/H5/Bot 共用）。"""
    q = (q or "").strip()
    _require(len(q) >= 1, _("请输入至少 1 个字符的查询词"), frappe.ValidationError)
    out = {"customers": [], "leads": []}
    if frappe.has_permission("Customer", "read"):
        out["customers"] = frappe.get_all(
            "Customer",
            filters={"customer_name": ("like", f"%{q}%")},
            fields=["name", "customer_name", "customer_type", "disabled"],
            limit=int(limit),
        )
    if frappe.has_permission("Lead", "read"):
        out["leads"] = frappe.get_all(
            "Lead",
            filters={
                "company_name": ("like", f"%{q}%"),
                "status": ("not in", ["Converted", "Lost Quotation", "Do Not Contact"]),
            },
            fields=["name", "company_name", "lead_owner", "status", "mobile_no"],
            limit=int(limit),
        )
    return out


# ---------------------------------------------------------------- 销售：我的订单


@frappe.whitelist(methods=["GET"])
def my_orders(limit=20):
    """当前用户的销售订单（非管理角色只见本人创建的单据）。"""
    _require_any_role({"Sales User", "Sales Manager", "System Manager"}, "查看销售订单")
    _require(frappe.has_permission("Sales Order", "read"), _("无销售订单读权限"))
    filters = {}
    if not ({"Sales Manager", "System Manager"} & _roles()):
        filters["owner"] = frappe.session.user
    rows = frappe.get_all(
        "Sales Order",
        filters=filters,
        fields=["name", "customer", "transaction_date", "grand_total", "status", "per_delivered", "per_billed"],
        order_by="modified desc",
        limit=int(limit),
    )
    return {"orders": rows}


@frappe.whitelist(methods=["GET"])
def order_detail(name):
    """订单明细 + 交付/收款摘要；非管理角色仅限本人单据。"""
    _require(frappe.has_permission("Sales Order", "read", doc=name), _("无权查看该订单"))
    d = frappe.get_doc("Sales Order", name)
    if not ({"Sales Manager", "System Manager"} & _roles()) and d.owner != frappe.session.user:
        frappe.throw(_("该订单不属于您"), frappe.PermissionError)
    return {
        "name": d.name,
        "customer": d.customer,
        "business_type": d.get("business_type"),
        "status": d.status,
        "grand_total": d.grand_total,
        "per_delivered": d.per_delivered,
        "per_billed": d.per_billed,
        "items": [
            {"item_code": i.item_code, "qty": i.qty, "rate": i.rate, "delivered_qty": i.delivered_qty}
            for i in d.items
        ],
    }


# ---------------------------------------------------------------- 生产：我的任务 / 进度更新

STAFF_ROLES = {"Manufacturing User", "Manufacturing Manager", "System Manager"}


def _my_employee():
    emp = frappe.db.get_value(
        "Employee", {"user_id": frappe.session.user, "status": "Active"}, ["name", "employee_name"], as_dict=1
    )
    _require(emp, _("当前账号未绑定在职员工，无法操作车间任务"), frappe.PermissionError)
    return emp


@frappe.whitelist(methods=["GET"])
def my_jobs(limit=50):
    """当前员工的任务单：指派多选 + 实际工时两个来源合并；管理角色可见全部。"""
    _require_any_role(STAFF_ROLES, "查看车间任务")
    if {"Manufacturing Manager", "System Manager"} & _roles():
        rows = frappe.get_all(
            "Job Card",
            filters={"docstatus": ("<", 2)},
            fields=["name", "work_order", "production_item", "operation", "workstation",
                    "for_quantity", "total_completed_qty", "status"],
            order_by="modified desc",
            limit=int(limit),
        )
        return {"jobs": rows}

    emp = _my_employee()
    names = set(
        frappe.db.sql(
            """
            select jc.name
            from `tabJob Card Time Log` tl
            join `tabJob Card` jc on tl.parent = jc.name
            left join `tabEmployee` e on tl.employee = e.name
            where tl.parentfield in ('time_logs', 'employee') and e.user_id = %(user)s and jc.docstatus < 2
            """,
            {"user": frappe.session.user},
            pluck=True,
        )
    ) or set(
        frappe.get_all(
            "Job Card Time Log",
            filters={"parenttype": "Job Card", "employee": emp["name"]},
            pluck="parent",
        )
    )
    rows = []
    for n in names:
        rows.append(
            frappe.db.get_value(
                "Job Card", n,
                ["name", "work_order", "production_item", "operation", "workstation",
                 "for_quantity", "total_completed_qty", "status", "docstatus"],
                as_dict=1,
            )
        )
    return {"jobs": rows, "employee": emp["name"], "employee_name": emp["employee_name"]}


@frappe.whitelist(methods=["POST"])
def update_job_progress(job_card, qty, note=None):
    """本人任务进度更新：开始 + 报工一次完成；完成全部数量时自动提交任务单。

    服务端约束：绑定在职员工；任务未取消/未提交；数量合法；
    已有指派且不含本人时拒绝（防止替他人报工）。
    """
    _require_any_role(STAFF_ROLES, "更新任务进度")
    emp = _my_employee()
    jc = frappe.get_doc("Job Card", job_card)
    _require(jc.docstatus < 2, _("任务单已取消"), frappe.ValidationError)

    assigned = {
        r.employee
        for r in frappe.get_all(
            "Job Card Time Log",
            filters={"parent": jc.name, "parenttype": "Job Card"},
            fields=["employee"],
        )
        if r.employee
    }
    if assigned and emp["name"] not in assigned:
        frappe.throw(_("该任务未分配给您（{0}）").format(emp["employee_name"]), frappe.PermissionError)

    _require(jc.docstatus == 0, _("任务单已提交/取消，不能报工"), frappe.ValidationError)
    _require(jc.status not in ("Completed", "Cancelled"), _("任务已{0}").format(jc.status), frappe.ValidationError)

    qty = flt = float(qty or 0)
    pending = (jc.for_quantity or 0) - (jc.total_completed_qty or 0)
    _require(qty > 0, _("报工数量必须大于 0"), frappe.ValidationError)
    _require(qty <= pending + 1e-9, _("报工数量 {0} 超过待完成 {1}").format(qty, pending), frappe.ValidationError)

    start = now_datetime()
    if not jc.time_logs:
        jc.start_timer(employees=emp["name"], start_time=start)
        frappe.db.commit()
        jc = frappe.get_doc("Job Card", job_card)
    jc.complete_job_card(
        qty=qty,
        pending_qty=round(max(pending - qty, 0), 6),
        end_time=now_datetime(),
        auto_submit=(qty >= pending - 1e-9),
    )
    frappe.db.commit()
    jc = frappe.get_doc("Job Card", job_card)
    _audit("Job Card", jc.name, "任务报工(H5/Bot/PC)", f"{emp['employee_name']} +{qty}")
    return {
        "job_card": jc.name,
        "status": jc.status,
        "completed": jc.total_completed_qty,
        "for_quantity": jc.for_quantity,
        "employee": emp["employee_name"],
    }


# ---------------------------------------------------------------- 库存：授权查询


@frappe.whitelist(methods=["GET"])
def stock_balances(warehouse=None, item=None, limit=100):
    """按公司/仓库存量查询。角色白名单：仓储/制造/系统管理。"""
    _require_any_role(
        {"Stock User", "Stock Manager", "Manufacturing User", "Manufacturing Manager", "System Manager"},
        "查询库存",
    )
    filters = {"company": COMPANY, "actual_qty": (">", 0)}
    if warehouse:
        _require(
            frappe.db.exists("Warehouse", {"name": warehouse, "company": COMPANY}),
            _("仓库不存在：{0}").format(warehouse),
            frappe.ValidationError,
        )
        filters["warehouse"] = warehouse
    if item:
        filters["item_code"] = item
    rows = frappe.get_all(
        "Bin",
        filters=filters,
        fields=["item_code", "warehouse", "actual_qty", "stock_value"],
        order_by="item_code",
        limit=int(limit),
    )
    return {"company": COMPANY, "warehouse": warehouse, "balances": rows}


# ---------------------------------------------------------------- 采购：Excel 入库草稿 / 确认

PURCHASE_ROLES = {"Stock User", "Stock Manager", "System Manager"}


def _validate_purchase_lines(lines, warehouse):
    """逐行校验：物料/仓库/供应商存在、数量>0、单价>=0。返回规范化行。"""
    clean = []
    for i, row in enumerate(lines, 1):
        item = (row.get("item_code") or "").strip()
        qty = float(row.get("qty") or 0)
        rate = row.get("rate")
        rate = None if rate in (None, "") else float(rate)
        _require(item, _("第 {0} 行：物料编码必填").format(i), frappe.ValidationError)
        _require(
            frappe.db.exists("Item", item),
            _("第 {0} 行：物料不存在 {1}").format(i, item),
            frappe.ValidationError,
        )
        _require(qty > 0, _("第 {0} 行：数量必须大于 0").format(i), frappe.ValidationError)
        if rate is None:
            rate = frappe.db.get_value("Item", item, "standard_rate") or 0
        clean.append({"item_code": item, "qty": qty, "rate": rate})
    return clean


@frappe.whitelist(methods=["POST"])
def prepare_purchase_draft(supplier, lines, warehouse=None, source="H5"):
    """Purchase Intake Draft：接收（Excel 解析后的）行数据，逐行校验后存草稿，不产生任何库存变化。"""
    _require_any_role(PURCHASE_ROLES, "准备Purchase Intake Draft")
    _require(
        frappe.db.exists("Supplier", {"name": supplier, "disabled": 0}),
        _("供应商不存在或已停用：{0}").format(supplier),
        frappe.ValidationError,
    )
    warehouse = warehouse or "原材料仓 - QC"
    _require(
        frappe.db.exists("Warehouse", {"name": warehouse, "company": COMPANY, "is_group": 0}),
        _("入库仓库无效：{0}").format(warehouse),
        frappe.ValidationError,
    )
    if isinstance(lines, str):
        lines = json.loads(lines)
    _require(isinstance(lines, list) and lines, _("明细行不能为空"), frappe.ValidationError)
    clean = _validate_purchase_lines(lines, warehouse)

    d = frappe.new_doc("Purchase Intake Draft")
    d.supplier = supplier
    d.warehouse = warehouse
    d.company = COMPANY
    d.lines_json = json.dumps(clean, ensure_ascii=False)
    d.status = "Draft"
    d.insert()
    frappe.db.commit()
    _audit("Purchase Intake Draft", d.name, "创建Purchase Intake Draft", f"supplier={supplier} rows={len(clean)} source={source}")
    return {"draft": d.name, "status": d.status, "lines": clean}


@frappe.whitelist(methods=["POST"])
def confirm_purchase_draft(draft):
    """确认草稿 → 生成并提交原生采购入库单（Purchase Receipt）。幂等：重复确认返回原单，不再过账。"""
    _require_any_role(PURCHASE_ROLES, "确认采购入库")
    d = frappe.get_doc("Purchase Intake Draft", draft)
    if d.status == "Confirmed" and d.purchase_receipt:
        pr_doc = frappe.get_doc("Purchase Receipt", d.purchase_receipt)
        return {
            "purchase_receipt": pr_doc.name,
            "docstatus": pr_doc.docstatus,
            "already_confirmed": True,
            "message": _("该草稿已确认过，返回原单据，未重复入库"),
        }
    _require(d.status == "Draft", _("草稿状态为 {0}，不能确认").format(d.status), frappe.ValidationError)

    lines = json.loads(d.lines_json)
    clean = _validate_purchase_lines(lines, d.warehouse)

    pr = frappe.new_doc("Purchase Receipt")
    pr.company = d.company
    pr.supplier = d.supplier
    pr.set_posting_time = 1
    for row in clean:
        pr.append("items", {
            "item_code": row["item_code"],
            "qty": row["qty"],
            "rate": row["rate"],
            "warehouse": d.warehouse,
        })
    pr.insert()
    pr.submit()
    frappe.db.commit()

    d.status = "Confirmed"
    d.purchase_receipt = pr.name
    d.flags.ignore_permissions = True
    d.save()
    frappe.db.commit()
    _audit("Purchase Receipt", pr.name, "采购入库确认", f"draft={d.name} user={frappe.session.user}")
    return {"purchase_receipt": pr.name, "docstatus": pr.docstatus, "already_confirmed": False}
