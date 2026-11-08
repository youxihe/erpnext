# -*- coding: utf-8 -*-
"""BUILD-91 幂等配置：自定义字段 + 九个模板 Task + Project Template。"""
import json

import frappe

frappe.init(site="erpnext-poc.localhost", sites_path="/workspace/development/frappe-bench/sites")
frappe.connect()
frappe.set_user("Administrator")

from cn_mfg_poc import production  # noqa: E402

out = production.setup_template()
tmpl = frappe.get_doc("Project Template", production.TEMPLATE_TYPE)
out["verify"] = {
    "template_name": tmpl.name,
    "template_rows": len(tmpl.tasks),
    "template_subjects": [frappe.db.get_value("Task", t.task, "subject") for t in tmpl.tasks],
    "template_task_records": frappe.db.count("Task", {"status": "Template"}),
    "custom_fields": [
        f for f, *_ in production.CUSTOM_FIELDS
        if frappe.db.exists("Custom Field", "Task-%s" % f)
    ],
    "due_soon_days": production.due_soon_days(),
}
print(json.dumps(out, ensure_ascii=False, indent=1, default=str))
