# -*- coding: utf-8 -*-
"""UX-96B：给订单行加「人工确认」标记，避免默认 BOM 冒充已确认。

背景：ERPNext 原生 get_item_details() 会把 Item.default_bom 自动写进
Sales Order Item.bom_no，因此「bom_no 有值」不等于「本单已确认」。
本补丁新增隐藏字段 custom_bom_confirmed（Check），只由人工动作置位：
- 界面「选择本单 BOM」确认
- 手工改动 bom_no
- 已提交订单（提交即确认，读取时按 docstatus 判定）

幂等：Custom Field 已存在就跳过。
"""

import frappe

FIELD = "custom_bom_confirmed"


def execute():
    if frappe.db.exists("Custom Field", {"dt": "Sales Order Item", "fieldname": FIELD}):
        print("BOM_CONFIRM_FIELD_EXISTS")
        return

    frappe.get_doc({
        "doctype": "Custom Field",
        "dt": "Sales Order Item",
        "fieldname": FIELD,
        "label": "本单 BOM 已确认",
        "fieldtype": "Check",
        "default": "0",
        "hidden": 1,
        "read_only": 1,
        "no_copy": 1,
        "print_hide": 1,
        "description": "由系统在人工选用/改动 BOM 时置位；"
                      "ERPNext 新建订单行自动带入的默认 BOM 不算确认。",
        "insert_after": "bom_no",
    }).insert(ignore_permissions=True)
    frappe.db.commit()
    frappe.clear_cache(doctype="Sales Order")
    print("BOM_CONFIRM_FIELD_CREATED", FIELD)
