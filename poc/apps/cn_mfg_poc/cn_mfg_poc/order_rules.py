# -*- coding: utf-8 -*-
"""四类订单的服务端流程约束（BUILD-80）。

通过 hooks.doc_events 挂在 Sales Order.validate 上，PC / H5 / Bot / REST 任何入口都生效。
BOM 相关约束（生产类是否必须有订单专属 BOM / 工单）等用户确认口径后再补，本文件暂不介入。
"""

import frappe
from frappe import _

ORDER_TYPES = ("生产", "耗材", "零部件", "服务")


def validate_sales_order(doc, method=None):
    """订单类型必填；服务类不得使用库存物料；耗材/零部件类不得混入非库存服务项。"""
    order_type = (doc.get("business_type") or "").strip()
    if not order_type:
        frappe.throw(
            _("请先选择订单类型：生产 / 耗材 / 零部件 / 服务"),
            frappe.ValidationError,
        )
    if order_type not in ORDER_TYPES:
        frappe.throw(
            _("订单类型「{0}」无效，只能是：{1}").format(order_type, " / ".join(ORDER_TYPES)),
            frappe.ValidationError,
        )

    for row in doc.get("items") or []:
        code = row.get("item_code")
        if not code:
            continue
        is_stock = frappe.db.get_value("Item", code, "is_stock_item")
        if order_type == "服务" and is_stock:
            frappe.throw(
                _("服务类订单只能使用非库存服务物料；{0} 是库存物料，会导致错误扣减库存").format(code),
                frappe.ValidationError,
            )
        if order_type in ("耗材", "零部件") and not is_stock:
            frappe.throw(
                _("耗材类 / 零部件类订单必须使用库存物料；{0} 不是库存物料").format(code),
                frappe.ValidationError,
            )
