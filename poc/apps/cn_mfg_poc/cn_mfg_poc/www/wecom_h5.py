# -*- coding: utf-8 -*-
"""企微自建 H5 工作台（/wecom_h5）：同一 ERPNext Site、同一套受控 API。"""

import frappe


def get_context(context):
    context.user = frappe.session.user
    context.is_guest = frappe.session.user == "Guest"
    # P0-4：Mock 选身份面板只在显式允许的本机/测试站点出现，公网默认关闭
    from cn_mfg_poc.wecom.oauth import mock_allowed
    context.mock_mode = mock_allowed()
    context.csrf_token = frappe.sessions.get_csrf_token() if not context.is_guest else ""
    context.page_title = "轻智造 ERP 移动工作台"

    # BUILD-93：按角色决定默认 Tab，避免非生产角色点进空的任务页
    roles = set() if context.is_guest else set(frappe.get_roles())
    staff = {"Employee", "Manufacturing User", "Manufacturing Manager", "System Manager"}
    context.can_production = bool(roles & staff)
    context.default_tab = "jobs" if context.can_production else "orders"
