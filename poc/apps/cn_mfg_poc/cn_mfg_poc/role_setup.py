# -*- coding: utf-8 -*-
"""UAT-97R：7 个中文业务岗位档案（Role Profile）与测试账号身份。

设计原则（与 docs/product/tasks/UAT-97R.md 对应）
- 只聚合 ERPNext 原生英文 Role，**不重命名、不删除**原生 Role：Workspace 可见性、
  DocPerm、H5/Bot 的 has_role 判定全部按英文标识，改名或删角色会直接打坏权限。
- Role Profile 是 Frappe 原生 DocType。用户通过 User.role_profiles 挂档案，
  Frappe 在 User.validate → populate_role_profile_roles 里会把 User.roles
  收敛为档案内的角色集合，因此「挂档案」本身就是清理额外角色授权，重跑幂等。
- 只改 User.first_name/full_name 与 role_profiles；不动 User.name(email)、密码、
  User Permission、单据 owner / 企微绑定。
- 参照账号（销售-B/车间-B）只是同档案的第二个用户，不是新角色。
"""

import frappe

# ---------------------------------------------------------------- 岗位档案定义

PROFILES = [
    {
        "name": "经营管理",
        "roles": ["System Manager", "Sales User", "Manufacturing User",
                  "Purchase User", "Stock User", "Accounts User"],
        "scope": "全部业务单据与管理页面（公司经营、订单进度、经营报表、用户与参数）",
        "note": ("该账号在 POC 中同时是唯一具备 System Manager 的业务账号，菜单等于全量后台，"
                 "属于**管理员口径**，不当普通业务岗位使用。"
                 "另外五个 User 级角色不是额外授权，而是中文工作台（Workspace.roles）"
                 "按用户级角色过滤所必需；只留 System Manager 会让「客户与销售」等模块整块消失。"),
    },
    {
        "name": "销售业务",
        "roles": ["Sales User"],
        "scope": ("客户报备、四类销售订单草稿/提交/取消、订单行选择本单 BOM、"
                  "交付进度查看、交货单"),
        "note": ("门户「我的订单」按 owner 只列本人单据；Desk 销售订单列表按原生 DocPerm "
                 "仍可读到全部订单，属已知数据范围缺口（DATA_SCOPE_GAP）。"),
    },
    {
        "name": "设计生产",
        "roles": ["Manufacturing User", "Manufacturing Manager"],
        "scope": ("物料/BOM 设计、九阶段任务模板维护、生产项目创建与负责人分派、"
                  "生产计划与工单、物料移动"),
        "note": ("Manufacturing Manager 用于 /production_template 模板维护与任务分派；"
                 "Project/Task 的原生 Desk 列表未额外授权，统一走 /production_board。"),
    },
    {
        "name": "采购业务",
        "roles": ["Purchase User", "Purchase Manager"],
        "scope": ("物料需求（MR）、询价与供应商报价、采购订单、采购来源反查、采购发票查看、"
                  "订单级 BOM 需求与缺料"),
        "note": ("保留 Purchase Manager 不是沿用旧授权：订单级物料追溯与执行概览按 "
                 "SENIOR_ROLES 判定，只有 Purchase User 时对销售订单会 403，"
                 "采购就看不了自己要买的需求。已记为实现耦合（BACKLOG），"
                 "后续应改成独立的只读口径再降级为 Purchase User。"),
    },
    {
        "name": "仓库管理",
        "roles": ["Stock User"],
        "scope": ("采购入库、原料/WIP/成品仓出入库、工单领料、完工入库、交货单、库存查询"),
        "note": "不授予 Stock Manager：库存调拨与盘点仍可由该角色发起，但无管理级导出。",
    },
    {
        "name": "车间执行",
        "roles": ["Manufacturing User"],
        "scope": ("本人九阶段生产任务的状态/备注/目标日期；查看本人负责的任务与预警"),
        "note": ("只能改 production_owner=本人 的 Task；任务状态与库存/总账完全解耦，"
                 "不触发任何过账。"),
    },
    {
        "name": "财务业务",
        "roles": ["Accounts User"],
        "scope": "销售/采购发票、应收应付账龄、收付款、总账与财务报表",
        "note": "不授予 Accounts Manager：发票删除/取消权限不收，避免误操作历史凭证。",
    },
]

# 现有 7 个业务账号：只改显示名与档案，保留 email/User.name
ACCOUNTS = [
    {"user": "zhaojingli@erpnext-poc.localhost", "profile": "经营管理",
     "full_name": "经营管理-A-赵经理"},
    {"user": "wangming@erpnext-poc.localhost", "profile": "销售业务",
     "full_name": "销售-A-王明"},
    {"user": "liugong@erpnext-poc.localhost", "profile": "设计生产",
     "full_name": "设计生产-A-刘工"},
    {"user": "chengong@erpnext-poc.localhost", "profile": "采购业务",
     "full_name": "采购-A-陈工"},
    {"user": "zhanggong@erpnext-poc.localhost", "profile": "仓库管理",
     "full_name": "仓库-A-张工"},
    {"user": "ligong@erpnext-poc.localhost", "profile": "车间执行",
     "full_name": "车间-A-李工"},
    {"user": "zhoukaiji@erpnext-poc.localhost", "profile": "财务业务",
     "full_name": "财务-A-周会计"},
]

# A/B 对照账号（只建缺失的，不复制管理/财务角色）
CONTRAST_ACCOUNTS = [
    {"user": "xiaoshou-b@erpnext-poc.localhost", "profile": "销售业务",
     "full_name": "销售-B-对照"},
    {"user": "chejian-b@erpnext-poc.localhost", "profile": "车间执行",
     "full_name": "车间-B-对照"},
]

PROFILE_NAMES = [p["name"] for p in PROFILES]


def _profile_roles(name):
    for p in PROFILES:
        if p["name"] == name:
            return list(p["roles"])
    frappe.throw("未定义的岗位档案：{0}".format(name), frappe.ValidationError)


def ensure_role_profiles(commit=True):
    """幂等创建/更新 7 个中文 Role Profile。"""
    created, updated, unchanged = [], [], []
    for p in PROFILES:
        name = p["name"]
        wanted = _profile_roles(name)
        if frappe.db.exists("Role Profile", name):
            doc = frappe.get_doc("Role Profile", name)
            current = [r.role for r in (doc.get("roles") or [])]
            if sorted(current) == sorted(wanted):
                unchanged.append(name)
                continue
            doc.set("roles", [])
            for r in wanted:
                doc.append("roles", {"role": r})
            doc.flags.ignore_permissions = True
            doc.save(ignore_permissions=True)
            updated.append(name)
        else:
            doc = frappe.new_doc("Role Profile")
            doc.role_profile = name
            for r in wanted:
                doc.append("roles", {"role": r})
            doc.flags.ignore_permissions = True
            doc.insert(ignore_permissions=True)
            created.append(name)
    if commit:
        frappe.db.commit()
    return {"created": created, "updated": updated, "unchanged": unchanged}


def _set_identity(user_name, profile, full_name, commit=False):
    """只改 first_name（→ full_name）与 role_profiles；不改密码/邮箱/权限。"""
    if not frappe.db.exists("User", user_name):
        return {"user": user_name, "skipped": "user_missing"}
    user = frappe.get_doc("User", user_name)
    before = {
        "full_name": user.full_name,
        "roles": sorted(r.role for r in (user.get("roles") or [])),
        "profiles": sorted(r.role_profile for r in (user.get("role_profiles") or [])),
    }
    changed = []
    if (user.first_name or "") != full_name or (user.last_name or "") or (user.middle_name or ""):
        user.first_name = full_name
        user.last_name = ""
        user.middle_name = ""
        changed.append("full_name")
    if before["profiles"] != [profile]:
        user.set("role_profiles", [])
        user.append("role_profiles", {"role_profile": profile})
        changed.append("role_profiles")
    # 岗位档案本身被改过（增删原生角色）时，挂档案的用户也要重新收敛；
    # 否则改档案后老用户仍留着旧角色集合，直到下一次 User.save()。
    if set(before["roles"]) != set(_profile_roles(profile)):
        changed.append("roles")
    if not changed:
        return {"user": user_name, "changed": [], "before": before, "after": before}
    user.flags.ignore_permissions = True
    user.save(ignore_permissions=True)
    if commit:
        frappe.db.commit()
    after = {
        "full_name": user.full_name,
        "roles": sorted(r.role for r in (user.get("roles") or [])),
        "profiles": sorted(r.role_profile for r in (user.get("role_profiles") or [])),
    }
    frappe.clear_cache(user=user_name)
    return {"user": user_name, "changed": changed, "before": before, "after": after}


def sync_identities(include_contrast=True, commit=True):
    """把 7 个现有账号 + A/B 对照账号收敛到岗位档案与「岗位-A-姓名」显示名。"""
    _require_admin()
    ensure_role_profiles(commit=False)
    rows = [_set_identity(a["user"], a["profile"], a["full_name"]) for a in ACCOUNTS]
    if include_contrast:
        rows += [_set_identity(a["user"], a["profile"], a["full_name"])
                 for a in CONTRAST_ACCOUNTS]
    if commit:
        frappe.db.commit()
    return rows


def _require_admin():
    if frappe.session.user == "Administrator":
        return
    if "System Manager" not in frappe.get_roles():
        frappe.throw("只有系统管理员可以执行岗位档案同步", frappe.PermissionError)


def snapshot():
    """当前岗位 → 用户 → 原生角色 的只读快照（供页面与证据使用）。"""
    out = {"profiles": [], "users": []}
    for p in PROFILES:
        roles = []
        if frappe.db.exists("Role Profile", p["name"]):
            doc = frappe.get_doc("Role Profile", p["name"])
            roles = sorted(r.role for r in (doc.get("roles") or []))
        out["profiles"].append({
            "profile": p["name"], "roles": roles, "scope": p["scope"], "note": p["note"],
        })
    for a in ACCOUNTS + CONTRAST_ACCOUNTS:
        if not frappe.db.exists("User", a["user"]):
            out["users"].append({"user": a["user"], "full_name": a["full_name"],
                                 "profile": a["profile"], "exists": False})
            continue
        d = frappe.get_doc("User", a["user"])
        out["users"].append({
            "user": d.name,
            "full_name": d.full_name,
            "enabled": bool(d.enabled),
            "profile": a["profile"],
            "profiles": sorted(r.role_profile for r in (d.get("role_profiles") or [])),
            "roles": sorted(r.role for r in (d.get("roles") or [])),
            "exists": True,
            "contrast": a in CONTRAST_ACCOUNTS,
        })
    out["native_roles"] = frappe.db.count("Role")
    out["role_profiles_total"] = frappe.db.count("Role Profile")
    return out
