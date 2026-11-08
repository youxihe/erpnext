# -*- coding: utf-8 -*-
"""CRM-100 报备详情（/lead_detail?name=）：显示报备归属与转化入口。

页面不写数据；转换动作调用 cn_mfg_poc.crm.convert_lead（幂等、真实权限）。
"""

import frappe

no_cache = 1


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.redirect("/login?redirect-to=%2Flead_detail")
        return

    name = (frappe.form_dict.get("name") or "").strip()
    if not name:
        frappe.throw("缺少报备单号（name 参数）", frappe.ValidationError)
    if not frappe.db.exists("Lead", name):
        frappe.throw("报备单不存在：{0}".format(name), frappe.ValidationError)
    if not frappe.has_permission("Lead", "read", doc=name):
        frappe.throw("当前角色无权查看该报备", frappe.PermissionError)

    context.user = frappe.session.user
    context.user_fullname = frappe.utils.get_fullname(frappe.session.user)
    context.csrf_token = frappe.sessions.get_csrf_token()
    context.lead = name
    context.page_title = "客户报备详情"
