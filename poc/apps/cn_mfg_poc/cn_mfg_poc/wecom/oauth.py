# -*- coding: utf-8 -*-
"""企微身份 OAuth2 免登（PC/H5/Bot 共用身份源）。

真实链路：企微内打开 H5 → 重定向企微 OAuth → 企微回调 ?code=xxx&state=xxx
→ 服务端用 corp secret 调 qyapi 换 userid → 查绑定 → 建立 ERP 会话。
Mock 链路（mock_mode=1，仅本地联调）：用服务端 HMAC 签名 state 模拟企微回调，
不调用企微 API。上线前必须关闭 Mock 模式并配置可信 HTTPS 域名。

安全底线：
- 不信任客户端自报 userid；真实模式下 userid 只来自企微服务端 API；
- state 签名 + 5 分钟有效期，防伪造/重放；
- 未绑定 / 绑定停用 / ERP 用户停用 一律拒绝；
- Secret 只存 WeCom Settings 密码字段，不出现在日志与响应中。
"""

import base64
import hashlib
import hmac
import json
import time

import frappe
from frappe import _
from frappe.auth import LoginManager
from frappe.utils import cint

STATE_TTL_SECONDS = 300
WECOM_OAUTH_BASE = "https://open.weixin.qq.com/connect/oauth2/authorize"
WECOM_API_BASE = "https://qyapi.weixin.qq.com/cgi-bin"


def _require(cond, msg, exc=frappe.PermissionError):
    if not cond:
        frappe.throw(msg, exc)


def _settings():
    s = frappe.get_single("WeCom Settings")
    return s


def _signing_key():
    key = _settings().get_password("mock_signing_key", raise_exception=False)
    _require(key, _("Mock 签名密钥未配置：请管理员在 WeCom Settings 保存一次以自动生成"), frappe.ValidationError)
    return key


def _sign(payload_b64: str) -> str:
    return hmac.new(_signing_key().encode(), payload_b64.encode(), hashlib.sha256).hexdigest()[:32]


def make_state(payload: dict) -> str:
    raw = base64.urlsafe_b64encode(json.dumps(payload, ensure_ascii=False).encode()).decode()
    return f"{raw}.{_sign(raw)}"


def read_state(state: str) -> dict:
    try:
        raw, sig = state.rsplit(".", 1)
    except ValueError:
        frappe.throw(_("state 格式非法"), frappe.PermissionError)
    if not hmac.compare_digest(_sign(raw), sig):
        frappe.throw(_("state 签名校验失败"), frappe.PermissionError)
    payload = json.loads(base64.urlsafe_b64decode(raw.encode()))
    if time.time() - payload.get("ts", 0) > STATE_TTL_SECONDS:
        frappe.throw(_("state 已过期，请重新发起免登"), frappe.PermissionError)
    return payload


# ---------------------------------------------------------------- 绑定与会话


def resolve_erp_user(wecom_userid: str, corp_id: str | None = None) -> str:
    """企微 userid → ERP User（唯一、启用绑定、启用账号），失败即拒绝。"""
    filters = {"wecom_userid": wecom_userid, "enabled": 1}
    if corp_id:
        filters["corp_id"] = corp_id
    erp_user = frappe.db.get_value("WeCom User Binding", filters, "erp_user")
    if not erp_user:
        frappe.throw(_("企微成员 {0} 未绑定或已停绑").format(wecom_userid), frappe.PermissionError)
    enabled = frappe.db.get_value("User", erp_user, "enabled")
    if not enabled:
        frappe.throw(_("ERP 账号已停用：{0}").format(erp_user), frappe.PermissionError)
    return erp_user


def _establish_session(erp_user: str) -> dict:
    frappe.local.login_manager = LoginManager()
    frappe.local.login_manager.login_as(erp_user)
    sid = frappe.session.sid
    frappe.db.commit()
    frappe.logger("cn_api").info(
        json.dumps({"action": "wecom_session_login", "user": erp_user, "time": str(frappe.utils.now_datetime())},
                   ensure_ascii=False)
    )
    return {"sid": sid, "user": erp_user, "roles": frappe.get_roles()}


# ---------------------------------------------------------------- 白名单端点


@frappe.whitelist(methods=["GET"], allow_guest=True)
def login_url(redirect="/app"):
    """返回企微 OAuth 授权链接。真实模式；Mock 模式返回本地模拟链接。"""
    s = _settings()
    if cint(s.mock_mode):
        frappe.throw(_("当前为 Mock 模式，请使用 mock_authorize（仅限本地联调）"), frappe.ValidationError)
    _require_config(s)
    redirect_uri = f"https://{s.redirect_domain}/api/method/cn_mfg_poc.wecom.oauth.oauth_callback"
    state = make_state({"redirect": redirect, "ts": time.time()})
    url = (
        f"{WECOM_OAUTH_BASE}?appid={s.corp_id}&redirect_uri={frappe.utils.quote(redirect_uri, safe='')}"
        f"&response_type=code&scope=snsapi_base&agentid={s.agent_id}&state={state}#wechat_redirect"
    )
    return {"authorize_url": url}


@frappe.whitelist(methods=["GET"], allow_guest=True)
def oauth_callback(code=None, state=None):
    """企微真实回调：code → userid → 绑定 → ERP 会话。"""
    s = _settings()
    if cint(s.mock_mode):
        frappe.throw(_("Mock 模式下不处理真实企微回调"), frappe.ValidationError)
    _require_config(s)
    _require(code and state, _("缺少 code/state"), frappe.ValidationError)
    payload = read_state(state)

    import urllib.parse
    import urllib.request

    token_url = f"{WECOM_API_BASE}/gettoken?corpid={s.corp_id}&corpsecret={s.get_password('contact_secret')}"
    with urllib.request.urlopen(token_url, timeout=15) as r:
        token = json.loads(r.read().decode())
    if token.get("errcode"):
        frappe.throw(_("获取 access_token 失败：{0}").format(token.get("errmsg")))
    info_url = f"{WECOM_API_BASE}/auth/getuserinfo?access_token={token['access_token']}&code={code}"
    with urllib.request.urlopen(info_url, timeout=15) as r:
        info = json.loads(r.read().decode())
    if info.get("errcode"):
        frappe.throw(_("获取成员身份失败：{0}").format(info.get("errmsg")))
    userid = info.get("userid")
    _require(userid, _("企微未返回成员 UserID"), frappe.PermissionError)

    erp_user = resolve_erp_user(userid, s.corp_id)
    session = _establish_session(erp_user)
    frappe.local.response["type"] = "redirect"
    frappe.local.response["location"] = payload.get("redirect") or "/app"


@frappe.whitelist(methods=["GET"], allow_guest=True)
def mock_authorize(wecom_userid, redirect="/app"):
    """【仅限本地联调】模拟「在企微内点开 H5」：生成带签名 state 的模拟回调链接。

    客户端提供的 wecom_userid 仅用于模拟企微服务端返回；生产环境此入口禁用。
    """
    s = _settings()
    if not cint(s.mock_mode):
        frappe.throw(_("Mock 模式已关闭，请走真实 OAuth：cn_mfg_poc.wecom.oauth.login_url"), frappe.PermissionError)
    state = make_state({"userid": wecom_userid, "redirect": redirect, "ts": time.time()})
    return {"mock_callback_url": f"/api/method/cn_mfg_poc.wecom.oauth.mock_callback?state={state}"}


@frappe.whitelist(methods=["GET"], allow_guest=True)
def mock_callback(state=None):
    """【仅限本地联调】模拟企微 OAuth 回调：验签 → 绑定 → ERP 会话（返回 sid Cookie）。"""
    s = _settings()
    if not cint(s.mock_mode):
        frappe.throw(_("Mock 模式已关闭"), frappe.PermissionError)
    _require(state, _("缺少 state"), frappe.ValidationError)
    payload = read_state(state)
    erp_user = resolve_erp_user(payload["userid"])
    session = _establish_session(erp_user)
    frappe.local.cookie_manager.set_cookie("sid", session["sid"])
    return {"user": session["user"], "sid": session["sid"], "roles": session["roles"],
            "redirect": payload.get("redirect") or "/app"}


def _require_config(s):
    missing = [n for n, v in (("CorpID", s.corp_id), ("AgentID", s.agent_id),
                              ("通讯录 Secret", s.get_password("contact_secret", raise_exception=False)),
                              ("可信域名", s.redirect_domain)) if not v]
    if missing:
        frappe.throw(
            _("真实企微接入缺少配置：{0}。请管理员在 WeCom Settings 中填写（Secret 填密码字段，勿发聊天）。")
            .format("、".join(missing)),
            frappe.ValidationError,
        )
