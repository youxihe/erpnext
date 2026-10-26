#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""POC-05 Stage 4：交付与收款 —— Delivery Note(2台) → Sales Invoice → Payment Entry。

幂等：按 sales_order 引用查找已提交单据，存在则跳过。
用法：docker exec -w /workspace/development/frappe-bench poc-frappe \
        /workspace/development/frappe-bench/env/bin/python /tmp/poc05_stage4.py
"""
import frappe

SITE = "erpnext-poc.localhost"
frappe.init(site=SITE, sites_path="/workspace/development/frappe-bench/sites")
frappe.connect()
frappe.set_user("Administrator")

SO = "SAL-ORD-2026-00001"
QTY = 2.0

from erpnext.selling.doctype.sales_order.sales_order import make_delivery_note, make_sales_invoice
from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry


def as_doc(obj):
    return frappe.get_doc(obj) if isinstance(obj, dict) else obj


def find_submitted(doctype, **filters):
    rows = frappe.get_all(doctype, filters=dict(filters, docstatus=1), pluck="name", order_by="creation")
    return rows[0] if rows else None


def submit(doc):
    doc.flags.ignore_permissions = True
    doc.insert()
    doc.submit()
    frappe.db.commit()
    return doc


# ---------------------------------------------------------------- 1. 交货
dn_name = frappe.db.get_value("Delivery Note Item", {"against_sales_order": SO, "docstatus": 1}, "parent")
if dn_name:
    print(f"[跳过] 交货单已存在: {dn_name}")
else:
    dn = as_doc(make_delivery_note(SO))
    for it in dn.items:
        it.qty = min(it.qty, QTY - frappe.db.get_value("Sales Order Item", it.so_detail, "delivered_qty") or it.qty)
    dn = submit(dn)
    dn_name = dn.name
    print(f"[创建] 交货单(Delivery Note): {dn_name}")
    for it in dn.items:
        print(f"   {it.item_code} {it.qty} {it.rate} 元 仓库={it.warehouse if hasattr(it,'warehouse') else '-'}")

dn = frappe.get_doc("Delivery Note", dn_name)
print(f"  交货单状态 docstatus={dn.docstatus} 合计 {dn.grand_total} {dn.currency}")

# ---------------------------------------------------------------- 2. 开票
si_name = frappe.db.get_value("Sales Invoice Item", {"sales_order": SO, "docstatus": 1}, "parent")
if si_name:
    print(f"[跳过] 销售发票已存在: {si_name}")
else:
    si = as_doc(make_sales_invoice(SO))
    si = submit(si)
    si_name = si.name
    print(f"[创建] 销售发票(Sales Invoice): {si_name} 金额 {si.grand_total} {si.currency} 状态 {si.status}")

si = frappe.get_doc("Sales Invoice", si_name)
print(f"  发票 未收金额 outstanding={si.outstanding_amount} 已收={si.total_advance or 0}")

# ---------------------------------------------------------------- 3. 收款
pe_name = frappe.db.get_value("Payment Entry Reference", {"reference_name": si_name, "docstatus": 1}, "parent")
if pe_name:
    print(f"[跳过] 收款单已存在: {pe_name}")
else:
    pe = as_doc(get_payment_entry("Sales Invoice", si_name))
    pe.mode_of_payment = "现金"
    pe.paid_from = "应收账款 1 - QC"   # 客户明细应收科目
    pe.paid_to = "现金 - QC"          # 中文支付方式「现金」绑定账户
    pe.reference_no = "POC05-收款-001"
    pe.reference_date = frappe.utils.nowdate()
    pe = submit(pe)
    pe_name = pe.name
    print(f"[创建] 收款单(Payment Entry): {pe_name} 金额 {pe.paid_amount} {pe.paid_from} -> {pe.paid_to}")

si.reload()
so = frappe.get_doc("Sales Order", SO)
print("\n--- 销售订单终态 ---")
print(f"  {SO} 总额 {so.grand_total} 已交付 {so.per_delivered}% 已开票 {so.per_billed}% 状态 {so.status}")
for it in so.items:
    print(f"   {it.item_code}: 订购 {it.qty} 已交付 {it.delivered_qty} 已开票 {it.billed_amt}")

print("\n--- 库存 ---")
for b in frappe.db.sql("""select item_code, warehouse, actual_qty, stock_uom from tabBin
                          where actual_qty != 0 order by item_code, warehouse""", as_dict=1):
    print(f"  {b['item_code']:<12} {b['warehouse']:<18} {b['actual_qty']:>8} {b['stock_uom']}")

print("\n--- 应收 ---")
for r in frappe.db.sql("""select name, customer, grand_total, outstanding_amount, status
                          from `tabSales Invoice` where docstatus=1 order by name""", as_dict=1):
    print(f"  {r['name']} {r['customer']} 金额 {r['grand_total']} 未收 {r['outstanding_amount']} 状态 {r['status']}")

print("\n--- 单据链 ---")
print(f"  销售订单 {SO} -> 交货单 {dn_name} / 发票 {si_name} / 收款 {pe_name}")
print(f"  生产计划 MFG-PP-2026-00001 -> 工单 MFG-WO-2026-00001 -> 领料 MAT-STE-2026-00001 -> 完工 MAT-STE-2026-00002")
