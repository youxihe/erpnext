# -*- coding: utf-8 -*-
"""BUILD-50 一致性复核（容器内运行）：机器人返回数值 == ERPNext 数据库数值 == PC/H5 同一套数据。

用法：docker exec -w /workspace/development/frappe-bench poc-frappe env/bin/python /workspace/build50_verify.py
"""

import hashlib
import hmac
import json
import secrets
import sys
import time
import urllib.request
import urllib.error
from urllib.parse import quote, urlencode

import frappe

BASE = "http://127.0.0.1:8000"
CFG_PATH = sys.argv[1] if len(sys.argv) > 1 else "/workspace/bot_adapter.local.json"
CFG = json.load(open(CFG_PATH, encoding="utf-8"))
COMPANY = "昆山启程智能设备有限公司"

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
    print(line)


def call(tool, params):
    path = f"/api/method/cn_mfg_poc.bot.{tool}"
    ts, nonce = str(int(time.time())), secrets.token_hex(12)
    canonical = "\n".join(
        ["POST", path, ts, nonce,
         "&".join(f"{quote(str(k), safe='')}={quote(str(v), safe='')}" for k, v in sorted(params.items()))]
    )
    sig = hmac.new(CFG["bot_adapter_secret"].encode(), canonical.encode(), hashlib.sha256).hexdigest()
    req = urllib.request.Request(
        BASE + path,
        data=urlencode(params).encode(),
        method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"token {CFG['api_key']}:{CFG['api_secret']}",
            "X-Cn-Bot-Timestamp": ts,
            "X-Cn-Bot-Nonce": nonce,
            "X-Cn-Bot-Signature": sig,
        },
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        return json.loads(opener.open(req, timeout=30).read().decode())["message"]
    except urllib.error.HTTPError as e:
        return {"ok": False, "code": "HTTP_ERROR", "message": e.read().decode()[:200]}


# ---------------------------------------------------------------- 1. 库存：Bot vs Bin
bin_rows = frappe.get_all(
    "Bin", filters={"company": COMPANY, "item_code": "SENSOR", "actual_qty": (">", 0)},
    fields=["item_code", "warehouse", "actual_qty"],
)
db_sensor = {r["warehouse"]: r["actual_qty"] for r in bin_rows}
env = call("stock_query", {"wecom_userid": "zhangsan", "query": "SENSOR", "warehouse": ""})
bot_sensor = {r["warehouse"]: r["qty"] for r in (env.get("data") or {}).get("rows", [])}
check("V1 库存：机器人 == Bin 表", db_sensor == bot_sensor, f"DB={db_sensor} BOT={bot_sensor}")

# ---------------------------------------------------------------- 2. 订单进度：Bot vs Sales Order
so_name = "SAL-ORD-2026-00005"
db_so = frappe.db.get_value(
    "Sales Order", so_name, ["status", "per_delivered", "per_billed", "grand_total"], as_dict=True
)
env = call("order_progress", {"wecom_userid": "wangming-wx", "order": so_name})
d = env.get("data") or {}
check(
    "V2 订单进度：机器人 == 销售订单单据",
    env.get("ok") and d.get("status") == db_so["status"]
    and d.get("per_delivered") == db_so["per_delivered"]
    and d.get("grand_total") == db_so["grand_total"],
    f"DB={db_so} BOT={ {k: d.get(k) for k in ('status','per_delivered','grand_total')} }",
)

# ---------------------------------------------------------------- 3. 车间任务：Bot vs Job Card
jc_name = "PO-JOB00003"
db_jc = frappe.db.get_value(
    "Job Card", jc_name, ["status", "for_quantity", "total_completed_qty"], as_dict=True
)
env = call("my_jobs", {"wecom_userid": "ligong", "limit": 20})
jobs = {(j["name"]): j for j in (env.get("data") or {}).get("jobs", [])}
bot_jc = jobs.get(jc_name) or {}
check(
    "V3 车间任务：机器人 == Job Card",
    env.get("ok") and bot_jc.get("status") == db_jc["status"]
    and bot_jc.get("for_quantity") == db_jc["for_quantity"]
    and round(bot_jc.get("total_completed_qty") or 0, 6) == round(db_jc["total_completed_qty"] or 0, 6),
    f"DB={db_jc} BOT={ {k: bot_jc.get(k) for k in ('status','for_quantity','total_completed_qty')} }",
)

# ---------------------------------------------------------------- 4. 经营摘要：Bot vs 直连 SQL
db_so_agg = frappe.db.sql(
    "select count(*) cnt, ifnull(sum(grand_total),0) amt from `tabSales Order` "
    "where company=%(c)s and docstatus=1", {"c": COMPANY}, as_dict=True
)[0]
env = call("mgmt_summary", {"wecom_userid": "zhaojingli", "days": 3650})
s = (env.get("data") or {}).get("sales_orders") or {}
check(
    "V4 经营摘要：机器人 == 服务端聚合",
    env.get("ok") and s.get("count") == db_so_agg["cnt"] and abs((s.get("amount") or 0) - float(db_so_agg["amt"])) < 0.01,
    f"DB={db_so_agg} BOT={s}",
)

# ---------------------------------------------------------------- 5. 撤权：停用绑定后机器人立即失效
b = frappe.get_doc("WeCom User Binding", {"wecom_userid": "ligong"})
b.enabled = 0
b.flags.ignore_permissions = True
b.save()
frappe.db.commit()
env = call("my_jobs", {"wecom_userid": "ligong", "limit": 5})
check("V5 撤权：停用绑定后机器人被拒", env.get("ok") is False and env.get("code") == "NOT_BOUND",
      f"code={env.get('code')}")
b.enabled = 1
b.flags.ignore_permissions = True
b.save()
frappe.db.commit()
env = call("my_jobs", {"wecom_userid": "ligong", "limit": 5})
check("V6 复权：重新启用后恢复查询", env.get("ok") is True, f"code={env.get('code')}")

# ---------------------------------------------------------------- 6. 通道开关：bot_enabled=0 全拒
s_doc = frappe.get_single("WeCom Settings")
s_doc.bot_enabled = 0
s_doc.flags.ignore_permissions = True
s_doc.save()
frappe.db.commit()
env = call("stock_query", {"wecom_userid": "zhangsan", "query": "SENSOR", "warehouse": ""})
check("V7 开关：关闭机器人通道后全拒", env.get("ok") is False and env.get("code") == "BOT_DISABLED",
      f"code={env.get('code')}")
s_doc.bot_enabled = 1
s_doc.flags.ignore_permissions = True
s_doc.save()
frappe.db.commit()

# ---------------------------------------------------------------- 7. 只读性：机器人端点不得产生写入
before = frappe.db.sql("select count(*) from `tabComment`")[0][0]
call("whoami", {"wecom_userid": "zhaojingli"})
call("stock_query", {"wecom_userid": "zhangsan", "query": "SENSOR", "warehouse": ""})
call("my_orders", {"wecom_userid": "wangming-wx", "limit": 5})
after = frappe.db.sql("select count(*) from `tabComment`")[0][0]
check("V8 只读链路不产生业务写入（Comment 数不变）", before == after, f"{before} → {after}")

print(f"\n合计 {len(results)} 项，失败 {failed} 项")
sys.exit(1 if failed else 0)
