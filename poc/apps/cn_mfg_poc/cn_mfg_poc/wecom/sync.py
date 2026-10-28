# -*- coding: utf-8 -*-
"""企微通讯录同步与绑定管理。

- 本地/Mock：sync_members 接收成员列表（userid/name/email），幂等建/启绑定。
- 真实：pull_from_wecom 需要真实 CorpID+Secret（BLOCKED 时明确报错，绝不编造数据）。
- 部门结构仅作备注同步，不自动生成任何 ERP 角色/权限。
"""

import json

import frappe
from frappe import _
from frappe.utils import now_datetime

MOCK_DOMAIN = "wecom.local"


def _require(cond, msg, exc=frappe.ValidationError):
    if not cond:
        frappe.throw(msg, exc)


@frappe.whitelist(methods=["POST"])
def sync_members(members, corp_id=None):
    """成员绑定同步（幂等）。members: [{userid, name, email?}] 或 JSON 字符串。

    规则：邮箱能对上既有 ERP User → 直接绑定；否则创建 Desk User（默认无业务角色）
    并绑定。已存在且启用的绑定跳过。部门不转权限。
    """
    _require_admin()
    if isinstance(members, str):
        members = json.loads(members)
    corp_id = corp_id or _corp_id()

    created_users, created_bindings, skipped = [], [], []
    for m in members:
        userid = (m.get("userid") or "").strip()
        name = (m.get("name") or userid).strip()
        email = (m.get("email") or "").strip().lower() or f"{userid}@{MOCK_DOMAIN}"
        _require(userid, _("成员缺少 userid"), frappe.ValidationError)

        existing_binding = frappe.db.get_value("WeCom User Binding", {"wecom_userid": userid}, "name")
        if existing_binding:
            if frappe.db.get_value("WeCom User Binding", existing_binding, "enabled"):
                skipped.append(userid)
                continue
            # 复职/重新加入：重新启用既有绑定，不新建
            b = frappe.get_doc("WeCom User Binding", existing_binding)
            b.enabled = 1
            b.synced_at = now_datetime()
            b.flags.ignore_permissions = True
            b.save()
            frappe.db.commit()
            created_bindings.append(f"{userid}→重新启用")
            continue

        erp_user = frappe.db.get_value("User", email, "name")
        if not erp_user:
            u = frappe.new_doc("User")
            u.email = email
            u.first_name = name
            u.enabled = 1
            u.user_type = "System User"
            u.send_welcome_email = 0
            u.flags.ignore_permissions = True
            u.insert()
            frappe.db.commit()
            erp_user = u.name
            created_users.append(erp_user)

        b = frappe.new_doc("WeCom User Binding")
        b.corp_id = corp_id
        b.wecom_userid = userid
        b.erp_user = erp_user
        b.enabled = 1
        b.synced_at = now_datetime()
        b.note = f"同步来源: {'mock/本地' if _is_mock() else '企微通讯录'} · 姓名 {name}"
        b.flags.ignore_permissions = True
        b.insert()
        frappe.db.commit()
        created_bindings.append(f"{userid}→{erp_user}")

    return {
        "corp_id": corp_id,
        "created_users": created_users,
        "created_bindings": created_bindings,
        "skipped": skipped,
    }


@frappe.whitelist(methods=["POST"])
def disable_binding(wecom_userid):
    """停用绑定并立刻清会话（离职/禁用撤权入口）。"""
    _require_admin()
    b = frappe.get_doc("WeCom User Binding", {"wecom_userid": wecom_userid})
    b.enabled = 0
    b.flags.ignore_permissions = True
    b.save()
    frappe.db.commit()
    frappe.logger("cn_api").info(json.dumps(
        {"action": "wecom_binding_disabled", "wecom_userid": wecom_userid,
         "erp_user": b.erp_user, "operator": frappe.session.user}, ensure_ascii=False))
    return {"binding": b.name, "enabled": 0, "erp_user": b.erp_user}


@frappe.whitelist(methods=["POST"])
def pull_from_wecom():
    """真实企微通讯录拉取。未配置凭据时明确 BLOCKED，不做任何 Mock 兜底。"""
    _require_admin()
    s = frappe.get_single("WeCom Settings")
    if not s.corp_id or not s.get_password("contact_secret", raise_exception=False):
        frappe.throw(
            _("真实通讯录同步 BLOCKED：缺少 CorpID 或通讯录 Secret。"
              "请管理员在 WeCom Settings 填写后重试（Secret 走密码字段，不要发聊天）。"),
            frappe.ValidationError,
        )
    import urllib.request

    token_url = f"https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid={s.corp_id}&corpsecret={s.get_password('contact_secret')}"
    with urllib.request.urlopen(token_url, timeout=15) as r:
        token = json.loads(r.read().decode())
    if token.get("errcode"):
        frappe.throw(_("获取 access_token 失败：{0}").format(token.get("errmsg")))
    dept_url = f"https://qyapi.weixin.qq.com/cgi-bin/user/list?access_token={token['access_token']}&department_id=1&fetch_child=1"
    with urllib.request.urlopen(dept_url, timeout=15) as r:
        data = json.loads(r.read().decode())
    if data.get("errcode"):
        frappe.throw(_("拉取成员失败：{0}").format(data.get("errmsg")))
    members = [
        {"userid": u["userid"], "name": u.get("name"), "email": (u.get("email") or "").lower() or None}
        for u in data.get("userlist", [])
    ]
    return sync_members(json.dumps(members, ensure_ascii=False))


# ---------------------------------------------------------------- 服务端内部工具（供 Bot 通道用，不白名单）

def get_erp_user_by_wecom_userid(wecom_userid):
    """Bot 消息身份 → ERP User；未绑定返回 None（由调用方拒绝）。"""
    return frappe.db.get_value(
        "WeCom User Binding", {"wecom_userid": wecom_userid, "enabled": 1}, "erp_user"
    )


def _require_admin():
    if "System Manager" not in frappe.get_roles():
        frappe.throw(_("仅系统管理员可管理企微绑定"), frappe.PermissionError)


def _corp_id():
    corp = frappe.db.get_single_value("WeCom Settings", "corp_id")
    return corp or "LOCAL-MOCK-CORP"


def _is_mock():
    return bool(frappe.db.get_single_value("WeCom Settings", "mock_mode"))
