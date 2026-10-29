# -*- coding: utf-8 -*-
"""BUILD-60 一致性复核（容器内运行）：机器人写入 → ERPNext 正式单据/库存/审计 的真实对照。

用法：docker exec -w /workspace/development/frappe-bench poc-frappe env/bin/python /workspace/build60_verify.py
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
CFG = json.load(open("/workspace/bot_adapter.local.json", encoding="utf-8"))
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


def call(module, method, params):
    path = f"/api/method/{module}.{method}"
    ts, nonce = str(int(time.time())), secrets.token_hex(12)
    canonical = "\n".join(
        ["POST", path, ts, nonce,
         "&".join(f"{quote(str(k), safe='')}={quote(str(v), safe='')}" for k, v in sorted(params.items()))]
    )
    sig = hmac.new(CFG["bot_adapter_secret"].encode(), canonical.encode(), hashlib.sha256).hexdigest()
    req = urllib.request.Request(
        BASE + path, data=urlencode(params).encode(), method="POST",
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


# ---------------------------------------------------------------- 1. 采购入库：草稿 → 正式单一一对应
drafts = frappe.get_all(
    "Purchase Intake Draft",
    filters={"file_name": ("like", "采购入库-有效%")},
    fields=["name", "status", "purchase_receipt", "file_sha256"],
    order_by="creation asc",
)
confirmed = [d for d in drafts if d["status"] == "Confirmed"]
pr_names = [d["purchase_receipt"] for d in confirmed if d["purchase_receipt"]]
check("V1 每个已确认草稿都有且只有一张已提交采购入库单",
      bool(confirmed) and len(pr_names) == len(confirmed)
      and all(frappe.db.get_value("Purchase Receipt", p, "docstatus") == 1 for p in pr_names),
      f"草稿 {len(confirmed)} 张 → 入库单 {len(pr_names)} 张（{pr_names[-1] if pr_names else '-'}）")

pr_qty = 0.0
for p in pr_names:
    for row in frappe.get_all("Purchase Receipt Item",
                              filters={"parent": p, "item_code": "SENSOR", "warehouse": "原材料仓 - QC"},
                              fields=["qty"]):
        pr_qty += row["qty"]
bin_qty = frappe.db.get_value("Bin", {"item_code": "SENSOR", "warehouse": "原材料仓 - QC"}, "actual_qty") or 0
check("V2 库存增量 == 入库单数量（无重复过账、无凭空增加）",
      abs(float(bin_qty) - pr_qty) < 1e-6, f"Bin={bin_qty} Σ入库单={pr_qty}")

# ---------------------------------------------------------------- 2. 重复确认不重复过账
if confirmed:
    before = frappe.db.count("Purchase Receipt", {"name": ("like", "MAT-PRE-%")})
    env = call("cn_mfg_poc.bot_write", "confirm_draft",
               {"wecom_userid": "zhangsan", "kind": "PURCHASE", "draft": confirmed[-1]["name"]})
    after = frappe.db.count("Purchase Receipt", {"name": ("like", "MAT-PRE-%")})
    check("V3 重复确认不再生成新入库单", env.get("ok") and env["data"].get("already_confirmed") and before == after,
          f"before={before} after={after} already={env.get('data', {}).get('already_confirmed')}")

# ---------------------------------------------------------------- 3. 取消的草稿：无入库单、无库存变化
cancelled = frappe.get_all(
    "Purchase Intake Draft",
    filters={"file_name": ("like", "采购入库-取消%"), "status": "Cancelled"},
    fields=["name", "purchase_receipt"],
)
check("V4 取消的草稿没有关联入库单（库存不变）",
      bool(cancelled) and all(not c["purchase_receipt"] for c in cancelled),
      f"取消草稿 {len(cancelled)} 张")

# ---------------------------------------------------------------- 4. 无效文件不留草稿
bad_files = ["采购入库-无效编码.xlsx", "采购入库-数量为负.xlsx", "采购入库-无表头.xlsx",
             "采购入库-供应商无效.xlsx", "采购入库-仓库无效.xlsx"]
bad_drafts = frappe.db.count("Purchase Intake Draft", {"file_name": ("in", bad_files)})
check("V5 校验失败的文件没有留下任何草稿", bad_drafts == 0, f"残留草稿 {bad_drafts} 张")

# ---------------------------------------------------------------- 5. 客户报备落地
leads = frappe.get_all(
    "Lead",
    filters={"company_name": ("like", "苏州新元精密%"), "status": "Open"},
    fields=["name", "owner", "lead_owner", "company_name"],
)
check("V6 报备写入正式 Lead 且归属报备人本人",
      len(leads) == 1 and leads[0]["owner"] == "wangming@erpnext-poc.localhost",
      f"{leads[0]['name'] if leads else '-'} owner={leads[0]['owner'] if leads else '-'}")

# ---------------------------------------------------------------- 6. 审计留痕
pr_name = pr_names[-1] if pr_names else None
has_comment = bool(pr_name) and bool(
    frappe.get_all("Comment", filters={"reference_doctype": "Purchase Receipt", "reference_name": pr_name}, limit=1)
)
lead_comment = bool(leads) and bool(
    frappe.get_all("Comment", filters={"reference_doctype": "Lead", "reference_name": leads[0]["name"]}, limit=1)
)
check("V7 正式单据上有审计 Comment（采购入库/报备）", has_comment and lead_comment,
      f"PR={has_comment} Lead={lead_comment}")

# ---------------------------------------------------------------- 7. 撤权后确认被拒（库存不变）
import base64

with open("/workspace/build60/采购入库-取消.xlsx", "rb") as f:
    raw = f.read()
env = call("cn_mfg_poc.bot_write", "parse_purchase_excel",
           {"wecom_userid": "zhangsan", "file_name": "采购入库-取消.xlsx",
            "file_base64": base64.b64encode(raw).decode()})
draft = (env.get("data") or {}).get("draft")
check("V8 撤权前可正常生成草稿", env.get("ok") and bool(draft), f"draft={draft}")

binding = frappe.get_doc("WeCom User Binding", {"wecom_userid": "zhangsan"})
binding.enabled = 0
binding.flags.ignore_permissions = True
binding.save()
frappe.db.commit()
env = call("cn_mfg_poc.bot_write", "confirm_draft",
           {"wecom_userid": "zhangsan", "kind": "PURCHASE", "draft": draft or "PID-00000"})
check("V9 撤权后确认被拒（NOT_BOUND）", env.get("ok") is False and env.get("code") == "NOT_BOUND",
      f"code={env.get('code')}")
env2 = call("cn_mfg_poc.bot_write", "parse_purchase_excel",
            {"wecom_userid": "zhangsan", "file_name": "采购入库-取消.xlsx",
             "file_base64": base64.b64encode(raw).decode()})
check("V10 撤权后也不能新建草稿", env2.get("ok") is False and env2.get("code") == "NOT_BOUND",
      f"code={env2.get('code')}")
binding.enabled = 1
binding.flags.ignore_permissions = True
binding.save()
frappe.db.commit()

print(f"\n合计 {len(results)} 项，失败 {failed} 项")
sys.exit(1 if failed else 0)
