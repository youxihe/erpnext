# -*- coding: utf-8 -*-
# 采购入库草稿：H5/Bot Excel 采购入库的草稿载体。
# 校验与转正式采购入库单统一走 cn_mfg_poc.api（服务端鉴权 + 幂等），此处只做基础约束。

import json

import frappe
from frappe import _
from frappe.model.document import Document


class PurchaseIntakeDraft(Document):
    def validate(self):
        if self.lines_json:
            try:
                json.loads(self.lines_json)
            except Exception:
                frappe.throw(_("明细行必须是合法 JSON"))
