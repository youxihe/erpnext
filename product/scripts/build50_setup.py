# -*- coding: utf-8 -*-
"""BUILD-50 机器人通道本地初始化（幂等）。

- 生成/刷新 WeCom Settings 的机器人适配器共享密钥（只在本机，不进 Git）
- 创建 bot-gateway 技术账号（无业务角色）并签发 API Token
- 补一条赵经理的企微绑定（管理类角色，用于经营摘要权限正/负例）
- 为王明补一张本人销售订单（三入口联合验收用的同一张订单）
"""

import json

import frappe
from frappe.utils import add_days, nowdate

SITE = "erpnext-poc.localhost"

frappe.init(site=SITE, sites_path="/workspace/development/frappe-bench/sites")
frappe.connect()
frappe.set_user("Administrator")

out = {}

# 1) 机器人适配器共享密钥
s = frappe.get_single("WeCom Settings")
import secrets

secret = secrets.token_hex(24)
s.bot_enabled = 1
s.bot_adapter_secret = secret
s.flags.ignore_permissions = True
s.save()
frappe.db.commit()
s.reload()
check = s.get_password("bot_adapter_secret", raise_exception=False)
out["bot_secret_roundtrip_ok"] = check == secret
out["bot_adapter_secret"] = secret
out["bot_enabled"] = s.bot_enabled

# 2) 技术账号 + API Token（无任何业务角色）
email = "bot-gateway@erpnext-poc.localhost"
if not frappe.db.exists("User", email):
    u = frappe.new_doc("User")
    u.email = email
    u.first_name = "企微机器人通道"
    u.enabled = 1
    u.user_type = "Website User"
    u.send_welcome_email = 0
    u.flags.ignore_permissions = True
    u.insert()
    frappe.db.commit()
from frappe.core.doctype.user.user import generate_keys
from frappe.utils.password import get_decrypted_password

keys = generate_keys(email)
frappe.db.commit()  # 控制台脚本不会自动提交，必须显式 commit 否则密钥回滚
stored = get_decrypted_password("User", email, "api_secret", raise_exception=False)
out["bot_gateway"] = {"user": email, **keys, "roundtrip_ok": stored == keys["api_secret"]}
out["bot_gateway_roles"] = frappe.get_roles(email)

# 3) 赵经理企微绑定
from cn_mfg_poc.wecom.sync import sync_members

out["bind_zhaojingli"] = sync_members(
    json.dumps([{"userid": "zhaojingli", "name": "赵经理", "email": "zhaojingli@erpnext-poc.localhost"}],
               ensure_ascii=False)
)

# 4) 王明本人销售订单（三入口共用同一张单据）
wangming = "wangming@erpnext-poc.localhost"
exists = frappe.db.exists("Sales Order", {"owner": wangming})
if exists:
    out["sales_order"] = {"name": exists, "created": False}
else:
    prev = frappe.session.user
    frappe.set_user(wangming)
    try:
        so = frappe.new_doc("Sales Order")
        so.customer = "苏州华新装备有限公司"
        so.transaction_date = nowdate()
        so.delivery_date = add_days(nowdate(), 14)
        so.company = "昆山启程智能设备有限公司"
        so.append("items", {"item_code": "SENSOR", "qty": 6, "rate": 300, "delivery_date": add_days(nowdate(), 14)})
        so.insert()
        frappe.db.commit()
        so.submit()
        frappe.db.commit()
        out["sales_order"] = {"name": so.name, "created": True, "status": so.status,
                              "grand_total": so.grand_total, "owner": so.owner}
    finally:
        frappe.set_user(prev)

# 5) 绑定与角色快照（供证据）
out["bindings"] = frappe.get_all(
    "WeCom User Binding", fields=["wecom_userid", "erp_user", "enabled"], order_by="wecom_userid"
)
for b in out["bindings"]:
    b["roles"] = sorted(frappe.get_roles(b["erp_user"]))

print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
