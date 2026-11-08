# -*- coding: utf-8 -*-
"""BUILD-92 PC 订单执行概览（/order_execution）：统一导航 iframe 内页，只读聚合。"""
import frappe

no_cache = 1


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.redirect("/login?redirect-to=%2Forder_execution")
        return
    context.user = frappe.session.user
    context.user_fullname = frappe.utils.get_fullname(frappe.session.user)
    context.csrf_token = frappe.sessions.get_csrf_token()
    context.page_title = "订单执行概览"
