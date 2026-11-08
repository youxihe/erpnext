# -*- coding: utf-8 -*-
"""UAT-97R：把 7 个业务岗位收敛为中文 Role Profile，并把测试账号显示名改成
「岗位-A-姓名」。

为什么放在 post_model_sync：
- Role Profile 是 Frappe 标准 DocType，需要 schema 就绪后写入。
- 用户角色收敛依赖 Frappe 的 populate_role_profile_roles（User.validate），
  属于数据修复，不是 schema 变更。

幂等：Role Profile 已存在且角色集合一致则跳过；用户 full_name / role_profiles
一致则不重写。不动 User.name(email)、密码、User Permission 与单据 owner。
对照账号（销售-B/车间-B）涉及独立密码，不放在补丁里，由一次性脚本创建。
"""

import frappe

from cn_mfg_poc.role_setup import ensure_role_profiles, sync_identities


def execute():
    prof = ensure_role_profiles(commit=False)
    print("UAT97R_PROFILES", prof)

    rows = sync_identities(include_contrast=False, commit=False)
    changed = [r for r in rows if r.get("changed")]
    for r in changed:
        print("UAT97R_IDENTITY", r["user"], r["changed"],
              r["before"]["roles"], "->", r["after"]["roles"])
    print("UAT97R_IDENTITIES_CHANGED", len(changed), "/", len(rows))
    frappe.db.commit()
