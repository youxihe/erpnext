# -*- coding: utf-8 -*-
"""CRM-100 客户详情（/customer_detail?name=）：第一屏展示归属与关联，一键新建销售订单。

页面本身不写业务数据；权限在 get_context 与 crm.customer_detail 两处各校验一次。
"""

import frappe

no_cache = 1


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.redirect("/login?redirect-to=%2Fcustomer_detail")
        return

    name = (frappe.form_dict.get("name") or "").strip()
    if not name:
        frappe.throw("缺少客户编号（name 参数）", frappe.ValidationError)

    if not frappe.db.exists("Customer", name):
        frappe.throw("客户不存在：{0}".format(name), frappe.ValidationError)
    if not frappe.has_permission("Customer", "read", doc=name):
        frappe.throw("当前角色无权查看该客户", frappe.PermissionError)

    context.user = frappe.session.user
    context.user_fullname = frappe.utils.get_fullname(frappe.session.user)
    context.csrf_token = frappe.sessions.get_csrf_token()
    context.customer = name
    context.page_title = "客户详情"
    context.can_create_order = bool(frappe.has_permission("Sales Order", "create"))
