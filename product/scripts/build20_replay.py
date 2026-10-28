# -*- coding: utf-8 -*-
"""BUILD-20 API 合同回放：以真实用户 Token 走 HTTP，覆盖允许/拒绝/幂等。

运行于宿主机。密钥来自 D:/ERP/poc/share/api_keys.local.json（不入 Git）。
输出：逐条回放结果 + 最终断言（任一失败 exit 1）。
"""
import io
import json
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:18000"
KEYS = json.load(io.open(r"D:/ERP/poc/share/api_keys.local.json", encoding="utf-8"))

WANG = KEYS["wangming@erpnext-poc.localhost"]
LI = KEYS["ligong@erpnext-poc.localhost"]
ZHANG = KEYS["zhanggong@erpnext-poc.localhost"]

results = []


def call(user_keys, method, params=None, data=None, expect=200, tag=""):
    url = f"{BASE}/api/method/{method}"
    if params:
        from urllib.parse import urlencode
        url += "?" + urlencode(params)
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, method="POST" if data is not None else "GET")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    if user_keys:
        req.add_header("Authorization", f"token {user_keys[0]}:{user_keys[1]}")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        resp = opener.open(req, timeout=30)
        status, payload = resp.status, json.loads(resp.read().decode())
        err = None
    except urllib.error.HTTPError as e:
        status = e.code
        try:
            payload = json.loads(e.read().decode())
        except Exception:
            payload = {}
        err = (payload.get("_server_messages") or payload.get("exception") or "")[:160]
    ok = (status == expect)
    results.append((tag, method, status, expect, ok))
    print(f"{'PASS' if ok else 'FAIL'} | {tag:<28} | {status} (期望 {expect}) | {method}")
    if err:
        print(f"     └ 错误消息: {err}")
    return status, payload


print("=" * 84)
# ---------------------------------------------------------------- 李工：车间任务
st, p = call(LI, "cn_mfg_poc.api.my_jobs", expect=200, tag="李工查我的任务")
jobs = {j["name"]: j for j in p.get("message", {}).get("jobs", [])}
print("     └ 任务:", {k: (v["status"], v["total_completed_qty"]) for k, v in jobs.items()})
assert "PO-JOB00003" in jobs and "PO-JOB00001" in jobs, "李工任务列表缺本人任务"
assert not any("PO-JOB00002" == k for k in jobs), "李工不应看到张工的 PO-JOB00002"

jc3 = jobs.get("PO-JOB00003")
if jc3 and jc3["status"] != "Completed":
    st, p = call(LI, "cn_mfg_poc.api.update_job_progress",
                 data={"job_card": "PO-JOB00003", "qty": 0.5}, expect=200, tag="李工报工完成 0.5/0.5")
    msg = p.get("message", {})
    print("     └ 结果:", msg.get("status"), msg.get("completed"), "/", msg.get("for_quantity"))
    assert msg.get("status") == "Completed", "PO-JOB00003 应为 Completed"
else:
    print("PASS | [跳过] 李工报工完成 0.5/0.5        | PO-JOB00003 上一轮已完成")

st, p = call(LI, "cn_mfg_poc.api.update_job_progress",
             data={"job_card": "PO-JOB00003", "qty": 0.5}, expect=417, tag="重复报工被拒(任务已完成)")

st, p = call(LI, "cn_mfg_poc.api.update_job_progress",
             data={"job_card": "PO-JOB00002", "qty": -1}, expect=403, tag="替张工报工被拒(未分配)")

st, p = call(LI, "cn_mfg_poc.api.update_job_progress",
             data={"job_card": "PO-JOB00004", "qty": 999}, expect=417, tag="超量报工被拒")

st, p = call(LI, "cn_mfg_poc.api.report_customer",
             data={"customer_name": "越权测试公司"}, expect=403, tag="李工报备客户被拒")

st, p = call(LI, "cn_mfg_poc.api.my_orders", expect=403, tag="李工查销售订单被拒")

# ---------------------------------------------------------------- 王明：客户 + 订单
st, p = call(WANG, "cn_mfg_poc.api.search_customers", params={"q": "海天"}, expect=200, tag="王明查客户")
assert p["message"]["customers"], "应能查到宁波海天精工"

NEW_CO = "苏州瑞丰自动化设备有限公司"
st, p = call(WANG, "cn_mfg_poc.api.report_customer",
             data={"customer_name": NEW_CO, "contact_name": "张经理", "mobile_no": "13900002222"},
             expect=200, tag="王明报备新客户")
lead1 = p["message"].get("lead")
print("     └ 报备单:", lead1)
assert lead1, "应创建报备单"

st, p = call(WANG, "cn_mfg_poc.api.report_customer",
             data={"customer_name": NEW_CO, "contact_name": "张经理"},
             expect=200, tag="重复报备幂等返回原单")
assert p["message"].get("lead") == lead1, "重复报备应返回同一张报备单"

st, p = call(WANG, "cn_mfg_poc.api.my_orders", expect=200, tag="王明查我的订单")
print("     └ 订单数:", len(p["message"]["orders"]))

st, p = call(WANG, "cn_mfg_poc.api.stock_balances", expect=403, tag="销售查库存被拒")

st, p = call(WANG, "cn_mfg_poc.api.update_job_progress",
             data={"job_card": "PO-JOB00004", "qty": 0.1}, expect=403, tag="销售报工被拒(未绑员工)")

# ---------------------------------------------------------------- 张工：库存 + 采购入库
st, p = call(ZHANG, "cn_mfg_poc.api.stock_balances",
             params={"warehouse": "原材料仓 - QC"}, expect=200, tag="张工查原材料仓")
bal = {b["item_code"]: b["actual_qty"] for b in p["message"]["balances"]}
print("     └ 库存:", bal)

st, p = call(ZHANG, "cn_mfg_poc.api.prepare_purchase_draft",
             data={"supplier": "昆山精工零部件有限公司",
                   "lines": [{"item_code": "FASTENER", "qty": 10, "rate": 5}]},
             expect=200, tag="张工建采购入库草稿")
draft = p["message"]["draft"]
print("     └ 草稿:", draft, p["message"]["lines"])

st, p = call(ZHANG, "cn_mfg_poc.api.confirm_purchase_draft",
             data={"draft": draft}, expect=200, tag="张工确认入库(真实过账)")
pr = p["message"]["purchase_receipt"]
print("     └ 采购入库单:", pr)

st, p = call(ZHANG, "cn_mfg_poc.api.confirm_purchase_draft",
             data={"draft": draft}, expect=200, tag="重复确认幂等(不再过账)")
assert p["message"]["purchase_receipt"] == pr and p["message"]["already_confirmed"], "重复确认应返回原单"

before = float(bal.get("FASTENER", 0))
st, p = call(ZHANG, "cn_mfg_poc.api.stock_balances",
             params={"warehouse": "原材料仓 - QC", "item": "FASTENER"}, expect=200, tag="确认后库存复核")
bal2 = p["message"]["balances"]
print("     └ FASTENER 现存:", bal2)
assert bal2 and abs(bal2[0]["actual_qty"] - (before + 10)) < 1e-9, \
    f"FASTENER 应为 {before}+10={before + 10}，仅入库一次"

st, p = call(ZHANG, "cn_mfg_poc.api.prepare_purchase_draft",
             data={"supplier": "昆山精工零部件有限公司", "lines": [{"item_code": "NO-SUCH-ITEM", "qty": 1}]},
             expect=417, tag="无效物料被拒")

st, p = call(ZHANG, "cn_mfg_poc.api.prepare_purchase_draft",
             data={"supplier": "不存在的供应商", "lines": [{"item_code": "FASTENER", "qty": 1}]},
             expect=417, tag="无效供应商被拒")

st, p = call(LI, "cn_mfg_poc.api.prepare_purchase_draft",
             data={"supplier": "昆山精工零部件有限公司", "lines": [{"item_code": "FASTENER", "qty": 1}]},
             expect=403, tag="制造员工建采购草稿被拒")

# ---------------------------------------------------------------- 匿名
st, p = call(None, "cn_mfg_poc.api.my_orders", expect=403, tag="匿名调用被拒")

print("=" * 84)
fails = [r for r in results if not r[4]]
print(f"合计 {len(results)} 项，失败 {len(fails)} 项")
if fails:
    for f in fails:
        print("  FAIL:", f)
    raise SystemExit(1)
print("BUILD-20 API 回放全部通过")
