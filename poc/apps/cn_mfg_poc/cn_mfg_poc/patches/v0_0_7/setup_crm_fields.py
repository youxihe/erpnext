# -*- coding: utf-8 -*-
"""CRM-100：Customer 增加「首次报备人 / 首次报备时间」两个自有字段，并做可证实的历史回填。

为什么不用原生字段：
- Customer.owner 是系统创建人，account_manager 是「当前客户负责人」（会随调岗变化），
  两者都不能代表业务上的首次报备人。ERPNext v16 没有同义稳定字段，故用 Custom Field 固化。

字段口径：
- custom_first_reporter  Link/User  首次报备人（业务归属，不随负责人调整而变）
- custom_first_reported_on  Datetime 首次报备时间（来自 Lead.creation 或直接建客户的时间）

回填范围（保守，不猜人）：
- 仅处理 `Customer.lead_name` 有值、且能解析到有效 Lead 的客户；
  报备人 = Lead.lead_owner（存在且启用），时间 = Lead.creation。
- 无法从 Lead 可靠识别的历史客户保持空白，由业务人员后续在客户中心确认，**不按 owner 猜人**。

幂等：Custom Field 已存在跳过；回填只填空值，不覆盖任何人工修正。
"""

import frappe

FIELDS = [
    {
        "fieldname": "custom_first_reporter",
        "label": "首次报备人",
        "fieldtype": "Link",
        "options": "User",
        # 放在「客户类型/区域」之后的第一个卡片里，Desk 客户表单第一屏就能看到
        "insert_after": "territory",
        "read_only": 1,
        "no_copy": 1,
        "search_index": 1,
        "description": "客户第一次被报备的销售（业务归属）。"
                       "不随客户负责人调整而改变；由报备转客户或直接建客户时自动写入。",
    },
    {
        "fieldname": "custom_first_reported_on",
        "label": "首次报备时间",
        "fieldtype": "Datetime",
        "insert_after": "custom_first_reporter",
        "read_only": 1,
        "no_copy": 1,
        "description": "来自报备单（Lead）的首次报备时间；直接建客户时为建客户时间。",
    },
]

# 客户负责人字段的中文标签（原生是英文 Account Manager，影响列表与详情可读性）
LABEL_SETTERS = [
    ("Customer", "account_manager", "label", "当前客户负责人", "Data"),
    ("Customer", "lead_name", "label", "来源报备", "Data"),
]


def execute():
    created, moved = [], []
    for spec in FIELDS:
        name = frappe.db.get_value(
            "Custom Field", {"dt": "Customer", "fieldname": spec["fieldname"]}, "name"
        )
        if name:
            # 幂等修正：字段已存在但放置位置变了（例如从「销售团队」页挪到第一屏）
            if frappe.db.get_value("Custom Field", name, "insert_after") != spec["insert_after"]:
                frappe.db.set_value("Custom Field", name, "insert_after", spec["insert_after"])
                moved.append(spec["fieldname"])
            continue
        doc = {"doctype": "Custom Field", "dt": "Customer"}
        doc.update(spec)
        frappe.get_doc(doc).insert(ignore_permissions=True)
        created.append(spec["fieldname"])

    from frappe.custom.doctype.property_setter.property_setter import make_property_setter

    labels = []
    for dt, field, prop, value, prop_type in LABEL_SETTERS:
        name = "%s-%s-%s" % (dt, field, prop)
        if frappe.db.exists("Property Setter", name):
            continue
        make_property_setter(dt, field, prop, value, prop_type, for_doctype=False)
        labels.append(name)

    frappe.db.commit()
    frappe.clear_cache(doctype="Customer")
    print("CRM100_FIELDS_CREATED:", created)
    print("CRM100_FIELDS_MOVED:", moved)
    print("CRM100_LABEL_SETTERS_CREATED:", labels)

    filled, skipped = _backfill()
    print("CRM100_BACKFILL_FILLED:", len(filled))
    print("CRM100_BACKFILL_ITEMS:", filled)
    print("CRM100_BACKFILL_SKIPPED:", skipped)


def _backfill():
    """只回填能由 Lead 可靠识别的客户；其余保持空白。"""
    filled, skipped = [], 0
    rows = frappe.get_all(
        "Customer",
        filters={"lead_name": ("is", "set")},
        fields=["name", "lead_name", "custom_first_reporter", "custom_first_reported_on"],
    )
    for row in rows:
        if row.custom_first_reporter and row.custom_first_reported_on:
            skipped += 1
            continue

        lead = frappe.db.get_value(
            "Lead", row.lead_name, ["lead_owner", "creation", "status"], as_dict=1
        )
        if not lead:
            skipped += 1
            continue

        reporter = None
        if lead.lead_owner:
            u = frappe.db.get_value("User", lead.lead_owner, ["name", "enabled"], as_dict=1)
            if u and u.enabled:
                reporter = u.name
        if not reporter:
            skipped += 1
            continue

        frappe.db.set_value(
            "Customer",
            row.name,
            {
                "custom_first_reporter": reporter,
                "custom_first_reported_on": lead.creation,
            },
            update_modified=False,
        )
        filled.append({"customer": row.name, "lead": row.lead_name,
                       "reporter": reporter, "reported_on": str(lead.creation)})

    frappe.db.commit()
    return filled, skipped
