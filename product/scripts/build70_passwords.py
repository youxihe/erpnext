# -*- coding: utf-8 -*-
"""BUILD-70：为体验账号批量设置同一个测试密码（仅本机执行）。

UAT-97R 之后旧共用口令已下线，且线上/本地账号改为各自独立强密码；
本脚本仅保留给「本地全新 POC 站点批量初始化」使用，密码必须由环境变量传入，
不再硬编码，避免口令再次进入 Git。
"""

import json
import os

import frappe
from frappe.utils.password import update_password

PWD = os.environ.get("BUILD70_PWD")
if not PWD or len(PWD) < 8:
    raise SystemExit("请先设置 BUILD70_PWD（≥8 位）；旧硬编码口令已在 UAT-97R 轮换下线")
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
