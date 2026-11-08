# -*- coding: utf-8 -*-
"""FLOW-97B 集中采购来源（/procurement_trace）。

采购角色从一张采购订单反查：PO 行 → 采购申请行 → 生产计划 → 各销售订单需求，
以及每条 PO 行的实际入库。只读，不写任何单据。
"""

import frappe

no_cache = 1

PURCHASE_ROLES = {"Purchase User", "Purchase Manager", "Stock User", "Stock Manager",
                  "System Manager"}


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.redirect("/login?redirect-to=%2Fprocurement_trace")
        return
    roles = set(frappe.get_roles())
    if not (roles & PURCHASE_ROLES):
        frappe.throw("仅采购/仓库/系统管理员可查看集中采购来源", frappe.PermissionError)

    context.user = frappe.session.user
    context.user_fullname = frappe.utils.get_fullname(frappe.session.user)
    context.csrf_token = frappe.sessions.get_csrf_token()
    context.page_title = "集中采购来源"
