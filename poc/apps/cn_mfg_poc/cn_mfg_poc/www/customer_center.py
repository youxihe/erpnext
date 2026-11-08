# -*- coding: utf-8 -*-
"""CRM-100 客户中心（/customer_center）：客户报备 + 正式客户两个可操作列表。

- 只做入口与展示，数据全部来自原生 Lead / Customer，写入走 cn_mfg_poc.crm 的受控接口。
- 角色可见性：能读 Lead 或 Customer 之一即可进入；具体按钮按真实权限显示。
"""

import frappe

no_cache = 1

SALES_ROLES = {"Sales User", "Sales Manager", "System Manager"}


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.redirect("/login?redirect-to=%2Fcustomer_center")
        return

    can_lead = bool(frappe.has_permission("Lead", "read"))
    can_customer = bool(frappe.has_permission("Customer", "read"))
    if not (can_lead or can_customer):
        frappe.throw("当前角色无权查看客户与报备", frappe.PermissionError)

    context.user = frappe.session.user
    context.user_fullname = frappe.utils.get_fullname(frappe.session.user)
    context.csrf_token = frappe.sessions.get_csrf_token()
    context.page_title = "客户中心"
    tab = (frappe.form_dict.get("tab") or "").strip().lower()
    context.default_tab = tab if tab in ("lead", "customer") else ("lead" if can_lead else "customer")
    context.can_read_lead = can_lead
    context.can_read_customer = can_customer
    context.can_create_lead = bool(frappe.has_permission("Lead", "create"))
    context.can_create_customer = bool(frappe.has_permission("Customer", "create"))
    context.can_create_order = bool(frappe.has_permission("Sales Order", "create"))
    context.is_sales = bool(set(frappe.get_roles()) & SALES_ROLES)
