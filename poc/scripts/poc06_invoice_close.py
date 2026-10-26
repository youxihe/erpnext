#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""POC-06：补齐耗材/零部件/服务三类订单的开票与收款，使四类订单均闭环。

对 SAL-ORD-2026-00002（耗材）、00003（零部件）、00004（服务）逐单：
  销售发票 → 收款单（现金），服务类不涉及库存单据。
用法：docker exec -w /workspace/development/frappe-bench poc-frappe \
        /workspace/development/frappe-bench/env/bin/python /tmp/poc06_invoice_close.py
"""
import frappe

frappe.init(site="erpnext-poc.localhost", sites_path="/workspace/development/frappe-bench/sites")
frappe.connect()
frappe.set_user("Administrator")

from erpnext.selling.doctype.sales_order.sales_order import make_sales_invoice
from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

ORDERS = [
    ("SAL-ORD-2026-00002", "耗材类", "POC06-收款-耗材"),
    ("SAL-ORD-2026-00003", "零部件类", "POC06-收款-零部件"),
    ("SAL-ORD-2026-00004", "服务类", "POC06-收款-服务"),
]


def as_doc(obj):
    return frappe.get_doc(obj) if isinstance(obj, dict) else obj


def submit(doc):
    doc.flags.ignore_permissions = True
    doc.insert()
    doc.submit()
    frappe.db.commit()
    return doc


for so_name, label, ref in ORDERS:
    so = frappe.get_doc("Sales Order", so_name)

    si_name = frappe.db.get_value("Sales Invoice Item", {"sales_order": so_name, "docstatus": 1}, "parent")
    if si_name:
        print(f"[跳过] {label} 发票已存在: {si_name}")
    else:
        si = submit(as_doc(make_sales_invoice(so_name)))
        si_name = si.name
        print(f"[开票] {label} {so_name} -> {si_name} 金额 {si.grand_total} {si.currency}")

    si = frappe.get_doc("Sales Invoice", si_name)
    pe_name = frappe.db.get_value("Payment Entry Reference", {"reference_name": si_name, "docstatus": 1}, "parent")
    if pe_name:
        print(f"[跳过] {label} 收款单已存在: {pe_name}")
    else:
        pe = as_doc(get_payment_entry("Sales Invoice", si_name))
        pe.mode_of_payment = "现金"
        pe.paid_from = "应收账款 1 - QC"
        pe.paid_to = "现金 - QC"
        pe.reference_no = ref
        pe.reference_date = frappe.utils.nowdate()
        pe = submit(pe)
        print(f"[收款] {label} {pe.name} 金额 {pe.paid_amount}")

print("\n--- 四类订单终态 ---")
for r in frappe.db.sql("""
    select so.name, so.business_type, so.grand_total, so.per_delivered, so.per_billed, so.status,
           ifnull(sum(si.grand_total),0) invoiced, ifnull(sum(si.outstanding_amount),0) outstanding
    from `tabSales Order` so
    left join `tabSales Invoice Item` sii on sii.sales_order = so.name and sii.docstatus = 1
    left join `tabSales Invoice` si on si.name = sii.parent and si.docstatus = 1
    where so.docstatus = 1
    group by so.name order by so.name
""", as_dict=1):
    print(f"  {r['name']} | {r['business_type']:<4} | 金额 {r['grand_total']:>9} | 交付 {r['per_delivered']:>5}% | "
          f"开票 {r['per_billed']:>5}% | 已开票额 {r['invoiced']:>9} | 未收 {r['outstanding']:>8} | {r['status']}")

print("\n  全部应收余额:", frappe.db.sql("select ifnull(sum(outstanding_amount),0) from `tabSales Invoice` where docstatus=1")[0][0])
print("  库存总值:", frappe.db.sql("select ifnull(sum(stock_value),0) from tabBin")[0][0])
print("  工单数量:", frappe.db.count("Work Order"))
print("  Stock Entry 数量:", frappe.db.count("Stock Entry"))
