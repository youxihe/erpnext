# -*- coding: utf-8 -*-
"""BUILD-93 真实 HTTP 验收：H5 生产任务页、订单进度、三入口接口权限。

不 mock 服务端：全部走 /api/method 与页面模板，用真实账号 Token 代表真实会话。
"""
import json
import urllib.error
import urllib.request
from urllib.parse import quote, urlencode

BASE = "http://localhost:8000"
KEYS_FILE = "/hostshare/api_keys.local.json"
SO_DONE = "SAL-ORD-2026-00006"   # BUILD-92 已交付订单
SO_OPEN = "SAL-ORD-2026-00007"   # BUILD-93 待采购订单（RACK 缺 2）
MEMBER = "ligong@erpnext-poc.localhost"
MANAGER = "liugong@erpnext-poc.localhost"
SALES = "wangming@erpnext-poc.localhost"
STOCK = "zhanggong@erpnext-poc.localhost"

with open(KEYS_FILE, encoding="utf-8") as f:
    KEYS = json.load(f)

out = {"steps": []}


def step(name, ok, detail=""):
    out["steps"].append({"name": name, "ok": bool(ok), "detail": str(detail)[:420]})
    print(("PASS " if ok else "FAIL ") + name + " | " + str(detail)[:240])


def call(path, user=None):
    headers = {"Accept": "application/json"}
    if user:
        k, s = KEYS[user]
        headers["Authorization"] = "token %s:%s" % (k, s)
    req = urllib.request.Request(BASE + path, headers=headers)
    try:
        r = urllib.request.urlopen(req, timeout=40)
        return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def api(method, user=None, params=None):
    path = "/api/method/" + method
    if params:
        path += "?" + urlencode(params)
    st, body = call(path, user)
    try:
        j = json.loads(body)
    except ValueError:
        j = {}
    return st, j.get("message"), body


# ---------------------------------------------------------------- 1. H5 页面按角色渲染
st, body = call("/wecom_h5", MEMBER)
step("H5 生产人员可打开 /wecom_h5", st == 200 and "轻智造" in body, "status=%s" % st)
step("H5 首屏默认进入「我的任务」",
     'switchTab("jobs")' in body or "switchTab('jobs')" in body,
     body[body.find("switchTab(\""):body.find("switchTab(\"") + 40] if "switchTab(\"" in body else "未找到")
step("H5 含「我的生产任务」与状态/目标日/备注控件",
     "我的生产任务" in body and "production_tasks_update" in body
     and "production_status" in body and 'type="date"' in body,
     {"任务标题": "我的生产任务" in body, "更新接口": "production_tasks_update" in body})
step("H5 明确「任务完成不等于入库」的口径提示",
     "不会改变库存" in body, "不会改变库存" in body)

st, body_sales = call("/wecom_h5", SALES)
step("H5 销售角色看不到生产任务页签（按角色隐藏）",
     st == 200 and 'data-tab="jobs"' not in body_sales and 'data-tab="orders"' in body_sales,
     {"status": st, "含订单页签": 'data-tab="orders"' in body_sales,
      "含任务页签": 'data-tab="jobs"' in body_sales})
step("H5 销售角色默认进入「我的订单」",
     'switchTab("orders")' in body_sales or "switchTab('orders')" in body_sales,
     "default_tab=orders")

# ---------------------------------------------------------------- 2. 三入口共用接口
st, mine, _ = api("cn_mfg_poc.api.production_tasks_mine", MEMBER, {"limit": 50})
step("HTTP 生产人员可读本人任务", st == 200 and mine and mine.get("summary", {}).get("total", 0) >= 3,
     {"status": st, "total": (mine or {}).get("summary", {}).get("total"),
      "due_soon_days": (mine or {}).get("due_soon_days")})

st, denied_sales, _ = api("cn_mfg_poc.api.production_tasks_mine", SALES)
step("HTTP 销售角色读任务被拒（403）", st == 403, "status=%s" % st)

st, one, _ = api("cn_mfg_poc.api.orders_summary", MEMBER, {"sales_order": SO_DONE})
step("HTTP 生产人员可按单看进度（本人有任务）",
     st == 200 and one and one.get("order", {}).get("name") == SO_DONE,
     {"status": st, "so": (one or {}).get("order", {}).get("name"),
      "produced": (one or {}).get("physical", {}).get("produced_qty")})
step("HTTP 生产人员拿到的是实物完工量而非任务数",
     one and one["physical"]["produced_qty"] == 1.0 and one["progress"]["total"] == 9
     and one["physical"]["job_cards"] == 0,
     {"produced": one["physical"]["produced_qty"], "tasks": one["progress"]["total"]})

st, short, _ = api("cn_mfg_poc.api.materials_shortage", MEMBER, {"limit": 20})
step("HTTP 生产人员可读缺料（仅本人订单）",
     st == 200 and short and short.get("count", 0) >= 1
     and all(o["sales_order"] in (SO_DONE, SO_OPEN) for o in short["orders"]),
     {"count": (short or {}).get("count"),
      "orders": [o["sales_order"] for o in (short or {}).get("orders", [])]})

st, short_stock, _ = api("cn_mfg_poc.api.materials_shortage", STOCK, {"limit": 20})
step("HTTP 仓库角色可读全局缺料", st == 200 and short_stock.get("count", 0) >= 1,
     {"count": (short_stock or {}).get("count")})

st, _, _ = api("cn_mfg_poc.api.materials_shortage", SALES)
step("HTTP 销售角色读全局缺料被拒（403）", st == 403, "status=%s" % st)

# ---------------------------------------------------------------- 3. PC 页面与入口
st, body = call("/order_execution?order=" + quote(SO_OPEN), MEMBER)
step("PC 订单执行概览页可按单打开", st == 200 and "订单执行概览" in body, "status=%s" % st)

st, body = call("/cn_portal", MEMBER)
step("统一导航对生产人员保留任务与进度入口",
     st == 200 and "我的任务" in body and "订单生产进度" in body,
     {"status": st, "我的任务": "我的任务" in body, "订单生产进度": "订单生产进度" in body})

st, body = call("/cn_portal", SALES)
step("统一导航对销售保留只读进度入口、不显示我的任务",
     st == 200 and "订单生产进度" in body and "我的任务" not in body,
     {"status": st, "我的任务": "我的任务" in body})

st, body = call("/cn_portal")
step("未登录访问门户仍被拦到登录", st in (200, 302, 403) and "登录" in body or st == 302,
     "status=%s" % st)

# ---------------------------------------------------------------- 4. 四类订单入口不回退
st, body = call("/cn_portal", SALES)
step("四类订单分类入口仍在（生产/耗材/零部件/服务）",
     st == 200 and all(t in body for t in ("生产类订单", "耗材类订单", "零部件类订单", "服务类订单")),
     {"status": st, "user": "sales"})

passed = sum(1 for s in out["steps"] if s["ok"])
out["summary"] = {"passed": passed, "total": len(out["steps"]),
                  "failed": [s["name"] for s in out["steps"] if not s["ok"]]}
print("RESULT %s/%s" % (passed, len(out["steps"])))
with open("/hostshare/build93-http.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1)
