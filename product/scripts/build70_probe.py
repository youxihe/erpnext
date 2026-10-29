# -*- coding: utf-8 -*-
"""诊断：账号停用后企微免登是否仍能建立会话。"""
import json
import urllib.error
import urllib.parse
import urllib.request

import frappe

BASE = "http://127.0.0.1:8000"
EMAIL = "ligong@erpnext-poc.localhost"

frappe.init(site="erpnext-poc.localhost", sites_path="/workspace/development/frappe-bench/sites")
frappe.connect()
frappe.set_user("Administrator")
frappe.db.sql("update `tabUser` set enabled=0 where name=%s", EMAIL)
frappe.db.commit()
frappe.clear_cache()
print("db enabled =", frappe.db.sql("select enabled from `tabUser` where name=%s", EMAIL))
print("get_value  =", frappe.db.get_value("User", EMAIL, "enabled"))
print("binding    =", frappe.db.get_value("WeCom User Binding", {"wecom_userid": "ligong"}, ["erp_user", "enabled"], as_dict=True))


def get(p):
    try:
        r = urllib.request.urlopen(urllib.parse.urljoin(BASE, p), timeout=30)
        return r.status, r.read().decode("utf-8", "replace"), r.headers.get("Set-Cookie") or ""
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace"), (e.headers.get("Set-Cookie") or "")


for i in range(3):
    st, txt, _ = get("/api/method/cn_mfg_poc.wecom.oauth.mock_authorize?wecom_userid=ligong")
    cb = json.loads(txt)["message"]["mock_callback_url"]
    st2, txt2, sc2 = get(cb)
    print(f"round{i} callback status={st2} has_sid={'sid=' in sc2} body={txt2[:150]!r}")

frappe.db.sql("update `tabUser` set enabled=1 where name=%s", EMAIL)
frappe.db.commit()
frappe.clear_cache()
print("restored")
