# -*- coding: utf-8 -*-
"""UAT-97R 业务岗位管理（/role_profiles）。

只给系统管理员用，只展示 7 个中文业务岗位档案与其账号；
原生 ERPNext 技术角色仍然存在，页面明确说明，不伪称「已删除标准角色」。
"""

import frappe

from cn_mfg_poc.role_setup import snapshot

no_cache = 1

ADMIN_ROLES = {"System Manager"}


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.redirect("/login?redirect-to=%2Frole_profiles")
        return
    roles = set(frappe.get_roles())
    if not (roles & ADMIN_ROLES):
        frappe.throw("仅系统管理员可查看业务岗位管理", frappe.PermissionError)

    snap = snapshot()
    context.user = frappe.session.user
    context.user_fullname = frappe.utils.get_fullname(frappe.session.user)
    context.profiles = snap["profiles"]
    context.accounts = snap["users"]
    context.native_roles = snap["native_roles"]
    context.profile_total = snap["role_profiles_total"]
    context.page_title = "业务岗位管理"
    context.csrf_token = frappe.sessions.get_csrf_token()
    return context
