# -*- coding: utf-8 -*-
"""BUILD-91 真实 HTTP 验证：门户菜单、生产进度页、受控 API 权限、幂等。

在容器内执行（/hostshare 挂载），密钥读 /hostshare/api_keys.local.json，不进仓库。
结果写 /hostshare/build91-http.json。
"""
import json
import re
import urllib.error
import urllib.request

BASE = "http://localhost:8000"
KEYS_FILE = "/hostshare/api_keys.local.json"
SO = "SAL-ORD-2026-00005"
USERS = {
    "Administrator": True,
    "liugong@erpnext-poc.localhost": True,   # Manufacturing Manager
    "ligong@erpnext-poc.localhost": True,    # Manufacturing User
    "wangming@erpnext-poc.localhost": False,  # 纯销售角色：不该看到「我的任务」
}
# (我的任务, 订单生产进度) 期望；销售角色只有只读入口
EXPECT = {u: (staff, True) for u, staff in USERS.items()}
with open(KEYS_FILE, encoding="utf-8") as f:
    KEYS = json.load(f)

out = {"steps": [], "ids": {}}


def step(name, ok, detail=""):
    out["steps"].append({"name": name, "ok": bool(ok), "detail": str(detail)[:420]})
    print(("PASS " if ok else "FAIL ") + name + " | " + str(detail)[:230])


def call(path, user=None, payload=None):
    headers = {"Accept": "application/json"}
    if user:
        k, s = KEYS[user]
        headers["Authorization"] = "token %s:%s" % (k, s)
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + path, data=data, headers=headers)
    try:
        resp = urllib.request.urlopen(req, timeout=40)
        return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def api(method, user=None, params=None, payload=None):
    path = "/api/method/" + method
    if params:
        from urllib.parse import urlencode
        path += "?" + urlencode(params)
    st, body = call(path, user, payload)
    try:
        j = json.loads(body)
    except ValueError:
        j = {}
    return st, j.get("message"), body


# ---------------------------------------------------------------- 1. 门户菜单按角色注入
for user, staff in USERS.items():
    st, body = call("/cn_portal", user)
    m = re.search(r'<script id="menu-data" type="application/json">(.*?)</script>', body, re.S)
    ok_json = False
    mine = order = order_types = False
    selling_visible = False
    labels = []
    if m:
        try:
            menu = json.loads(m.group(1))
            ok_json = True
            labels = [i["label"] for mod in menu for g in mod.get("groups", []) for i in g["items"]]
            mine = "我的任务" in labels
            order = "订单生产进度" in labels
            selling = next((x for x in menu if x["label"] == "客户与销售"), None)
            selling_visible = selling is not None
            order_types = selling_visible and any(
                g["label"] == "四类订单" for g in selling.get("groups", []))
        except ValueError:
            pass
    step("HTTP /cn_portal 200 且菜单可解析 [%s]" % user, st == 200 and ok_json, "status=%s" % st)
    exp_mine, exp_order = EXPECT[user]
    step("生产进度菜单按角色可见 [%s]" % user, mine == exp_mine and order == exp_order,
         "我的任务=%s(期望%s) 订单生产进度=%s(期望%s)" % (mine, exp_mine, order, exp_order))
    # 生产角色看不到「客户与销售」工作台时，四类订单组自然不会出现，不算回退。
    step("四类订单入口未回退 [%s]" % user, (not selling_visible) or order_types,
         "客户与销售可见=%s 四类订单=%s" % (selling_visible, order_types))

# ---------------------------------------------------------------- 2. 生产进度页
for user in USERS:
    st, body = call("/production_board?view=order", user)
    step("HTTP /production_board 200 [%s]" % user, st == 200 and "生产进度" in body,
         "status=%s len=%d" % (st, len(body)))

# ---------------------------------------------------------------- 3. 受控 API
st, mine, body = api("cn_mfg_poc.production.tasks_mine", "ligong@erpnext-poc.localhost", {"limit": 100})
step("李工 HTTP 只见本人任务", st == 200 and mine and all(
    t["production_owner"] == "ligong@erpnext-poc.localhost" for t in mine["tasks"]),
    "%s 项" % (len(mine["tasks"]) if mine else "N/A"))

st, orders, body = api("cn_mfg_poc.production.my_production_orders",
                       "wangming@erpnext-poc.localhost", {"limit": 100})
step("销售角色可见生产订单下拉", st == 200 and orders and any(
    o["name"] == SO for o in orders["orders"]), "%s 张" % (len(orders["orders"]) if orders else "N/A"))

st, prog, body = api("cn_mfg_poc.production.order_progress",
                     "wangming@erpnext-poc.localhost", {"sales_order": SO})
step("销售角色可读订单生产进度（只读）",
     st == 200 and prog and prog["started"] and prog["total"] == 9,
     {"project": prog.get("project") if prog else None, "total": prog.get("total") if prog else None})

st, msg, body = api("cn_mfg_poc.production.tasks_update", "wangming@erpnext-poc.localhost",
                    payload={"task": (mine or {}).get("tasks", [{}])[0].get("name"),
                             "production_status": "已完成"})
step("销售角色不能更新生产任务（HTTP 拒绝）", st >= 400, "status=%s" % st)

st, msg, body = api("cn_mfg_poc.production.create_project", "wangming@erpnext-poc.localhost",
                    payload={"sales_order": SO})
step("销售角色不能创建生产进度项目（HTTP 拒绝）", st >= 400, "status=%s" % st)

st, msg, body = api("cn_mfg_poc.production.tasks_mine", None, {"limit": 5})
step("未登录不能读生产任务", st in (401, 403), "status=%s" % st)

# ---------------------------------------------------------------- 4. 幂等 + 库存解耦（HTTP 触发）
st, before, body = api("frappe.client.get_count", "Administrator",
                       {"doctype": "Stock Ledger Entry"})
st2, replay, body2 = api("cn_mfg_poc.production.create_project", "liugong@erpnext-poc.localhost",
                         payload={"sales_order": SO})
st3, after, body3 = api("frappe.client.get_count", "Administrator",
                        {"doctype": "Stock Ledger Entry"})
step("HTTP 重复创建返回原项目且任务数不变",
     st2 == 200 and replay and replay.get("replayed") and len(replay.get("tasks", [])) == 9,
     {"project": replay.get("project") if replay else None, "tasks": len(replay.get("tasks", [])) if replay else 0})
step("HTTP 全程库存 SLE 不变", isinstance(before, int) and before == after,
     "%s -> %s" % (before, after))
out["ids"]["project"] = replay.get("project") if replay else None

out["summary"] = {
    "passed": sum(1 for s in out["steps"] if s["ok"]),
    "total": len(out["steps"]),
}
with open("/hostshare/build91-http.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1, default=str)
print("RESULT %d/%d" % (out["summary"]["passed"], out["summary"]["total"]))
