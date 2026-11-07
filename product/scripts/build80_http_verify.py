# -*- coding: utf-8 -*-
"""BUILD-80：通过真实 HTTP（API Token）验证服务端四类订单约束生效。

只发一条会被拦截的非法单据，不产生任何业务数据。
密钥从本机 /hostshare/api_keys.local.json 读取，不写入仓库。
"""
import json
import urllib.error
import urllib.request

BASE = "http://localhost:8000"
KEYS_FILE = "/hostshare/api_keys.local.json"

with open(KEYS_FILE, encoding="utf-8") as f:
    keys = json.load(f)
api_key, api_secret = keys["Administrator"]
AUTH = {"Authorization": "token " + str(api_key) + ":" + str(api_secret)}


def call(path, payload=None, headers=None):
    hdr = {"Accept": "application/json"}
    if headers:
        hdr.update(headers)
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode()
        hdr["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + path, data=data, headers=hdr)
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


doc = {
    "doctype": "Sales Order",
    "customer": "苏州华新装备有限公司",
    "company": "昆山启程智能设备有限公司",
    "transaction_date": "2026-11-07",
    "delivery_date": "2026-12-07",
    "items": [{"item_code": "FLANGE-ASSY", "qty": 1, "rate": 100, "delivery_date": "2026-12-07"}],
}
status, body = call(
    "/api/method/frappe.client.insert",
    {"doc": json.dumps(doc, ensure_ascii=False)},
    AUTH,
)
print("INSERT_STATUS", status)
print("INSERT_BODY", body[:400])

ok = status >= 400 and "订单类型" in body
print("HTTP_NEGATIVE", "PASS" if ok else "FAIL")
if not ok:
    raise SystemExit(2)
