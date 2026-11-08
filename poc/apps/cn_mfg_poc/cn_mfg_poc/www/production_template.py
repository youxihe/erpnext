# -*- coding: utf-8 -*-
"""UX-96A 九阶段任务模板管理（/production_template）。

仅生产经理 / 系统管理员可进入；页面只调用受控接口，不直接写 DocType。
模板修改只影响之后新建的生产进度项目，不反写已生成订单任务。
"""

import frappe

no_cache = 1

MANAGER_ROLES = {"Manufacturing Manager", "System Manager"}


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.redirect("/login?redirect-to=%2Fproduction_template")
        return
    roles = set(frappe.get_roles())
    if not (roles & MANAGER_ROLES):
        frappe.throw("仅生产负责人/系统管理员可维护生产任务模板", frappe.PermissionError)

    context.user = frappe.session.user
    context.user_fullname = frappe.utils.get_fullname(frappe.session.user)
    context.csrf_token = frappe.sessions.get_csrf_token()
    context.page_title = "任务模板管理"
    context.is_manager = True
