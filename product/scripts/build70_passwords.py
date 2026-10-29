# -*- coding: utf-8 -*-
"""BUILD-70：为体验账号设置统一测试密码（仅本机，密码不进 Git）。"""

import json

import frappe
from frappe.utils.password import update_password

PWD = "ErpV1@2026"
USERS = [
    "Administrator",
    "zhaojingli@erpnext-poc.localhost",
    "wangming@erpnext-poc.localhost",
    "ligong@erpnext-poc.localhost",
    "zhanggong@erpnext-poc.localhost",
    "liugong@erpnext-poc.localhost",
    "zhoukaiji@erpnext-poc.localhost",
]

frappe.init(site="erpnext-poc.localhost", sites_path="/workspace/development/frappe-bench/sites")
frappe.connect()
frappe.set_user("Administrator")

out = []
for u in USERS:
    if not frappe.db.exists("User", u):
        out.append({"user": u, "status": "missing"})
        continue
    update_password(u, PWD)
    out.append({"user": u, "status": "ok", "roles": sorted(frappe.get_roles(u))})
frappe.db.commit()
print(json.dumps({"password": PWD, "users": out}, ensure_ascii=False, indent=2))
