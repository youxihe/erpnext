# -*- coding: utf-8 -*-
"""BUILD-92 真实 HTTP 验收：门户入口、概览页、按角色金额隔离、原生单据链接。"""
import json
import re
import urllib.error
import urllib.request
from urllib.parse import urlencode

BASE = "http://localhost:8000"
KEYS_FILE = "/hostshare/api_keys.local.json"
SO = "SAL-ORD-2026-00006"
EXPECTED = {
    "material_request": "MAT-MR-2026-00002", "purchase_order": "PUR-ORD-2026-00002",
    "purchase_receipt": "MAT-PRE-2026-00016", "work_order": "MFG-WO-2026-00004",
    "delivery_note": "MAT-DN-2026-00005", "sales_invoice": "ACC-SINV-2026-00006",
    "payment_entry": "ACC-PAY-2026-00006",
}
ROLES = {
    "Administrator": {"execution": True, "mine": True, "finance": True},
    "wangming@erpnext-poc.localhost": {"execution": True, "mine": False, "finance": False},
    "zhanggong@erpnext-poc.localhost": {"execution": True, "mine": True, "finance": False},
    "liugong@erpnext-poc.localhost": {"execution": True, "mine": True, "finance": False},
    "zhoukaiji@erpnext-poc.localhost": {"execution": True, "mine": False, "finance": True},
}

with open(KEYS_FILE, encoding="utf-8") as f:
    KEYS = json.load(f)

out = {"steps": []}


def step(name, ok, detail=""):
    out["steps"].append({"name": name, "ok": bool(ok), "detail": str(detail)[:420]})
    print(("PASS " if ok else "FAIL ") + name + " | " + str(detail)[:230])


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


# ---------------------------------------------------------------- 1. 门户菜单
for user, exp in ROLES.items():
    st, body = call("/cn_portal", user)
    m = re.search(r'<script id="menu-data" type="application/json">(.*?)</script>', body, re.S)
    labels = []
    ok_json = False
    if m:
        try:
            menu = json.loads(m.group(1))
            ok_json = True
            labels = [i["label"] for mod in menu for g in mod.get("groups", []) for i in g["items"]]
        except ValueError:
            pass
    step("HTTP /cn_portal 200 [%s]" % user, st == 200 and ok_json, "status=%s" % st)
    step("订单执行概览入口可见 [%s]" % user, ("订单执行概览" in labels) == exp["execution"],
         "订单执行概览=%s" % ("订单执行概览" in labels))
    step("我的任务入口按角色 [%s]" % user, ("我的任务" in labels) == exp["mine"],
         "我的任务=%s" % ("我的任务" in labels))
    # 「四类订单」是分组名，分类入口的实际菜单项是「生产类订单」等四项
    step("BUILD-91/80 入口未回退 [%s]" % user,
         "订单生产进度" in labels
         and ("生产类订单" in labels or "客户与销售" not in body),
         "订单生产进度=%s 生产类订单=%s" % ("订单生产进度" in labels, "生产类订单" in labels))

# ---------------------------------------------------------------- 2. 概览页
for user in ROLES:
    st, body = call("/order_execution", user)
    step("HTTP /order_execution 200 [%s]" % user,
         st == 200 and "订单执行概览" in body and "物料覆盖" in body,
         "status=%s len=%d" % (st, len(body)))

# ---------------------------------------------------------------- 3. 概览 API 按角色
for user, exp in ROLES.items():
    st, r, body = api("cn_mfg_poc.order_execution.order_summary", user, {"sales_order": SO})
    ok = (st == 200 and r and r["order"]["name"] == SO
          and r["finance_visible"] == exp["finance"])
    if ok and not exp["finance"]:
        ok = (r["finance"] is None and r["order"]["grand_total"] is None
              and all(i["rate"] is None for i in r["items"])
              and all("grand_total" not in d for grp in r["documents"].values() for d in grp))
    if ok and exp["finance"]:
        ok = r["finance"] and r["finance"]["paid_amount"] == 5000
    step("HTTP 概览金额按角色隔离 [%s]" % user, ok,
         {"status": st, "finance_visible": r.get("finance_visible") if r else None,
          "expected": exp["finance"]})

st, r, body = api("cn_mfg_poc.order_execution.order_summary", None, {"sales_order": SO})
step("未登录不能读订单执行概览", st in (401, 403), "status=%s" % st)

st, r, body = api("cn_mfg_poc.order_execution.order_summary", "Administrator", {"sales_order": SO})
all_urls = [d["url"] for grp in r["documents"].values() for d in grp] if r else []
step("单据链每个原生单据都有可点击 Desk 链接", len(all_urls) >= 8 and all(
    u.startswith("/desk/") for u in all_urls), "%d 个链接" % len(all_urls))

for key, name in EXPECTED.items():
    step("单据链包含 %s" % name, any(name in u for u in all_urls), name)

# ---------------------------------------------------------------- 4. 原生单据链接可打开
for path in ["/desk/sales-order/" + SO,
             "/desk/delivery-note/" + EXPECTED["delivery_note"],
             "/desk/work-order/" + EXPECTED["work_order"],
             "/desk/bom/BOM-ASSY-X1-002"]:
    st, body = call(path, "Administrator")
    step("原生单据链接 HTTP 200 %s" % path.rsplit("/", 1)[-1], st == 200, "status=%s" % st)

# ---------------------------------------------------------------- 5. 缺料契约 HTTP
st, r, body = api("cn_mfg_poc.order_execution.materials_shortage", "Administrator", {"limit": 20})
step("materials.shortage HTTP 可用", st == 200 and r and "shortage_formula" in r,
     {"count": r.get("count") if r else None})

out["summary"] = {"passed": sum(1 for s in out["steps"] if s["ok"]), "total": len(out["steps"])}
with open("/hostshare/build92-http.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1, default=str)
print("RESULT %d/%d" % (out["summary"]["passed"], out["summary"]["total"]))
