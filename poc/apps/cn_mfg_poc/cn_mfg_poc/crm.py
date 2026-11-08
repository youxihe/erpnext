# -*- coding: utf-8 -*-
"""CRM-100：客户报备（原生 Lead）→ 正式客户（原生 Customer）→ 销售订单（原生 Sales Order）。

设计原则（docs/product/tasks/CRM-100.md）：
- 不建第二份客户表：Lead / Customer / Contact / Address / Sales Order 全部用 ERPNext 原生 DocType。
- 不复制框架逻辑：Lead → Customer 走原生 `erpnext.crm.doctype.lead.lead.make_customer` 的字段映射；
  Customer 保存时由原生 `Customer.update_lead_status` 把 Lead 标记为 Converted。
- 归属可追溯：Customer.custom_first_reporter / custom_first_reported_on 由 `set_first_reporter`
  （hooks 里的 Customer.before_insert）在**任何入口**建客户时写入，不从 owner / 最后修改人推断。
- 不越权：所有写操作使用当前会话用户的真实权限，不出现 ignore_permissions；
  报备人只取 `Lead.lead_owner` 或当前会话用户，永不接受客户端传入的“报备人”。
- 幂等：转客户/建客户重复调用返回原单据，不重复建 Customer。
"""

import frappe
from frappe import _
from frappe.utils import now_datetime

from urllib.parse import quote

from cn_mfg_poc.api import _audit, _require, _require_any_role

SALES_ROLES = {"Sales User", "Sales Manager", "System Manager"}

# Lead 中视为“还在流程里”的状态（与 api.report_customer 的查重口径一致）
OPEN_LEAD_STATUS = ("not in", ["Converted", "Lost Quotation", "Do Not Contact"])
CLOSED_LEAD_STATUS = ("in", ["Converted", "Lost Quotation", "Do Not Contact"])

BUSINESS_TYPES = ["生产", "耗材", "零部件", "服务"]

# 客户可能没有默认客户组/区域时的兜底（仅当文档本身没有值时使用）
FALLBACK_CUSTOMER_GROUP = "Commercial"
FALLBACK_TERRITORY = "China"


# ---------------------------------------------------------------- 身份与展示


def _fullname(user):
    if not user:
        return ""
    return frappe.db.get_value("User", user, "full_name") or user


def _valid_user(user):
    """只接受存在且启用的用户作为报备人/负责人，避免历史脏数据写入。"""
    if not user:
        return None
    row = frappe.db.get_value("User", user, ["name", "enabled"], as_dict=1)
    if not row or not row.enabled:
        return None
    return row.name


def _can_create_customer():
    return bool(frappe.has_permission("Customer", "create"))


def _can_create_order():
    return bool(frappe.has_permission("Sales Order", "create"))


def _customer_by_name(name):
    """同名正式客户（客户名唯一，ERPNext 以 customer_name 命名）。"""
    if not name:
        return None
    return frappe.db.get_value("Customer", {"customer_name": name.strip()}, "name")


def _lead_customer(lead_doc):
    """已转化的正式客户：优先 Lead.customer，其次 Customer.lead_name 反查。"""
    if lead_doc.get("customer") and frappe.db.exists("Customer", lead_doc.customer):
        return lead_doc.customer
    return frappe.db.get_value("Customer", {"lead_name": lead_doc.name}, "name")


# ---------------------------------------------------------------- 首次报备人（doc event）


def set_first_reporter(doc, method=None):
    """Customer.before_insert：写入首次报备人/首次报备时间。

    - 来自 Lead 的转换：报备人 = Lead.lead_owner（存在且启用时），时间 = Lead.creation（首次报备时间）。
    - 直接创建客户：报备人 = 当前会话用户，时间 = 当前时间。
    - 已有值不覆盖（历史回填、管理员手工修正都保留）。
    - 绝不使用 owner / modified_by 充当业务报备人。
    """
    if doc.get("custom_first_reporter") and doc.get("custom_first_reported_on"):
        return

    lead = None
    if doc.get("lead_name"):
        lead = frappe.db.get_value(
            "Lead", doc.lead_name, ["name", "lead_owner", "creation"], as_dict=1
        )

    if not doc.get("custom_first_reporter"):
        reporter = _valid_user(lead.lead_owner) if lead else None
        doc.custom_first_reporter = reporter or _valid_user(frappe.session.user)

    if not doc.get("custom_first_reported_on"):
        doc.custom_first_reported_on = lead.creation if lead else now_datetime()


# ---------------------------------------------------------------- 报备列表 / 详情


@frappe.whitelist(methods=["GET"])
def lead_list(q=None, status=None, limit=100):
    """客户报备列表：名称、首次报备人、报备时间、状态、关联正式客户。"""
    _require(frappe.has_permission("Lead", "read"), _("当前角色无权查看客户报备"))
    filters = {}
    if q:
        filters["company_name"] = ("like", "%" + q.strip() + "%")
    if status == "open":
        filters["status"] = OPEN_LEAD_STATUS
    elif status == "converted":
        filters["status"] = ("in", ["Converted"])
    elif status:
        filters["status"] = status

    rows = frappe.get_list(
        "Lead",
        filters=filters,
        fields=["name", "company_name", "lead_name", "status", "lead_owner", "owner",
                "creation", "mobile_no", "customer"],
        order_by="creation desc",
        limit=int(limit),
    )
    can_convert = _can_create_customer()
    for r in rows:
        r["reporter_name"] = _fullname(r["lead_owner"])
        r["customer"] = _lead_customer(frappe._dict(r))
        r["duplicate_customer"] = _customer_by_name(r["company_name"])
        r["can_convert"] = bool(
            can_convert
            and r["status"] != "Converted"
            and not r["customer"]
            and not r["duplicate_customer"]
        )

    return {
        "leads": rows,
        "count": len(rows),
        "can_create_customer": can_convert,
        "can_create_lead": bool(frappe.has_permission("Lead", "create")),
        "open_count": frappe.db.count("Lead", {"status": OPEN_LEAD_STATUS}),
        "converted_count": frappe.db.count("Lead", {"status": "Converted"}),
    }


@frappe.whitelist(methods=["GET"])
def lead_detail(name):
    """客户报备详情：报备人、报备时间、状态、关联客户、可否转换。"""
    _require(frappe.db.exists("Lead", name), _("报备单不存在：{0}").format(name), frappe.ValidationError)
    _require(frappe.has_permission("Lead", "read", doc=name), _("当前角色无权查看该报备"))

    d = frappe.get_doc("Lead", name)
    customer = _lead_customer(d)
    dup = _customer_by_name(d.company_name or d.lead_name)
    return {
        "name": d.name,
        "company_name": d.company_name,
        "contact_name": d.lead_name,
        "mobile_no": d.mobile_no,
        "email_id": d.email_id,
        "status": d.status,
        "lead_owner": d.lead_owner,
        "reporter_name": _fullname(d.lead_owner),
        "creation": d.creation,
        "owner": d.owner,
        "customer": customer,
        "customer_name": frappe.db.get_value("Customer", customer, "customer_name") if customer else None,
        "duplicate_customer": dup,
        "duplicate_customer_manager": _fullname(
            frappe.db.get_value("Customer", dup, "account_manager")) if dup else None,
        "can_convert": bool(
            _can_create_customer()
            and d.status != "Converted"
            and not customer
            and not dup
        ),
        "desk_url": "/desk/lead/" + quote(d.name),
    }


# ---------------------------------------------------------------- 转换 / 直接建客户


@frappe.whitelist(methods=["POST"])
def convert_lead(lead):
    """把客户报备转为正式客户（幂等）。

    - 已转化：返回原客户，`replayed=True`，不重复建。
    - 已有同名正式客户：返回该客户，`created=False`，**不合并、不抢占报备人/负责人**。
    - 新建：复用原生 `make_customer` 字段映射，报备人/时间取 Lead 首次报备信息，
      客户负责人默认沿用报备人；保存后原生逻辑把 Lead 置为 Converted。
    """
    _require_any_role(SALES_ROLES, "把客户报备转为正式客户")
    _require(frappe.db.exists("Lead", lead), _("报备单不存在：{0}").format(lead), frappe.ValidationError)
    _require(frappe.has_permission("Lead", "read", doc=lead), _("当前角色无权查看该报备"))
    _require(frappe.has_permission("Lead", "write", doc=lead), _("当前角色无权更新该报备"))
    _require(frappe.has_permission("Customer", "create"), _("当前角色无权创建正式客户"))

    ld = frappe.get_doc("Lead", lead)

    existing = _lead_customer(ld)
    if existing:
        if not ld.get("customer"):
            frappe.db.set_value("Lead", lead, "customer", existing, update_modified=False)
        return {
            "customer": existing,
            "customer_name": frappe.db.get_value("Customer", existing, "customer_name"),
            "replayed": True,
            "created": False,
            "message": _("该报备已转为正式客户 {0}").format(existing),
        }

    dup = _customer_by_name(ld.company_name or ld.lead_name)
    if dup:
        return {
            "customer": dup,
            "customer_name": frappe.db.get_value("Customer", dup, "customer_name"),
            "replayed": False,
            "created": False,
            "existing_customer": dup,
            "message": _("已存在同名正式客户 {0}，未重复创建；请直接使用该客户").format(dup),
        }

    from erpnext.crm.doctype.lead.lead import make_customer

    doc = make_customer(ld.name)
    doc.lead_name = ld.name
    if not doc.get("customer_name"):
        doc.customer_name = ld.company_name or ld.lead_name
    if not doc.get("customer_group"):
        doc.customer_group = frappe.db.get_default("Customer Group") or FALLBACK_CUSTOMER_GROUP
    if not doc.get("territory"):
        doc.territory = FALLBACK_TERRITORY
    # 首次报备信息以 Lead 为准；客户负责人默认沿用报备人，之后可由管理人员调整
    reporter = _valid_user(ld.lead_owner) or _valid_user(frappe.session.user)
    doc.custom_first_reporter = reporter
    doc.custom_first_reported_on = ld.creation
    if not doc.get("account_manager") and reporter:
        doc.account_manager = reporter

    doc.insert()  # 真实权限，不 ignore_permissions

    frappe.db.set_value("Lead", ld.name, "customer", doc.name, update_modified=False)
    frappe.db.commit()
    _audit("Customer", doc.name, "客户报备转正式客户",
           "lead=%s reporter=%s" % (ld.name, reporter))
    _audit("Lead", ld.name, "转为正式客户", "customer=%s" % doc.name)
    return {
        "customer": doc.name,
        "customer_name": doc.customer_name,
        "lead": ld.name,
        "replayed": False,
        "created": True,
        "first_reporter": doc.custom_first_reporter,
        "first_reported_on": str(doc.custom_first_reported_on),
        "account_manager": doc.get("account_manager"),
        "message": _("已转为正式客户 {0}").format(doc.name),
    }


def _ensure_contact(customer_doc, contact_name=None, mobile_no=None):
    """直接建客户时补一个原生 Contact（姓名/手机分开存，不挤进客户名称）。

    已存在同名联系人则复用，不重复建。失败不阻断客户创建，只在返回里说明。
    """
    contact_name = (contact_name or "").strip()
    mobile_no = (mobile_no or "").strip()
    if not contact_name and not mobile_no:
        return None
    try:
        existing = frappe.db.get_value(
            "Dynamic Link",
            {"link_doctype": "Customer", "link_name": customer_doc.name,
             "parenttype": "Contact", "parentfield": "links"},
            "parent",
        )
        if existing:
            return existing
        c = frappe.new_doc("Contact")
        c.first_name = contact_name or mobile_no
        c.mobile_no = mobile_no or None
        c.append("links", {"link_doctype": "Customer", "link_name": customer_doc.name,
                           "link_title": customer_doc.customer_name})
        c.insert()
        frappe.db.set_value("Customer", customer_doc.name, "customer_primary_contact", c.name)
        return c.name
    except Exception:
        frappe.clear_messages()
        frappe.logger("cn_api").warning(
            "create contact failed for %s" % customer_doc.name, exc_info=True
        )
        return None


@frappe.whitelist(methods=["POST"])
def create_customer(customer_name, contact_name=None, mobile_no=None, note=None,
                    account_manager=None):
    """已确认客户主体时直接建正式客户（不强制先写报备）。

    查重顺序：同名客户 → 同名未关闭报备（提示先转正式客户，避免两条并行主数据）。
    报备人固定为当前会话用户，时间取当前时间；不接受客户端指定报备人。
    """
    _require_any_role(SALES_ROLES, "新建正式客户")
    _require(frappe.has_permission("Customer", "create"), _("当前角色无权创建正式客户"))

    customer_name = (customer_name or "").strip()
    _require(customer_name, _("客户名称必填"), frappe.ValidationError)

    dup = _customer_by_name(customer_name)
    if dup:
        return {
            "customer": dup,
            "created": False,
            "replayed": True,
            "existing_customer": dup,
            "message": _("该客户已存在：{0}").format(dup),
        }

    open_lead = frappe.db.get_value(
        "Lead", {"company_name": customer_name, "status": OPEN_LEAD_STATUS}, "name"
    )
    if open_lead:
        return {
            "lead": open_lead,
            "created": False,
            "existing": "lead",
            "message": _("已有未关闭的客户报备 {0}，请使用「转为正式客户」以保留报备人").format(open_lead),
        }

    doc = frappe.new_doc("Customer")
    doc.customer_name = customer_name
    doc.customer_type = "Company"
    doc.customer_group = frappe.db.get_default("Customer Group") or FALLBACK_CUSTOMER_GROUP
    doc.territory = FALLBACK_TERRITORY
    doc.custom_first_reporter = _valid_user(frappe.session.user)
    doc.custom_first_reported_on = now_datetime()
    manager = _valid_user(account_manager) if account_manager else None
    doc.account_manager = manager or doc.custom_first_reporter
    doc.insert()

    contact = _ensure_contact(doc, contact_name, mobile_no)

    frappe.db.commit()
    _audit("Customer", doc.name, "直接新建正式客户" + ("（来源：{0}）".format(note) if note else ""),
           "reporter=%s" % doc.custom_first_reporter)
    return {
        "customer": doc.name,
        "customer_name": doc.customer_name,
        "created": True,
        "replayed": False,
        "contact": contact,
        "first_reporter": doc.custom_first_reporter,
        "first_reported_on": str(doc.custom_first_reported_on),
        "account_manager": doc.get("account_manager"),
        "message": _("已创建正式客户 {0}").format(doc.name),
    }


# ---------------------------------------------------------------- 客户列表 / 详情


@frappe.whitelist(methods=["GET"])
def customer_list(q=None, limit=100):
    """正式客户列表：公司、首次报备人/时间、当前客户负责人、来源报备、订单数。"""
    _require(frappe.has_permission("Customer", "read"), _("当前角色无权查看客户"))
    filters = {"disabled": 0}
    if q:
        filters["customer_name"] = ("like", "%" + q.strip() + "%")

    rows = frappe.get_list(
        "Customer",
        filters=filters,
        fields=["name", "customer_name", "customer_type", "customer_group", "lead_name",
                "account_manager", "custom_first_reporter", "custom_first_reported_on",
                "owner", "creation", "mobile_no"],
        order_by="modified desc",
        limit=int(limit),
    )
    for r in rows:
        r["reporter_name"] = _fullname(r["custom_first_reporter"])
        r["manager_name"] = _fullname(r["account_manager"])
        r["so_count"] = frappe.db.count(
            "Sales Order", {"customer": r["name"], "docstatus": ("<", 2)}
        )

    return {
        "customers": rows,
        "count": len(rows),
        "total": frappe.db.count("Customer", {"disabled": 0}),
        "without_reporter": frappe.db.count("Customer", {"custom_first_reporter": ("is", "not set")}),
    }


@frappe.whitelist(methods=["GET"])
def customer_detail(name):
    """客户详情第一屏数据：公司/联系人/首次报备人/首次报备时间/当前负责人/来源报备 + 关联销售订单。"""
    _require(frappe.db.exists("Customer", name), _("客户不存在：{0}").format(name), frappe.ValidationError)
    _require(frappe.has_permission("Customer", "read", doc=name), _("当前角色无权查看该客户"))

    d = frappe.get_doc("Customer", name)

    contacts = []
    if frappe.has_permission("Contact", "read"):
        contact_names = [
            r.parent for r in frappe.get_all(
                "Dynamic Link",
                filters={"link_doctype": "Customer", "link_name": name, "parenttype": "Contact"},
                fields=["parent"],
            )
        ]
        if d.get("customer_primary_contact") and d.customer_primary_contact not in contact_names:
            contact_names.append(d.customer_primary_contact)
        for cn in contact_names[:10]:
            c = frappe.db.get_value(
                "Contact", cn, ["name", "full_name", "email_id", "mobile_no", "phone"], as_dict=1
            )
            if c:
                c["is_primary"] = cn == d.get("customer_primary_contact")
                contacts.append(c)

    address = None
    if d.get("customer_primary_address"):
        address = frappe.db.get_value(
            "Address", d.customer_primary_address, "address_line1"
        )

    orders = frappe.get_list(
        "Sales Order",
        filters={"customer": name, "docstatus": ("<", 2)},
        fields=["name", "transaction_date", "delivery_date", "business_type", "status",
                "grand_total", "currency", "per_delivered", "per_billed", "docstatus", "owner"],
        order_by="transaction_date desc, creation desc",
        limit=50,
    )
    for o in orders:
        o["owner_name"] = _fullname(o["owner"])
        o["execution_url"] = "/order_execution?sales_order=" + quote(o["name"])
        o["desk_url"] = "/desk/sales-order/" + quote(o["name"])

    lead = None
    if d.get("lead_name"):
        lead = frappe.db.get_value(
            "Lead", d.lead_name,
            ["name", "company_name", "status", "lead_owner", "creation", "mobile_no"], as_dict=1
        )
        if lead:
            lead["reporter_name"] = _fullname(lead.lead_owner)
            lead["url"] = "/lead_detail?name=" + quote(lead["name"])

    return {
        "name": d.name,
        "customer_name": d.customer_name,
        "customer_type": d.customer_type,
        "customer_group": d.customer_group,
        "territory": d.territory,
        "disabled": d.disabled,
        "mobile_no": d.mobile_no,
        "email_id": d.email_id,
        "creation": d.creation,
        "owner": d.owner,
        "owner_name": _fullname(d.owner),
        "first_reporter": d.get("custom_first_reporter"),
        "first_reporter_name": _fullname(d.get("custom_first_reporter")),
        "first_reported_on": str(d.get("custom_first_reported_on") or "") or None,
        "account_manager": d.get("account_manager"),
        "account_manager_name": _fullname(d.get("account_manager")),
        "lead": lead,
        "contacts": contacts,
        "primary_address": address,
        "orders": orders,
        "order_count": len(orders),
        "can_create_order": _can_create_order(),
        "sales_order_new_url": sales_order_new_url(name),
        "desk_url": "/desk/customer/" + quote(d.name),
    }


@frappe.whitelist(methods=["GET"])
def sales_order_new_url(customer=None, business_type=None):
    """销售订单新建 URL（预填客户/订单类型），只是路由参数，不写任何数据。

    真正的订单仍由用户在 Desk 表单里保存/提交，走原生权限与校验。
    """
    params = []
    if customer:
        params.append("customer=" + quote(customer))
    if business_type:
        params.append("business_type=" + quote(business_type))
    url = "/desk/sales-order/new"
    return url + ("?" + "&".join(params) if params else "")


@frappe.whitelist(methods=["GET"])
def customer_center():
    """客户中心首屏：报备与客户两块的统计与可操作标记。"""
    can_lead = bool(frappe.has_permission("Lead", "read"))
    can_customer = bool(frappe.has_permission("Customer", "read"))
    _require(can_lead or can_customer, _("当前角色无权查看客户与报备"))
    return {
        "user": frappe.session.user,
        "business_types": BUSINESS_TYPES,
        "can_read_lead": can_lead,
        "can_read_customer": can_customer,
        "can_create_lead": bool(frappe.has_permission("Lead", "create")),
        "can_create_customer": _can_create_customer(),
        "can_create_order": _can_create_order(),
        "open_leads": frappe.db.count("Lead", {"status": OPEN_LEAD_STATUS}) if can_lead else 0,
        "converted_leads": frappe.db.count("Lead", {"status": "Converted"}) if can_lead else 0,
        "total_customers": frappe.db.count("Customer", {"disabled": 0}) if can_customer else 0,
    }
