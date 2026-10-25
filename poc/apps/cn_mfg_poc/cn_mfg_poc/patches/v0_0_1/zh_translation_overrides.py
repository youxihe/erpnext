# -*- coding: utf-8 -*-
"""POC-02：补齐影响本 POC 关键界面的 zh 空翻译。

背景：frappe / erpnext v16 自带的 zh.po 中，以下字符串 msgstr 为空，
导致默认简体中文界面出现中英混排（例如列表页「No 销售订单 created」、
物料列表标题「Item」等）。

处理方式：写站点级 Translation 记录（frappe 会优先使用 DB 翻译，
优先级高于 app 自带 .po，见 frappe/translate.py get_all_translations），
不改任何上游 .po / JSON 文件，可重复执行（幂等）。

复测方式：
  bench --site erpnext-poc.localhost migrate        # 重放
  bench --site erpnext-poc.localhost clear-cache
  浏览器打开 /app/item 应显示「物料」，/app/sales-order 空状态应为中文
"""

import frappe

# msgid -> zh 译文
ZH_OVERRIDES = {
    # DocType 名称 / 列表标题
    "Item": "物料",
    # 列表页空状态
    "No {0} created": "暂无{0}",
    "Clear the filters to see all records.": "清除筛选条件以查看全部记录。",
    "A customer's confirmed order.": "客户确认的销售订单。",
    # 生产 / 收付款相关
    "Advance": "预付款",
    "For Quantity": "本次数量",
    "Transfer Material": "转移物料",
    "Work Order Operations": "工单工序",
}


def execute():
    created = 0
    for source_text, translated in ZH_OVERRIDES.items():
        existing = frappe.db.get_value(
            "Translation",
            {"language": "zh", "source_text": source_text},
            ["name", "translated_text"],
            as_dict=True,
        )
        if existing:
            if existing.translated_text != translated:
                frappe.db.set_value("Translation", existing.name, "translated_text", translated)
                created += 1
            continue

        frappe.get_doc(
            {
                "doctype": "Translation",
                "language": "zh",
                "source_text": source_text,
                "translated_text": translated,
            }
        ).insert(ignore_permissions=True)
        created += 1

    frappe.db.commit()
    print(f"[cn_mfg_poc] zh translation overrides written: {created}")
