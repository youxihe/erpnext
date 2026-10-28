# -*- coding: utf-8 -*-
# WeCom Settings（单例）：企微自建应用配置。Secret 用 Password 字段加密存储，不入 Git/日志。

import frappe
from frappe.model.document import Document
from frappe.utils import get_url


class WeComSettings(Document):
    def validate(self):
        if not self.mock_signing_key:
            self.mock_signing_key = frappe.generate_hash(length=32)
        if not self.config_note:
            self.config_note = (
                "真实企微接入需要管理员提供：1) 企业ID CorpID；2) 自建应用 AgentID 与 Secret"
                "（Secret 由管理员直接填入本表单的密码字段，不要发到聊天）；"
                "3) 可信回调域名（H5 所在 HTTPS 域名，须备案并在企微后台配置）；"
                "4) 通讯录同步权限。填写后关闭 Mock 模式。"
            )
