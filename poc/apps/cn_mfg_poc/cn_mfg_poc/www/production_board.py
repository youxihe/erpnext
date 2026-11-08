# -*- coding: utf-8 -*-
"""BUILD-91 PC 生产进度看板（/production_board）：统一导航 iframe 内页。

UX-96A 增补：管理端可在此建项目、改负责人/目标日期/备注，并可跳转模板管理。
只调用 cn_mfg_poc.production 的受控 API，服务端按当前会话用户做角色/负责人校验；
页面本身不写库、不触发库存事务。
"""

import frappe

no_cache = 1

MANAGER_ROLES = {"Manufacturing Manager", "System Manager"}


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.redirect("/login?redirect-to=%2Fproduction_board")
        return
    roles = set(frappe.get_roles())
    context.user = frappe.session.user
    context.user_fullname = frappe.utils.get_fullname(frappe.session.user)
    context.csrf_token = frappe.sessions.get_csrf_token()
    context.page_title = "生产进度"
    context.is_manager = bool(roles & MANAGER_ROLES)
