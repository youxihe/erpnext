# -*- coding: utf-8 -*-
# WeCom User Binding：企业微信成员 UserID ↔ ERPNext User 唯一绑定。
# 部门/通讯录结构不自动转成任何 ERP 财务/库存权限；业务权限一律按 ERP User 角色判定。

import frappe
from frappe import _
from frappe.model.document import Document


class WeComUserBinding(Document):
    def validate(self):
        # 同一企微 UserID 只能绑定一个 ERP User；同一 ERP User 只接受一个企微 UserID
        for field, other in (("wecom_userid", "erp_user"), ("erp_user", "wecom_userid")):
            dup = frappe.db.get_value(
                "WeCom User Binding",
                {field: self.get(field), "name": ("!=", self.name), "enabled": 1},
                "name",
            )
            if dup:
                frappe.throw(_("绑定冲突：{0} 已存在于 {1}").format(self.get(field), dup))

    def on_update(self):
        if not self.enabled:
            # 解绑/停用后立即清掉该 ERP 用户的在线会话
            from frappe.sessions import clear_sessions
            clear_sessions(user=self.erp_user, force=True)
