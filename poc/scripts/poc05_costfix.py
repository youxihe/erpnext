#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""POC-05 成本修正：回滚采购入库 → 按物料参考价重做入库/领料/完工/交付/开票/收款。

根因：POC-05 Stage1 建采购订单时未传单价（rate=0），导致采购入库估值为 0，
      进而成品 ASSY-X1 完工厂成本只有 240 元（应为 1440 元）。
本脚本：撤单 → 修正 PO 单价（RACK 200 / SENSOR 300）→ 重做全链路。
用法：docker exec -w /workspace/development/frappe-bench poc-frappe \
        /workspace/development/frappe-bench/env/bin/python /tmp/poc05_costfix.py
"""
import frappe

frappe.init(site="erpnext-poc.localhost", sites_path="/workspace/development/frappe-bench/sites")
frappe.connect()
frappe.set_user("Administrator")

WO = "MFG-WO-2026-00001"
SO = "SAL-ORD-2026-00001"
QTY = 2.0
RATES = {"RACK": 200.0, "SENSOR": 300.0}

from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_receipt
from erpnext.manufacturing.doctype.work_order.work_order import make_stock_entry
from erpnext.selling.doctype.sales_order.sales_order import make_delivery_note, make_sales_invoice
from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

# ---------------------------------------------------------------- 1. 撤单（逆序）
cancel_order = [
    ("Payment Entry", "ACC-PAY-2026-00001"),
    ("Sales Invoice", "ACC-SINV-2026-00001"),
    ("Delivery Note", "MAT-DN-2026-00003"),
    ("Stock Entry", "MAT-STE-2026-00002"),
    ("Stock Entry", "MAT-STE-2026-00001"),
    ("Purchase Receipt", "MAT-PRE-2026-00001"),
]
for dt, name in cancel_order:
    if not frappe.db.exists(dt, name):
        print(f"[缺失] {dt} {name}")
        continue
    d = frappe.get_doc(dt, name)
    if d.docstatus == 1:
        d.flags.ignore_permissions = True
        d.cancel()
        frappe.db.commit()
        print(f"[撤销] {dt} {name}")
    else:
        print(f"[已撤] {dt} {name} docstatus={d.docstatus}")

# ---------------------------------------------------------------- 2. 修正采购单价
po = frappe.get_doc("Purchase Order", "PUR-ORD-2026-00001")
changed = False
for it in po.items:
    if it.item_code in RATES and abs((it.rate or 0) - RATES[it.item_code]) > 0.001:
        it.rate = RATES[it.item_code]
        it.amount = it.qty * it.rate
        changed = True
if changed:
    po.calculate_taxes_and_totals()
    po.db_update()
    for it in po.items:
        it.db_update()
    frappe.db.commit()
    print(f"[修正] 采购订单单价: " + ", ".join(f"{i.item_code}={i.rate}" for i in po.items) + f" 合计={po.grand_total}")
else:
    print(f"[跳过] 采购订单单价已正确 合计={po.grand_total}")

# ---------------------------------------------------------------- 3. 重做采购入库
pr = make_purchase_receipt("PUR-ORD-2026-00001")
pr.flags.ignore_permissions = True
pr.insert()
pr.submit()
frappe.db.commit()
print(f"[重做] 采购入库 {pr.name} 合计={pr.grand_total}")
for it in pr.items:
    print(f"   {it.item_code} {it.qty}@{it.rate} = {it.amount}")

# ---------------------------------------------------------------- 4. 重做领料 / 完工
wo = frappe.get_doc("Work Order", WO)
print(f"  工单状态={wo.status} 已产={wo.produced_qty}")

se_tr = frappe.get_doc(make_stock_entry(WO, "Material Transfer for Manufacture", QTY))
se_tr.flags.ignore_permissions = True
se_tr.insert()
se_tr.submit()
frappe.db.commit()
print(f"[重做] 领料单 {se_tr.name}")
for it in se_tr.items:
    print(f"   {it.item_code} {it.qty} 单价={it.s_warehouse and frappe.db.get_value('Bin', {'item_code': it.item_code, 'warehouse': it.s_warehouse}, 'valuation_rate') or '-'}")

se_mfg = frappe.get_doc(make_stock_entry(WO, "Manufacture", QTY))
se_mfg.flags.ignore_permissions = True
se_mfg.insert()
se_mfg.submit()
frappe.db.commit()
print(f"[重做] 完工入库 {se_mfg.name} 耗料={se_mfg.total_outgoing_value} 成品={se_mfg.total_incoming_value} 单位成本={(se_mfg.total_incoming_value or 0)/QTY:.2f}")

# ---------------------------------------------------------------- 5. 重做交付 / 开票 / 收款
dn = make_delivery_note(SO)
dn = frappe.get_doc(dn) if isinstance(dn, dict) else dn
dn.flags.ignore_permissions = True
dn.insert()
dn.submit()
frappe.db.commit()
print(f"[重做] 交货单 {dn.name} 金额={dn.grand_total}")

si = make_sales_invoice(SO)
si = frappe.get_doc(si) if isinstance(si, dict) else si
si.flags.ignore_permissions = True
si.insert()
si.submit()
frappe.db.commit()
print(f"[重做] 销售发票 {si.name} 金额={si.grand_total} 状态={si.status}")

pe = frappe.get_doc(get_payment_entry("Sales Invoice", si.name))
pe.mode_of_payment = "现金"
pe.paid_from = "应收账款 1 - QC"
pe.paid_to = "现金 - QC"
pe.reference_no = "POC05-收款-001"
pe.reference_date = frappe.utils.nowdate()
pe.flags.ignore_permissions = True
pe.insert()
pe.submit()
frappe.db.commit()
print(f"[重做] 收款单 {pe.name} 金额={pe.paid_amount} {pe.paid_from} -> {pe.paid_to}")

# ---------------------------------------------------------------- 6. 结果
wo.reload()
si.reload()
so = frappe.get_doc("Sales Order", SO)
print("\n--- 结果 ---")
print(f"  工单 {wo.name} 状态={wo.status} 产出={wo.produced_qty}")
print(f"  发票 {si.name} 状态={si.status} 未收={si.outstanding_amount}")
print(f"  订单 {so.name} 交付={so.per_delivered}% 开票={so.per_billed}% 状态={so.status}")
print(f"  成品单位成本 = {(se_mfg.total_incoming_value or 0)/QTY:.2f} 元/台，售价 8800 元/台")
print("  单据: PR=%s TRF=%s MFG=%s DN=%s SI=%s PE=%s" % (pr.name, se_tr.name, se_mfg.name, dn.name, si.name, pe.name))
