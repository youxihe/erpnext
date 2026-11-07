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


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.redirect("/login?redirect-to=%2Fcn_portal")
        return

    roles = set(frappe.get_roles())
    context.user = frappe.session.user
    context.user_fullname = frappe.utils.get_fullname(frappe.session.user)
    context.csrf_token = frappe.sessions.get_csrf_token()
    context.roles_text = " / ".join(sorted(roles - {"All", "Guest"}))
    context.menu_json = json.dumps(_build_menu(roles), ensure_ascii=False)
    context.page_title = "统一导航"
