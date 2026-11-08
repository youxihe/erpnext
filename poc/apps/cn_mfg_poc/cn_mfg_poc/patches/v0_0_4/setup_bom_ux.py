# -*- coding: utf-8 -*-
"""UX-96B：把行级 BOM 变成销售订单里看得见、选得到的「本单 BOM」。

原生 Sales Order Item.bom_no 其实一直存在且可写，但 in_list_view=0 + 英文 label，
销售在物料表里看不到，只能靠 ERPNext 的"更多信息"，于是误以为系统不支持。
这里只改展示属性，不动字段类型/权限；真正的业务校验在 bom_link.validate_sales_order_bom。

幂等：Property Setter 已存在就跳过，管理员手工改过也不会被覆盖。
"""

import frappe

PROPERTIES = [
    # (doctype, fieldname, property, value, property_type)
    ("Sales Order Item", "bom_no", "label", "本单 BOM", "Data"),
    ("Sales Order Item", "bom_no", "in_list_view", "1", "Check"),
    ("Sales Order Item", "bom_no", "columns", "2", "Int"),
]


def execute():
    from frappe.custom.doctype.property_setter.property_setter import make_property_setter

    created = []
    for dt, field, prop, value, prop_type in PROPERTIES:
        name = "%s-%s-%s" % (dt, field, prop)
        if frappe.db.exists("Property Setter", name):
            continue
        make_property_setter(dt, field, prop, value, prop_type, for_doctype=False)
        created.append(name)

    frappe.db.commit()
    frappe.clear_cache(doctype="Sales Order")
    print("BOM_UX_PROPERTY_SETTERS_CREATED:", created)
