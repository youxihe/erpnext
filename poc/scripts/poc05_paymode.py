#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""POC-05 辅助：建立中文支付方式（现金/银行转账），绑定现金/银行账户。

ERPNext 自带的 Mode of Payment 只有英文（Cash/Wire Transfer…），
中文界面下这里补齐，让收款单可以直接选「现金 / 银行转账」。
用法：docker exec -w /workspace/development/frappe-bench poc-frappe \
        /workspace/development/frappe-bench/env/bin/python /tmp/poc05_paymode.py
"""
import frappe

frappe.init(site="erpnext-poc.localhost", sites_path="/workspace/development/frappe-bench/sites")
frappe.connect()
frappe.set_user("Administrator")

COMPANY = "昆山启程智能设备有限公司"
CASH = "现金 - QC"
BANK = "银行存款 - QC"
BANK_PARENT = "银行账户 - QC"

# 「银行账户 - QC」是分组科目，不能直接用于支付方式；先建一个明细银行科目。
if not frappe.db.exists("Account", BANK):
    acc = frappe.new_doc("Account")
    acc.account_name = "银行存款"
    acc.parent_account = BANK_PARENT
    acc.company = COMPANY
    acc.account_type = "Bank"
    acc.is_group = 0
    acc.flags.ignore_permissions = True
    acc.insert()
    frappe.db.commit()
    print(f"[创建] 银行明细科目: {BANK}")

MODES = [
    ("现金", "Cash", CASH),
    ("银行转账", "Bank", BANK),
]

for name, typ, acct in MODES:
    if frappe.db.exists("Mode of Payment", name):
        print(f"[跳过] 支付方式已存在: {name}")
        continue
    mop = frappe.new_doc("Mode of Payment")
    mop.mode_of_payment = name
    mop.type = typ
    mop.enabled = 1
    mop.append("accounts", {"company": COMPANY, "default_account": acct})
    mop.flags.ignore_permissions = True
    mop.insert()
    frappe.db.commit()
    print(f"[创建] 支付方式: {name} ({typ}) 默认账户={acct}")

print("\n当前支付方式:")
for m in frappe.get_all("Mode of Payment", fields=["name", "type", "enabled"], order_by="name"):
    print(f"  {m['name']:<14} {m['type']:<10} enabled={m['enabled']}")
