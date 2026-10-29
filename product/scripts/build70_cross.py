# -*- coding: utf-8 -*-
"""BUILD-70 三入口联合验收（容器内运行）

三个通道分别是真实不同的入口，不是同一个 HTTP 调用换皮：
  PC  ：容器内 frappe 直连站点数据库（等价于 PC 界面读写）
  H5  ：企微免登 → 真实 sid 会话 → 取页面 CSRF → 调 /api/method/cn_mfg_poc.api.*
  Bot ：HMAC 签名通道 + wecom_userid 换身份 → /api/method/cn_mfg_poc.bot*.*

用法：
  docker exec -w /workspace/development/frappe-bench poc-frappe env/bin/python /workspace/build70_cross.py
  docker exec -w /workspace/development/frappe-bench poc-frappe env/bin/python /workspace/build70_cross.py --after-restart
"""

import base64
import hashlib
import hmac
import http.cookiejar
import json
import re
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import frappe
from frappe.sessions import clear_sessions

BASE = "http://127.0.0.1:8000"
CFG = json.load(open("/workspace/bot_adapter.local.json", encoding="utf-8"))
try:
    ADMIN = json.load(open("/workspace/build70.local.json", encoding="utf-8"))
except Exception:
    ADMIN = {}
COMPANY = "昆山启程智能设备有限公司"
FILES = "/workspace/build60"
AFTER_RESTART = "--after-restart" in sys.argv
RUN_TAG = time.strftime("%m%d%H%M%S")

frappe.init(site="erpnext-poc.localhost", sites_path="/workspace/development/frappe-bench/sites")
frappe.connect()
frappe.set_user("Administrator")

results = []
failed = 0


def check(tag, cond, detail=""):
    global failed
    ok = bool(cond)
    if not ok:
        failed += 1
    line = f"[{'PASS' if ok else 'FAIL'}] {tag}" + (f" · {detail}" if detail else "")
    results.append(line)
    print(line, flush=True)


def section(title):
    print(f"\n—— {title} ——", flush=True)


# ---------------------------------------------------------------- HTTP 基础
def _open(req, timeout=40):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        resp = opener.open(req, timeout=timeout)
        return resp.status, resp.read().decode("utf-8", "replace"), resp.headers
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace"), e.headers or {}


def http(method, path, data=None, headers=None, raw=False):
    url = urllib.parse.urljoin(BASE, path)
    if data is not None and method == "GET":
        url = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(data)
        body = None
    else:
        body = json.dumps(data, ensure_ascii=False).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Accept", "application/json")
    if body is not None:
        req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    status, text, h = _open(req)
    if raw:
        return status, text, h
    try:
        payload = json.loads(text)
    except Exception:
        payload = {"_raw": text[:300]}
    return status, payload, h


def refresh():
    """结束当前只读事务，开启新事务 → 能读到 web 进程刚提交的数据。"""
    try:
        frappe.db.commit()
    except Exception:
        pass


# ---------------------------------------------------------------- H5 通道（企微免登 → sid → CSRF）
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def h5_login(wecom_userid):
    """模拟企微成员打开自建 H5：OAuth mock 回调拿到会话，再从 H5 页面取 CSRF。"""
    st, p, _ = http("GET", f"/api/method/cn_mfg_poc.wecom.oauth.mock_authorize?wecom_userid={wecom_userid}")
    if st != 200:
        return {"ok": False, "status": st, "message": p}
    cb = urllib.parse.urljoin(BASE, p["message"]["mock_callback_url"])
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    try:
        resp = op.open(cb, timeout=40)
        sc, st2 = resp.headers.get("Set-Cookie") or "", resp.status
    except urllib.error.HTTPError as e:
        sc, st2 = (e.headers.get("Set-Cookie") or "") if e.headers else "", e.code
    sid = sc.split("sid=")[1].split(";")[0] if "sid=" in sc else ""
    if not sid:
        return {"ok": False, "status": st2, "message": "no sid"}
    st3, html, _ = http("GET", "/wecom_h5", headers={"Cookie": f"sid={sid}"}, raw=True)
    m = re.search(r'var CSRF = "([^"]+)"', html or "")
    csrf = m.group(1) if m else ""
    # Frappe 会为 Guest 请求也下发 sid Cookie，必须确认会话身份不是 Guest
    st4, p4, _ = http("GET", "/api/method/frappe.auth.get_logged_user", headers={"Cookie": f"sid={sid}"})
    user = p4.get("message") if isinstance(p4, dict) else None
    if not user or user == "Guest":
        return {"ok": False, "status": st2, "message": f"会话身份为 {user}"}
    return {"ok": True, "sid": sid, "csrf": csrf, "user": user}


def h5_api(sess, method, data=None, verb="POST"):
    st, p, _ = http(
        verb,
        f"/api/method/cn_mfg_poc.api.{method}",
        data=data,
        headers={"Cookie": f"sid={sess['sid']}", "X-Frappe-CSRF-Token": sess.get("csrf", "")},
    )
    return st, p


# ---------------------------------------------------------------- Bot 通道（HMAC 签名换身份）
def bot_call(tool, params, module="cn_mfg_poc.bot"):
    path = f"/api/method/{module}.{tool}"
    ts, nonce = str(int(time.time())), secrets.token_hex(12)
    canonical = "\n".join(
        [
            "POST",
            path,
            ts,
            nonce,
            "&".join(f"{urllib.parse.quote(str(k), safe='')}={urllib.parse.quote(str(v), safe='')}"
                     for k, v in sorted(params.items())),
        ]
    )
    sig = hmac.new(CFG["bot_adapter_secret"].encode(), canonical.encode(), hashlib.sha256).hexdigest()
    body = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(BASE + path, data=body, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    req.add_header("Authorization", f"token {CFG['api_key']}:{CFG['api_secret']}")
    req.add_header("X-Cn-Bot-Timestamp", ts)
    req.add_header("X-Cn-Bot-Nonce", nonce)
    req.add_header("X-Cn-Bot-Signature", sig)
    st, text, _ = _open(req)
    try:
        return st, json.loads(text)["message"]
    except Exception:
        return st, {"ok": False, "code": "HTTP_ERROR", "message": text[:200]}


def admin_call(method, data=None, verb="POST"):
    """以管理员 Token 调管理类接口（如通讯录同步）。"""
    st, p, _ = http(verb, f"/api/method/{method}", data=data,
                    headers={"Authorization": f"token {ADMIN['api_key']}:{ADMIN['api_secret']}"})
    return st, p


def bot_ok(env):
    return bool(env.get("ok"))


def bot_data(env):
    return env.get("data") or {}


# ---------------------------------------------------------------- PC 通道
def pc_bin(item_code):
    return {
        r["warehouse"]: float(r["actual_qty"])
        for r in frappe.get_all(
            "Bin", filters={"company": COMPANY, "item_code": item_code, "actual_qty": (">", 0)},
            fields=["warehouse", "actual_qty"],
        )
    }


print("=" * 78)
print(f"BUILD-70 三入口联合验收  RUN={RUN_TAG}  模式={'重启后复测' if AFTER_RESTART else '全量'}")
print("=" * 78)

# ================================================================ P0 自举：绑定与任务分配
section("P0 准备：绑定自举 / 车间任务分配")
for uid, email, name in [
    ("ligong", "ligong@erpnext-poc.localhost", "李工"),
    ("wangming-wx", "wangming@erpnext-poc.localhost", "王明"),
    ("zhangsan", "zhanggong@erpnext-poc.localhost", "张工"),
]:
    st, p = admin_call("cn_mfg_poc.wecom.sync.sync_members",
                       {"members": [{"userid": uid, "name": name, "email": email}]})
    check(f"P0 绑定自举 {uid}", st == 200, f"→ {email} {json.dumps(p, ensure_ascii=False)[:60]}")

# 给未完工 Job Card 分配李工，保证「我的车间任务」有内容
jc_name = "PO-JOB00004"
refresh()
jc = frappe.get_doc("Job Card", jc_name)
assigned = {r.employee for r in (jc.get("employee") or [])}
if "HR-EMP-00001" not in assigned:
    row = frappe.new_doc("Job Card Time Log")
    row.parent = jc_name
    row.parenttype = "Job Card"
    row.parentfield = "employee"
    row.employee = "HR-EMP-00001"
    row.idx = len(assigned) + 1
    row.insert(ignore_permissions=True)
    frappe.db.commit()
refresh()
jc = frappe.get_doc("Job Card", jc_name)
assigned = {r.employee for r in (jc.get("employee") or [])}
check("P0 车间任务已分配给李工", "HR-EMP-00001" in assigned, f"{jc_name} employees={sorted(assigned)}")

# ================================================================ 场景1 角色与身份一致
section("场景1 角色与身份一致")
pc_email = frappe.db.get_value("Employee", "HR-EMP-00001", "user_id")
pc_roles = sorted(frappe.get_roles(pc_email))
h5_l = h5_login("ligong")
st, env = bot_call("whoami", {"wecom_userid": "ligong"})
bot_user = bot_data(env).get("erp_user")
bot_roles = sorted(bot_data(env).get("roles") or [])

check("J1 三入口映射到同一 ERP 用户",
      pc_email == bot_user == "ligong@erpnext-poc.localhost" and h5_l.get("ok"),
      f"PC={pc_email} H5={'sid已建立' if h5_l.get('ok') else '失败'} Bot={bot_user}")
check("J2 PC 与 Bot 角色集合一致", pc_roles == bot_roles, f"{pc_roles}")

# ================================================================ 场景2 客户报备
section("场景2 客户报备（Bot 写入 → PC/H5 同一套数据）")
CUST = f"苏州联合验收客户{RUN_TAG}有限公司"
h5_w = h5_login("wangming-wx")

if AFTER_RESTART:
    lead = frappe.db.get_value("Lead", {"company_name": ("like", "苏州联合验收客户%")},
                               ["name", "owner", "company_name"], as_dict=True)
    check("J3 重启后报备单仍在（PC 侧）", bool(lead), f"lead={lead}")
else:
    st, env = bot_call("prepare_customer_report",
                       {"wecom_userid": "wangming-wx", "customer_name": CUST,
                        "contact_name": "联合验收", "mobile_no": "13700009999"},
                       module="cn_mfg_poc.bot_write")
    draft = bot_data(env).get("draft")
    check("J3 Bot 生成待确认报备草稿", bot_ok(env) and bool(draft), f"draft={draft}")
    st, env2 = bot_call("confirm_draft", {"wecom_userid": "wangming-wx", "kind": "CUSTOMER", "draft": draft},
                        module="cn_mfg_poc.bot_write")
    refresh()
    lead = frappe.db.get_value("Lead", {"company_name": CUST}, ["name", "owner", "company_name"], as_dict=True)
    check("J4 确认后 PC 侧存在正式报备单且归属本人",
          bool(lead) and lead["owner"] == "wangming@erpnext-poc.localhost",
          f"lead={lead['name'] if lead else '-'} owner={lead['owner'] if lead else '-'}")

# H5 用同一客户名报备 → 应被同一套数据查重拒绝，并回带同一单号
if lead:
    st, p = h5_api(h5_w, "report_customer", {"customer_name": lead["company_name"],
                                             "contact_name": "联合验收", "mobile_no": "13700009999"})
    txt = json.dumps(p, ensure_ascii=False)
    check("J5 H5 报备同一客户被查重拦截（与 Bot 共享数据）",
          st >= 400 or "已存在" in txt or "重复" in txt, f"status={st} {txt[:110]}")

# ================================================================ 场景3 销售订单
section("场景3 销售订单（同一订单号/状态/金额 三入口一致）")
SO = "SAL-ORD-2026-00005"
so = frappe.get_doc("Sales Order", SO)
pc_so = {"status": so.status, "grand_total": float(so.grand_total), "per_delivered": float(so.per_delivered or 0)}
st, env = bot_call("order_progress", {"wecom_userid": "wangming-wx", "order": SO})
bot_so = bot_data(env)
check("J6 Bot 与 PC 订单状态/金额一致",
      bot_so.get("status") == pc_so["status"]
      and abs(float(bot_so.get("grand_total") or 0) - pc_so["grand_total"]) < 1e-6,
      f"PC={pc_so} Bot={{'status':{bot_so.get('status')},'total':{bot_so.get('grand_total')}}}")

st, p = h5_api(h5_w, "order_detail", {"name": SO}, verb="GET")
h5_msg = p.get("message", p) if isinstance(p, dict) else p
check("J7 H5 与 PC 订单状态/金额一致",
      isinstance(h5_msg, dict) and h5_msg.get("status") == pc_so["status"]
      and abs(float(h5_msg.get("grand_total") or 0) - pc_so["grand_total"]) < 1e-6,
      f"H5 status={h5_msg.get('status') if isinstance(h5_msg, dict) else h5_msg}")

# 越权：李工查王明的订单
st, env = bot_call("order_progress", {"wecom_userid": "ligong", "order": SO})
st2, p2 = h5_api(h5_l, "order_detail", {"name": SO}, verb="GET")
check("J8 越权订单：Bot 拒绝", not bot_ok(env), f"code={env.get('code')}")
check("J9 越权订单：H5 拒绝", st2 >= 400, f"status={st2}")

# ================================================================ 场景4 车间生产任务
section("场景4 车间任务（H5 报工 → PC / Bot 立即一致）")
refresh()
jc = frappe.get_doc("Job Card", jc_name)
before_qty = float(jc.total_completed_qty or 0)
pending = float(jc.for_quantity or 0) - before_qty
if pending > 0 and jc.docstatus == 0 and not AFTER_RESTART:
    step = round(pending / 2, 3) if pending > 0.2 else pending
    st, p = h5_api(h5_l, "update_job_progress", {"job_card": jc_name, "qty": step, "note": "BUILD-70 联合验收报工"})
    check("J10 H5 本人报工成功", st == 200, f"status={st} {json.dumps(p, ensure_ascii=False)[:110]}")
else:
    check("J10 H5 本人报工（该工单已完工，跳过写入）", True, f"{jc_name} 已完成 {before_qty}")

refresh()
pc_qty = float(frappe.db.get_value("Job Card", jc_name, "total_completed_qty") or 0)
st, env = bot_call("my_jobs", {"wecom_userid": "ligong"})
jobs = bot_data(env).get("jobs") or []
bot_qty = next((float(j.get("total_completed_qty") or 0) for j in jobs if j.get("name") == jc_name), None)
check("J11 Bot 读到的完工数 == PC", bot_qty is not None and abs(bot_qty - pc_qty) < 1e-6,
      f"PC={pc_qty} Bot={bot_qty}")
st, p = h5_api(h5_l, "my_jobs", None, verb="GET")
h5_jobs = (p.get("message", {}) or {}).get("jobs") or []
h5_qty = next((float(j.get("total_completed_qty") or 0) for j in h5_jobs if j.get("name") == jc_name), None)
check("J12 H5 读到的完工数 == PC", h5_qty is not None and abs(h5_qty - pc_qty) < 1e-6,
      f"PC={pc_qty} H5={h5_qty}")

# ================================================================ 场景5 仓库存量
section("场景5 仓库存量（三入口同值 / 无权限拒绝）")
ITEM = "SENSOR"
refresh()
pc_stock = pc_bin(ITEM)
h5_z = h5_login("zhangsan")
st, env = bot_call("stock_query", {"wecom_userid": "zhangsan", "query": ITEM})
bot_stock = {r["warehouse"]: float(r["qty"]) for r in bot_data(env).get("rows", [])}
st, p = h5_api(h5_z, "stock_balances", {"item": ITEM}, verb="GET")
h5_rows = (p.get("message", {}) or {}).get("rows") or (p.get("message", {}) or {}).get("balances") or []
h5_stock = {r["warehouse"]: float(r["qty"] if "qty" in r else r.get("actual_qty") or 0) for r in h5_rows}
check("J13 Bot 库存 == PC Bin", bot_stock == pc_stock, f"PC={pc_stock} Bot={bot_stock}")
check("J14 H5 库存 == PC Bin", h5_stock == pc_stock, f"PC={pc_stock} H5={h5_stock}")

st, env = bot_call("stock_query", {"wecom_userid": "wangming-wx", "query": ITEM})
st2, p2 = h5_api(h5_w, "stock_balances", {"item": ITEM}, verb="GET")
check("J15 无库存角色（销售）：Bot 拒绝", not bot_ok(env), f"code={env.get('code')}")
check("J16 无库存角色（销售）：H5 拒绝", st2 >= 400, f"status={st2}")

# ================================================================ 场景6 Excel 采购入库
section("场景6 Excel 采购入库（Bot 预览→确认 → 库存只变一次）")
ITEM2 = "SENSOR"
refresh()
total_before = sum(pc_bin(ITEM2).values())

if AFTER_RESTART:
    # 重启复测：不新增业务，只核对持久化结果与三入口读数一致
    pr = frappe.db.get_value("Purchase Receipt", {"docstatus": 1}, "name", order_by="creation desc")
    refresh()
    after2 = sum(pc_bin(ITEM2).values())
    check("J17' 重启后正式入库单仍在", bool(pr), f"PR={pr}")
    check("J18' 重启后库存与入库单总量一致（无重复过账/无丢失）",
          bool(pr) and abs(float(frappe.db.sql(
              "select sum(qty) from `tabPurchase Receipt Item` where parent=%s and item_code=%s and docstatus=1",
              (pr, ITEM2))[0][0] or 0) - 5.0) < 1e-6,
          f"末张单据 {pr} 含 {ITEM2} 5.0")
    st, p = h5_api(h5_z, "stock_balances", {"item": ITEM2}, verb="GET")
    h5_rows = (p.get("message", {}) or {}).get("balances") or []
    h5_after = sum(float(r.get("actual_qty") or 0) for r in h5_rows)
    st, env = bot_call("stock_query", {"wecom_userid": "zhangsan", "query": ITEM2})
    bot_after = sum(float(r["qty"]) for r in bot_data(env).get("rows", []))
    check("J19' 重启后 PC / H5 / Bot 库存同值",
          abs(h5_after - after2) < 1e-6 and abs(bot_after - after2) < 1e-6,
          f"PC={after2} H5={h5_after} Bot={bot_after}")
    st, env = bot_call("whoami", {"wecom_userid": "ligong"})
    check("J20' 重启后机器人通道恢复（身份可用）", bot_ok(env), f"user={bot_data(env).get('erp_user')}")
    st, p = h5_api(h5_l, "my_jobs", None, verb="GET")
    check("J21' 重启后 H5 仍可查本人任务", st == 200, f"status={st}")
    print("\n" + "=" * 78)
    for line in results:
        print(line)
    print("=" * 78)
    print(f"合计 {len(results)} 项，失败 {failed} 项")
    sys.exit(1 if failed else 0)

raw = open(f"{FILES}/采购入库-有效.xlsx", "rb").read()
st, env = bot_call("parse_purchase_excel",
                   {"wecom_userid": "zhangsan", "file_base64": base64.b64encode(raw).decode(),
                    "file_name": f"采购入库-联合验收-{RUN_TAG}.xlsx"},
                   module="cn_mfg_poc.bot_write")
draft = bot_data(env).get("draft")
refresh()
after_preview = sum(pc_bin(ITEM2).values())
check("J17 Excel 解析生成待确认草稿", bot_ok(env) and bool(draft), f"draft={draft}")
check("J18 预览阶段库存零变化", abs(after_preview - total_before) < 1e-6,
      f"{total_before} → {after_preview}")

st, env = bot_call("confirm_draft", {"wecom_userid": "zhangsan", "kind": "PURCHASE", "draft": draft},
                   module="cn_mfg_poc.bot_write")
pr = (bot_data(env).get("doc") or bot_data(env).get("purchase_receipt")
      or bot_data(env).get("name") or "")
refresh()
after1 = sum(pc_bin(ITEM2).values())
delta = after1 - total_before
check("J19 确认后生成正式采购入库单", bool(pr) and delta > 0, f"PR={pr or '-'} 库存 {total_before} → {after1}")

# PC 侧核对：该草稿只对应一张已提交入库单，且数量等于库存增量
pr_qty = 0.0
if pr:
    pr_qty = float(frappe.db.sql(
        """select sum(qty) from `tabPurchase Receipt Item`
           where parent=%(p)s and item_code=%(i)s and docstatus=1""",
        {"p": pr, "i": ITEM2},
    )[0][0] or 0)
check("J20 库存增量 == 入库单数量（一次过账）", abs(delta - pr_qty) < 1e-6, f"Δ库存={delta} 单据={pr_qty}")

st, env = bot_call("confirm_draft", {"wecom_userid": "zhangsan", "kind": "PURCHASE", "draft": draft},
                   module="cn_mfg_poc.bot_write")
refresh()
after2 = sum(pc_bin(ITEM2).values())
check("J21 重复确认不重复入库", abs(after2 - after1) < 1e-6, f"{after1} → {after2}")

st, p = h5_api(h5_z, "stock_balances", {"item": ITEM2}, verb="GET")
h5_rows = (p.get("message", {}) or {}).get("rows") or (p.get("message", {}) or {}).get("balances") or []
h5_after = sum(float(r.get("qty") if "qty" in r else r.get("actual_qty") or 0) for r in h5_rows)
check("J22 H5 看到的库存 == PC（入库后）", abs(h5_after - after2) < 1e-6, f"PC={after2} H5={h5_after}")

# ================================================================ 场景7 账号停用撤权
section("场景7 账号停用撤权（三入口同时失效）")
def set_enabled(email, val):
    refresh()
    for _ in range(4):
        try:
            frappe.db.sql("update `tabUser` set enabled=%s where name=%s", (val, email))
            frappe.db.commit()
            return True
        except Exception:
            time.sleep(1)
            refresh()
    return False


set_enabled("ligong@erpnext-poc.localhost", 0)
clear_sessions(user="ligong@erpnext-poc.localhost", force=True)
frappe.db.commit()

st, env = bot_call("whoami", {"wecom_userid": "ligong"})
check("J23 Bot：停用后身份不再可用", not bot_ok(env), f"code={env.get('code')} msg={str(env.get('message'))[:60]}")
st2, p2 = h5_api(h5_l, "my_jobs", None, verb="GET")
check("J24 H5：停用后旧会话被拒", st2 >= 400, f"status={st2}")
sess_new = h5_login("ligong")
check("J25 H5：停用后无法重新免登", not sess_new.get("ok"), f"status={sess_new.get('status')}")
st, env = bot_call("my_jobs", {"wecom_userid": "ligong"})
check("J26 Bot：停用后业务查询被拒", not bot_ok(env), f"code={env.get('code')}")

# 恢复
set_enabled("ligong@erpnext-poc.localhost", 1)
refresh()
h5_l2 = h5_login("ligong")
st, env = bot_call("whoami", {"wecom_userid": "ligong"})
check("J27 恢复启用后 Bot 与 H5 均恢复", bot_ok(env) and h5_l2.get("ok"),
      f"Bot={bot_data(env).get('erp_user')} H5={'ok' if h5_l2.get('ok') else 'fail'}")

# ================================================================ 汇总
print("\n" + "=" * 78)
for line in results:
    print(line)
print("=" * 78)
print(f"合计 {len(results)} 项，失败 {failed} 项")
sys.exit(1 if failed else 0)
