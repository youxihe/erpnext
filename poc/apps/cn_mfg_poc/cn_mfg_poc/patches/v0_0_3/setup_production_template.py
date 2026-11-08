# -*- coding: utf-8 -*-
"""RELEASE-95：轻制造固定生产进度模板的一次性初始化（幂等，可重复执行）。

线上站点首次升级到 BUILD-90~94 后，如果没有初始化九阶段模板，
生产人员点击「创建生产进度」会得到「九阶段模板未初始化」错误。
把初始化放进 migrate 补丁，让任何站点迁移后自愈，不依赖人工执行。

做的事全部是自有 app 的自定义字段 / Task / Project Template，不改 ERPNext 标准记录。
"""

import frappe


def execute():
    from cn_mfg_poc.production import setup_template

    out = setup_template()
    frappe.db.commit()
    frappe.clear_cache()
    print("CUSTOM_FIELDS_CREATED:", out.get("custom_fields"))
    print("TEMPLATE_TASKS_CREATED:", out.get("template_tasks"))
    print("TEMPLATE_TASKS_REPAIRED:", out.get("repaired_template_tasks"))
    print("ORPHAN_TASKS_REMOVED:", out.get("removed_orphan_tasks"))
    print("PROJECT_TEMPLATE:", out.get("project_template"))
