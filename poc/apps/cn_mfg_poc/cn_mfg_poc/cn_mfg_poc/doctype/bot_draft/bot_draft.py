# -*- coding: utf-8 -*-
# 机器人「待本人确认」的写入草稿（BUILD-60）。
# 只有用户本人明确确认后才会转成正式业务单据；确认与取消统一走 cn_mfg_poc.bot_write（服务端鉴权 + 幂等）。

import json

import frappe
from frappe import _
from frappe.model.document import Document


class BotDraft(Document):
    def validate(self):
        if self.payload_json:
            try:
                json.loads(self.payload_json)
            except Exception:
                frappe.throw(_("结构化数据必须是合法 JSON"))
        if self.status != "Draft":
            self.flags.ignore_validate_update_after_submit = True
