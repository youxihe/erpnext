# -*- coding: utf-8 -*-
"""统一导航门户（/cn_portal）：顶部一级 + 左侧二级的中式后台布局。

菜单完全由现有 Workspace / Workspace Link 推导，按当前用户角色过滤，
与 PC 原生 Desk 共用同一份配置；不新增 DocType、不写业务数据。
"""

import json
import re
from urllib.parse import quote

import frappe

no_cache = 1

# 顶部一级菜单顺序（与 CN MFG POC 模块下的中文工作区一致）
ORDER = [
    ("工作台", "⌂"),
    ("客户与销售", "◈"),
    ("设计与生产", "▤"),
    ("采购管理", "▣"),
    ("仓库管理", "▥"),
    ("物流交付", "⇄"),
    ("财务管理", "¥"),
    ("经营报表", "▦"),
    ("基础资料", "☰"),
    ("系统设置", "⚙"),
]

# 四类订单分类入口（BUILD-80）：Frappe v16 的 Workspace Link 只支持 DocType/Page/Report，
# 不能放带 query 的 URL，所以由门户在「客户与销售」下虚拟注入，不改 Workspace 数据。
# 实测 /desk/sales-order?business_type=生产 会被 Frappe 列表应用为筛选条件。
ORDER_TYPES = [
    ("生产类订单", "生产"),
    ("耗材类订单", "耗材"),
    ("零部件类订单", "零部件"),
    ("服务类订单", "服务"),
]

# BUILD-91：Project/Task 生产进度页。角色口径与 cn_mfg_poc.production 保持一致，
# 由门户侧再做一次可见性过滤，避免无权用户看到点不开的菜单。
PRODUCTION_STAFF_ROLES = {"Employee", "Manufacturing User", "Manufacturing Manager", "System Manager"}
PRODUCTION_READ_ROLES = PRODUCTION_STAFF_ROLES | {
    "Sales User", "Sales Manager", "Accounts User", "Accounts Manager",
}
# BUILD-92：订单执行概览的角色口径与 cn_mfg_poc.order_execution.READ_ROLES 一致
EXECUTION_READ_ROLES = {
    "Sales User", "Sales Manager", "Purchase User", "Purchase Manager",
    "Stock User", "Stock Manager", "Manufacturing User", "Manufacturing Manager",
    "Accounts User", "Accounts Manager", "System Manager",
}


def _slug(text):
    text = (text or "").strip().lower()
    text = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", text)
    return text.strip("-")


def _link_url(row):
    lt, to = row.link_type, row.link_to
    if not to:
        return ""
    if lt == "DocType":
        return "/desk/" + quote(_slug(to))
    if lt == "Report":
        return "/desk/query-report/" + quote(to)
    if lt == "Page":
        return "/desk/" + quote(_slug(to))
    if lt == "Workspace":
        return "/desk/" + quote(to)
    if lt == "URL":
        return to
    return "/desk/" + quote(_slug(to))


def _build_menu(roles):
    by_name = {}
    for ws in frappe.get_all(
        "Workspace",
        filters={"module": "CN MFG POC"},
        fields=["name", "label", "icon"],
        limit=100,
    ):
        doc = frappe.get_doc("Workspace", ws.name)
        allowed = {r.role for r in (doc.get("roles") or [])}
        if allowed and not (allowed & roles):
            continue

        groups, cur = [], None
        for row in doc.get("links") or []:
            if row.hidden:
                continue
            if row.type == "Card Break":
                cur = {"label": row.label, "items": []}
                groups.append(cur)
                continue
            url = _link_url(row)
            if not url:
                continue
            if cur is None:
                cur = {"label": ws.label, "items": []}
                groups.append(cur)
            cur["items"].append({
                "label": row.label,
                "url": url,
                "kind": row.link_type,
                "target": row.link_to,
            })
        by_name[ws.name] = {
            "name": ws.name,
            "label": ws.label,
            "icon": "",
            "groups": groups,
            "count": sum(len(g["items"]) for g in groups),
        }

    menu = []
    for name, icon in ORDER:
        item = by_name.get(name)
        if item:
            item["icon"] = icon
            menu.append(item)
    # 追加 ORDER 之外新增的中文工作区
    for name in sorted(by_name):
        if name not in [m["name"] for m in menu]:
            by_name[name]["icon"] = "◆"
            menu.append(by_name[name])
    return menu


def _inject_order_types(menu):
    """在「客户与销售」模块顶部插入四类订单的分类入口。"""
    for mod in menu:
        if mod["label"] != "客户与销售":
            continue
        if any(g["label"] == "四类订单" for g in mod["groups"]):
            continue
        mod["groups"].insert(0, {
            "label": "四类订单",
            "items": [
                {
                    "label": label,
                    "url": "/desk/sales-order?business_type=" + quote(value),
                    "kind": "DocType",
                    "target": "Sales Order",
                }
                for label, value in ORDER_TYPES
            ],
        })
        mod["count"] = sum(len(g["items"]) for g in mod["groups"])
    return menu


def _add_group(menu, candidates, group_label, items):
    """把一组入口挂到第一个当前用户可见的模块上；已有同名分组则不重复。"""
    for wanted in candidates:
        for mod in menu:
            if mod["label"] != wanted:
                continue
            if any(g["label"] == group_label for g in mod["groups"]):
                return True
            mod["groups"].insert(0, {"label": group_label, "items": items})
            mod["count"] = sum(len(g["items"]) for g in mod["groups"])
            return True
    return False


def _inject_production_links(menu, roles):
    """注入「我的任务」「订单生产进度」PC 入口。

    生产角色优先挂「设计与生产」；纯销售角色通常看不到该工作台，按顺序回退到
    「客户与销售」「工作台」，保证只读的订单生产进度仍然可点。
    """
    items = []
    if roles & PRODUCTION_STAFF_ROLES:
        items.append({
            "label": "我的任务",
            "url": "/production_board?view=mine",
            "kind": "URL", "target": "production_board",
        })
    if roles & PRODUCTION_READ_ROLES:
        items.append({
            "label": "订单生产进度",
            "url": "/production_board?view=order",
            "kind": "URL", "target": "production_board",
        })
    # UX-96A：模板维护只给生产经理/系统管理员，避免普通生产人员误改后续订单默认阶段
    if roles & {"Manufacturing Manager", "System Manager"}:
        items.append({
            "label": "任务模板管理",
            "url": "/production_template",
            "kind": "URL", "target": "production_template",
        })
    if not items:
        return menu
    _add_group(menu, ["设计与生产", "客户与销售", "工作台"], "固定生产进度", items)
    return menu


def _inject_execution_links(menu, roles):
    """BUILD-92：把「订单执行概览」挂到第一个可见的业务模块。"""
    if not (roles & EXECUTION_READ_ROLES):
        return menu
    _add_group(menu, ["客户与销售", "设计与生产", "经营报表", "工作台"], "订单执行", [{
        "label": "订单执行概览",
        "url": "/order_execution",
        "kind": "URL", "target": "order_execution",
    }])
    return menu


PURCHASE_ROLES = {"Purchase User", "Purchase Manager", "Stock User", "Stock Manager",
                  "System Manager"}


def _inject_purchase_links(menu, roles):
    """FLOW-97B：采购/仓库角色从采购订单反查集中采购来源。"""
    if not (roles & PURCHASE_ROLES):
        return menu
    _add_group(menu, ["采购与库存", "设计与生产", "客户与销售", "工作台"], "集中采购", [{
        "label": "集中采购来源",
        "url": "/procurement_trace",
        "kind": "URL", "target": "procurement_trace",
    }])
    return menu


def _inject_role_profile_link(menu, roles):
    """UAT-97R：系统管理员从门户进入「业务岗位管理」（只展示 7 个中文岗位）。"""
    if "System Manager" not in roles:
        return menu
    _add_group(menu, ["系统设置", "工作台"], "岗位与账号", [{
        "label": "业务岗位管理",
        "url": "/role_profiles",
        "kind": "URL", "target": "role_profiles",
    }])
    return menu


# CRM-100：把「客户报备」「客户」两个入口指向客户中心的可操作页面，
# 保留原有两个入口与中文名称，避免用户点进 Desk 后找不到“转正式客户/开销售订单”。
CRM_LINKS = {
    "Lead": ("客户报备", "/customer_center?tab=lead"),
    "Customer": ("客户", "/customer_center?tab=customer"),
}


def _rewrite_crm_links(menu):
    for mod in menu:
        for grp in mod["groups"]:
            for item in grp["items"]:
                if item.get("kind") != "DocType":
                    continue
                mapped = CRM_LINKS.get(item.get("target"))
                if not mapped:
                    continue
                item["label"], item["url"] = mapped
                item["kind"] = "URL"
                item["desk_url"] = "/desk/" + item["target"].lower().replace(" ", "-")
    return menu


# ---------------------------------------------------------------------------
# 菜单与真实权限对齐（PORTAL-PERM-101）
#
# 背景：门户菜单是按 Workspace / Workspace Link 推导的，而 Workspace 的可见性只看
# Workspace.roles（粗粒度），DocType / Report 是否真能打开取决于 DocPerm 与
# Report.roles + ref_doctype 的读权限（细粒度）。两者不是同一套数据，必然出现
# 「菜单能看、点进去 403」。这里在渲染前按当前会话用户的真实权限逐条过滤。
#
# 实测反例（设计生产账号）：42 条菜单里 16 条会被 Desk 拒绝——销售订单/采购订单/
# 交货单/供应商/客户组/供应商组/销售分析/采购分析/库存余额/账龄/总账等。
# ---------------------------------------------------------------------------


def _report_permitted(name):
    """与 frappe.desk.query_report.get_report_doc 的口径完全一致：

        (1) Report.is_permitted() —— 报表自身 Has Role 子表限定的角色；
        (2) has_permission(ref_doctype, "report") —— 注意是 **report** 级而非 read 级。

    之前用 ref_doctype 的 read 级判断，会放行一批「能读单据、但没有报表级权限」的
    账号；而 Frappe 在 get_report_doc 里用的是 report 级，二者不一致会导致菜单放行、
    点进去却 403。这里改成与框架同口径。"""
    if not name or not frappe.db.exists("Report", name):
        return False
    report = frappe.get_doc("Report", name)
    if not report.is_permitted():
        return False
    if report.ref_doctype and not frappe.has_permission(report.ref_doctype, "report"):
        return False
    return True


def _page_permitted(name):
    """Page 的 DocPerm 只有管理员，真正的可见性由 Page.roles 子表决定。"""
    page_roles = frappe.get_all(
        "Has Role", filters={"parent": name, "parenttype": "Page"}, pluck="role")
    return (not page_roles) or bool(set(page_roles) & set(frappe.get_roles()))


def _item_permitted(item):
    kind, target = item.get("kind"), item.get("target")
    if kind == "DocType":
        return bool(target) and bool(frappe.has_permission(target, "read"))
    if kind == "Report":
        return _report_permitted(target)
    if kind == "Page":
        return bool(target) and _page_permitted(target)
    if kind == "URL":
        # 被 _rewrite_crm_links 改写成客户中心的「客户报备 / 客户」，按底层 DocType 判断；
        # 其余自定义页面（order_execution / production_board / ...）各自在页面内校验。
        if target in ("Lead", "Customer"):
            return bool(frappe.has_permission(target, "read"))
        return True
    return True


def _filter_menu_by_permission(menu):
    """去掉当前用户点进去必然被拒的条目，空分组 / 空模块一并收起。"""
    hidden = []
    for mod in menu:
        kept_groups = []
        for grp in mod["groups"]:
            kept = [it for it in grp["items"] if _item_permitted(it)]
            kept_ids = {id(x) for x in kept}
            hidden += [it["label"] for it in grp["items"] if id(it) not in kept_ids]
            if kept:
                grp["items"] = kept
                kept_groups.append(grp)
        mod["groups"] = kept_groups
        mod["count"] = sum(len(g["items"]) for g in kept_groups)
    return [m for m in menu if m["groups"]], hidden



def get_context(context):
    if frappe.session.user == "Guest":
        frappe.redirect("/login?redirect-to=%2Fcn_portal")
        return

    roles = set(frappe.get_roles())
    context.user = frappe.session.user
    context.user_fullname = frappe.utils.get_fullname(frappe.session.user)
    context.csrf_token = frappe.sessions.get_csrf_token()
    # Administrator 会带上几十个角色，全部平铺会把左侧栏底部撑成一长串小字；
    # 这里只显示摘要，完整名单放在 title 里供鼠标悬停查看。
    visible_roles = sorted(roles - {"All", "Guest"})
    context.roles_title = " / ".join(visible_roles)
    context.roles_text = " / ".join(visible_roles[:2]) + (
        " 等 %d 项" % len(visible_roles) if len(visible_roles) > 2 else ""
    )
    # UAT-97R：中文岗位档案优先展示，英文原生角色退到 title 里做技术核对
    profiles = frappe.get_all("User Role Profile",
                              filters={"parent": frappe.session.user, "parenttype": "User"},
                              pluck="role_profile", order_by="idx asc")
    context.profile_text = " / ".join(profiles) or "（未配置岗位档案）"
    # 门户首页 KPI 口径：非管理角色只看本人创建的销售订单，与 my_orders 一致，
    # 避免首页数字和「我的订单」列表对不上（Desk 列表仍按原生 DocPerm）。
    context.can_see_all_sales = bool(roles & {"Sales Manager", "System Manager"})
    menu = _build_menu(roles)
    menu = _inject_order_types(menu)
    menu = _inject_production_links(menu, roles)
    menu = _inject_execution_links(menu, roles)
    menu = _inject_purchase_links(menu, roles)
    menu = _inject_role_profile_link(menu, roles)
    menu = _rewrite_crm_links(menu)
    menu, hidden_items = _filter_menu_by_permission(menu)
    context.menu_hidden_count = len(hidden_items)
    context.menu_json = json.dumps(menu, ensure_ascii=False)
    context.page_title = "统一导航"
