# -*- coding: utf-8 -*-
"""cn_mfg_poc.bot — 企业微信 AI 机器人的受控只读入口（BUILD-50）。

设计（沿用旧 OpenClaw 通道思想，但独立实现，不复用 JSH 业务 ID / 不改 MySQL）：

1. 通道闸：机器人适配器用 HMAC-SHA256 对 `POST\\n<path>\\n<ts>\\n<nonce>\\n<规范化参数>` 签名，
   密钥只存在于 WeCom Settings 的 Password 字段（适配器侧由环境变量注入），请求 ±300 秒有效。
2. 账号闸：适配器只持有 bot-gateway 技术账号 Token，该账号没有任何业务角色。
3. 身份闸：请求里只有企微 UserID，服务端经「WeCom User Binding」解析成 ERP User 后
   `frappe.set_user`，再调用 cn_mfg_poc.api 的业务函数——权限/归属/角色判断与 PC、H5 完全一致，
   不接受提示词自报身份，也不使用 Administrator 共享 Token。

返回统一信封：{"ok": bool, "nature": "REAL_ERP", "erp_user": ..., "as_of": ..., "data": {...}}
拒绝时返回 ok=False + code（PERMISSION_DENIED / NOT_BOUND / VALIDATION / ...），HTTP 仍为 200，
由适配器翻译成中文话术，不会出现「模型编造数值」。
"""

import hashlib
import hmac
import json
import os
import time
from urllib.parse import quote

import frappe
from frappe import _
from frappe.utils import add_days, now_datetime, nowdate

from cn_mfg_poc.wecom.sync import get_erp_user_by_wecom_userid

TS_WINDOW = 300
MGMT_ROLES = {"Sales Manager", "Stock Manager", "Manufacturing Manager", "System Manager"}


def _require(cond, msg, exc=frappe.PermissionError):
    if not cond:
        frappe.throw(msg, exc)


def _log(action, **kw):
    """机器人链路审计。frappe.logger 默认级别是 ERROR（INFO 不落盘），因此同时写站点日志文件。"""
    try:
        kw.update({"action": action, "user": frappe.session.user, "time": str(now_datetime())})
        line = json.dumps(kw, ensure_ascii=False, default=str)
    except Exception:
        return
    try:
        frappe.logger("cn_bot").warning(line)
    except Exception:
        pass
    try:
        log_dir = os.path.join(frappe.get_site_path(), "logs")
        os.makedirs(log_dir, exist_ok=True)
        with open(os.path.join(log_dir, "cn_bot.log"), "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


# ---------------------------------------------------------------- 通道校验与身份解析


class _BotRefusal(Exception):
    """通道闸拒绝：带机器可读 code，供适配器翻译成中文话术。"""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def _deny(code, message):
    raise _BotRefusal(code, message)


def _canonical(method, path, ts, nonce, params):
    body = "&".join(
        f"{quote(str(k), safe='')}={quote(str(v), safe='')}" for k, v in sorted(params.items())
    )
    return "\n".join([method, path, str(ts), str(nonce), body])


def _receive(name):
    """校验签名并解析企微身份。必须在 frappe.set_user 之前调用（set_user 会清空 form_dict）。"""
    params = {
        k: v
        for k, v in (frappe.form_dict or {}).items()
        if not str(k).startswith("_") and k not in ("cmd", "sid")
    }
    ts = frappe.get_request_header("X-Cn-Bot-Timestamp")
    nonce = frappe.get_request_header("X-Cn-Bot-Nonce")
    sig = frappe.get_request_header("X-Cn-Bot-Signature")
    if not (ts and nonce and sig):
        _deny("BAD_SIGNATURE", _("缺少机器人通道签名头"))
    try:
        tsn = int(ts)
    except Exception:
        _deny("BAD_SIGNATURE", _("时间戳非法"))
    if abs(time.time() - tsn) > TS_WINDOW:
        _deny("BAD_SIGNATURE", _("机器人请求签名已过期（±{0} 秒）").format(TS_WINDOW))

    s = frappe.get_single("WeCom Settings")
    if not s.bot_enabled:
        _deny("BOT_DISABLED", _("机器人通道已关闭（WeCom Settings）"))
    secret = s.get_password("bot_adapter_secret", raise_exception=False)
    if not secret:
        _deny("BOT_DISABLED", _("未配置机器人适配器共享密钥"))

    path = f"/api/method/cn_mfg_poc.bot.{name}"
    expect = hmac.new(
        secret.encode("utf-8"),
        _canonical("POST", path, ts, nonce, params).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expect, sig or ""):
        _deny("BAD_SIGNATURE", _("机器人签名校验失败"))

    wecom_userid = (params.get("wecom_userid") or "").strip()
    if not wecom_userid:
        _deny("NOT_BOUND", _("缺少企微 UserID"))
    erp_user = get_erp_user_by_wecom_userid(wecom_userid)
    if not erp_user:
        _deny(
            "NOT_BOUND",
            _("该企微账号尚未绑定 ERP 账号（{0}），请管理员在企微应用完成绑定后再问").format(wecom_userid),
        )
    if not frappe.db.get_value("User", erp_user, "enabled"):
        _deny("USER_DISABLED", _("ERP 账号已停用：{0}").format(erp_user))
    return wecom_userid, params, erp_user


def _serve(name, fn):
    """统一入口：验签 → 换身份 → 执行 → 统一信封。"""
    try:
        wecom_userid, params, erp_user = _receive(name)
    except _BotRefusal as e:
        _log("bot_denied", tool=name, reason=e.code, message=e.message)
        return {"ok": False, "code": e.code, "message": e.message, "nature": "REAL_ERP"}
    except Exception as e:
        _log("bot_error", tool=name, reason="CHANNEL_ERROR", message=str(e))
        return {"ok": False, "code": "CHANNEL_ERROR", "message": str(e), "nature": "REAL_ERP"}

    previous_user = frappe.session.user
    frappe.set_user(erp_user)
    try:
        data = fn(params)
        _log("bot_query", tool=name, wecom_userid=wecom_userid, erp_user=erp_user)
        return {
            "ok": True,
            "nature": "REAL_ERP",
            "tool": name,
            "wecom_userid": wecom_userid,
            "erp_user": erp_user,
            "as_of": str(now_datetime()),
            "data": data,
        }
    except frappe.PermissionError as e:
        frappe.db.rollback()
        _log("bot_denied", tool=name, wecom_userid=wecom_userid, erp_user=erp_user, reason="PERMISSION")
        return {"ok": False, "code": "PERMISSION_DENIED", "message": str(e),
                "erp_user": erp_user, "as_of": str(now_datetime()), "nature": "REAL_ERP"}
    except frappe.ValidationError as e:
        frappe.db.rollback()
        _log("bot_denied", tool=name, wecom_userid=wecom_userid, erp_user=erp_user, reason="VALIDATION")
        return {"ok": False, "code": "VALIDATION", "message": str(e),
                "erp_user": erp_user, "as_of": str(now_datetime()), "nature": "REAL_ERP"}
    except Exception as e:
        frappe.db.rollback()
        _log("bot_error", tool=name, wecom_userid=wecom_userid, erp_user=erp_user, message=str(e))
        return {"ok": False, "code": "ERROR", "message": str(e)[:300],
                "erp_user": erp_user, "as_of": str(now_datetime()), "nature": "REAL_ERP"}
    finally:
        try:
            frappe.set_user(previous_user)
        except Exception:
            pass


# ---------------------------------------------------------------- 查询实现（全部复用 api 层）


def _item_names(item_codes):
    out = {}
    if not item_codes:
        return out
    for r in frappe.get_all("Item", filters={"name": ("in", list(item_codes))},
                           fields=["name", "item_name", "stock_uom"], limit_page_length=0):
        out[r["name"]] = r
    return out


def _resolve_item(q):
    """关键字 → item_code。返回 (item_or_None, candidates)。"""
    q = (q or "").strip()
    if not q:
        return None, []
    if frappe.db.exists("Item", q):
        return q, []
    rows = frappe.get_all(
        "Item",
        filters={"disabled": 0},
        or_filters={"item_code": ("like", f"%{q}%"), "item_name": ("like", f"%{q}%")},
        fields=["name", "item_name"],
        limit=5,
    )
    if len(rows) == 1:
        return rows[0]["name"], []
    if len(rows) > 1:
        return None, [{"item_code": r["name"], "item_name": r["item_name"]} for r in rows]
    return None, []


def _stock_query(p):
    from cn_mfg_poc import api

    item, candidates = _resolve_item(p.get("query") or p.get("item"))
    if candidates:
        return {
            "ambiguous": True,
            "candidates": candidates,
            "hint": _("匹配到多个物料，请用编码再问一次（如 SENSOR）"),
        }
    res = api.stock_balances(warehouse=(p.get("warehouse") or None), item=item)
    names = _item_names({r["item_code"] for r in res.get("balances", [])})
    rows = []
    for r in res.get("balances", []):
        meta = names.get(r["item_code"], {})
        rows.append(
            {
                "item_code": r["item_code"],
                "item_name": meta.get("item_name") or r["item_code"],
                "uom": meta.get("stock_uom") or "",
                "warehouse": r["warehouse"],
                "qty": r["actual_qty"],
                "stock_value": r["stock_value"],
            }
        )
    return {
        "company": res.get("company"),
        "warehouse": res.get("warehouse"),
        "item": item,
        "rows": rows,
        "row_count": len(rows),
        "hint": _("无库存记录") if not rows else None,
    }


def _progress_text(d):
    if d.get("per_delivered") >= 100 and d.get("per_billed") >= 100:
        return "已交付并已收款，订单完成"
    if d.get("per_delivered") >= 100:
        return "已全部交付，待收款/开票"
    if (d.get("per_delivered") or 0) > 0:
        return f"部分交付 {round(d['per_delivered'], 1)}%，仍在交付中"
    return "尚未交付，待安排出库"


def _order_progress(p):
    from cn_mfg_poc import api

    name = (p.get("order") or p.get("name") or "").strip()
    if not name:
        rows = api.my_orders(limit=1).get("orders") or []
        _require(rows, _("您名下暂无销售订单"), frappe.ValidationError)
        name = rows[0]["name"]
    d = api.order_detail(name)

    deliveries = frappe.db.sql(
        """
        select dn.name, dn.posting_date, sum(dni.qty) as qty
        from `tabDelivery Note Item` dni
        join `tabDelivery Note` dn on dn.name = dni.parent
        where dni.against_sales_order = %(so)s and dn.docstatus = 1
        group by dn.name, dn.posting_date order by dn.posting_date desc limit 5
        """,
        {"so": name},
        as_dict=1,
    )
    invoices = frappe.db.sql(
        """
        select si.name, si.posting_date, si.grand_total
        from `tabSales Invoice Item` sii
        join `tabSales Invoice` si on si.name = sii.parent
        where sii.sales_order = %(so)s and si.docstatus = 1
        group by si.name, si.posting_date, si.grand_total order by si.posting_date desc limit 5
        """,
        {"so": name},
        as_dict=1,
    )
    out = {
        "sales_order": d["name"],
        "customer": d["customer"],
        "business_type": d.get("business_type"),
        "status": d["status"],
        "grand_total": d["grand_total"],
        "per_delivered": d["per_delivered"],
        "per_billed": d["per_billed"],
        "progress": _progress_text(d),
        "items": d.get("items", []),
        "delivery_notes": deliveries,
        "invoices": invoices,
    }
    return out


def _my_orders(p):
    from cn_mfg_poc import api

    limit = int(p.get("limit") or 10)
    res = api.my_orders(limit=limit)
    rows = []
    for o in res.get("orders", []):
        o = dict(o)
        o["progress"] = _progress_text(o)
        rows.append(o)
    return {"orders": rows, "row_count": len(rows),
            "hint": _("您名下暂无销售订单") if not rows else None}


def _my_jobs(p):
    from cn_mfg_poc import api

    res = api.my_jobs(limit=int(p.get("limit") or 20))
    jobs = []
    for j in res.get("jobs", []):
        j = dict(j)
        pending = (j.get("for_quantity") or 0) - (j.get("total_completed_qty") or 0)
        j["pending_qty"] = round(max(pending, 0), 3)
        jobs.append(j)
    return {
        "employee": res.get("employee"),
        "employee_name": res.get("employee_name"),
        "jobs": jobs,
        "row_count": len(jobs),
        "hint": _("当前没有分配给您的车间任务") if not jobs else None,
    }


def _mgmt_summary(p):
    _require(
        set(frappe.get_roles()) & MGMT_ROLES,
        _("当前角色无权查看经营摘要（需要：{0}）").format("、".join(sorted(MGMT_ROLES))),
    )
    days = int(p.get("days") or 30)
    days = max(1, min(days, 365))
    since = add_days(nowdate(), -days)
    company = "昆山启程智能设备有限公司"

    so = frappe.db.sql(
        """
        select count(*) as cnt, ifnull(sum(grand_total), 0) as amount
        from `tabSales Order`
        where company = %(c)s and docstatus = 1 and transaction_date >= %(d)s
        """,
        {"c": company, "d": since},
        as_dict=1,
    )[0]
    pending = frappe.db.sql(
        """
        select count(*) as cnt, ifnull(sum(grand_total), 0) as amount
        from `tabSales Order`
        where company = %(c)s and docstatus = 1 and status in ('To Deliver', 'To Deliver and Bill', 'Overdue')
        """,
        {"c": company},
        as_dict=1,
    )[0]
    wo = frappe.db.sql(
        """
        select status, count(*) as cnt from `tabWork Order`
        where company = %(c)s and docstatus < 2 group by status
        """,
        {"c": company},
        as_dict=1,
    )
    stock = frappe.db.sql(
        """
        select ifnull(sum(stock_value), 0) as value, ifnull(sum(actual_qty), 0) as qty
        from `tabBin` where company = %(c)s
        """,
        {"c": company},
        as_dict=1,
    )[0]
    return {
        "company": company,
        "from_date": since,
        "to_date": nowdate(),
        "days": days,
        "sales_orders": {"count": so["cnt"], "amount": so["amount"]},
        "pending_delivery": {"count": pending["cnt"], "amount": pending["amount"]},
        "work_orders": {r["status"]: r["cnt"] for r in wo},
        "stock": {"value": stock["value"], "qty": stock["qty"]},
    }


# ---------------------------------------------------------------- 白名单端点


@frappe.whitelist(methods=["POST"])
def whoami(**kwargs):
    """返回当前企微身份绑定的 ERP 账号、姓名、角色（用于「我是谁」类问法与排障）。"""
    return _serve("whoami", lambda p: {
        "erp_user": frappe.session.user,
        "full_name": frappe.db.get_value("User", frappe.session.user, "full_name"),
        "roles": sorted(frappe.get_roles()),
        "employee": frappe.db.get_value(
            "Employee", {"user_id": frappe.session.user, "status": "Active"},
            ["name", "employee_name"], as_dict=True,
        ),
    })


@frappe.whitelist(methods=["POST"])
def stock_query(**kwargs):
    """授权仓库存量查询（按物料关键字/编码/仓库）。"""
    return _serve("stock_query", _stock_query)


@frappe.whitelist(methods=["POST"])
def order_progress(**kwargs):
    """单个销售订单的交付/收款进度；不给单号时取本人最近一张。"""
    return _serve("order_progress", _order_progress)


@frappe.whitelist(methods=["POST"])
def my_orders(**kwargs):
    """我的销售订单与交付进度。"""
    return _serve("my_orders", _my_orders)


@frappe.whitelist(methods=["POST"])
def my_jobs(**kwargs):
    """我的车间任务（Job Card）与待完成数量。"""
    return _serve("my_jobs", _my_jobs)


@frappe.whitelist(methods=["POST"])
def mgmt_summary(**kwargs):
    """简要经营数据（销售/待交付/生产/库存），仅管理类角色。"""
    return _serve("mgmt_summary", _mgmt_summary)
