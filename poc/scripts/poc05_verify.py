#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""POC-05 验证：单据链、库存台账(SLE)、总账(GL)、工单成本、Job Card 工时。"""
import frappe

frappe.init(site="erpnext-poc.localhost", sites_path="/workspace/development/frappe-bench/sites")
frappe.connect()
frappe.set_user("Administrator")

CO = "昆山启程智能设备有限公司"

print("=" * 78)
print("1. 单据链（接单 → 生产 → 交付 → 收款）")
print("=" * 78)
chain = [
    ("Sales Order", "SAL-ORD-2026-00001", "销售订单"),
    ("Production Plan", "MFG-PP-2026-00001", "生产计划"),
    ("Material Request", "MAT-MR-2026-00001", "物料申请"),
    ("Purchase Order", "PUR-ORD-2026-00001", "采购订单"),
    ("Purchase Receipt", "MAT-PRE-2026-00002", "采购入库"),
    ("Work Order", "MFG-WO-2026-00001", "生产工单"),
    ("Job Card", "PO-JOB00001", "作业卡-装配"),
    ("Job Card", "PO-JOB00002", "作业卡-检验"),
    ("Stock Entry", "MAT-STE-2026-00003", "领料"),
    ("Stock Entry", "MAT-STE-2026-00004", "完工入库"),
    ("Delivery Note", "MAT-DN-2026-00004", "交货单"),
    ("Sales Invoice", "ACC-SINV-2026-00002", "销售发票"),
    ("Payment Entry", "ACC-PAY-2026-00002", "收款单"),
]
ok = 0
for dt, name, label in chain:
    try:
        d = frappe.get_doc(dt, name)
        st = {0: "草稿", 1: "已提交", 2: "已取消"}[d.docstatus]
        extra = ""
        if dt == "Stock Entry":
            extra = f" | 类型={d.purpose} | 金额={d.total_outgoing_value or d.total_incoming_value}"
        elif dt == "Work Order":
            extra = f" | {d.production_item} x{d.qty} 产出={d.produced_qty} 状态={d.status}"
        elif dt == "Job Card":
            extra = f" | 工序={d.operation} 完成={d.total_completed_qty} 用时={d.total_time_in_mins}min 状态={d.status}"
        elif dt in ("Sales Order", "Sales Invoice", "Payment Entry", "Purchase Order", "Purchase Receipt", "Material Request", "Production Plan"):
            extra = f" | 金额={d.get('grand_total') or d.get('paid_amount') or d.get('total_qty') or '-'}"
        print(f"  OK  {label:<10} {name:<24} {st}{extra}")
        ok += 1
    except Exception as e:
        print(f"  ERR {label:<10} {name:<24} {e}")
print(f"  → {ok}/{len(chain)} 张单据存在")

print("\n" + "=" * 78)
print("2. 工单成本与工序")
print("=" * 78)
wo = frappe.get_doc("Work Order", "MFG-WO-2026-00001")
print(f"  工单 {wo.name} 产品 {wo.production_item} 数量 {wo.qty} 已产 {wo.produced_qty} 状态 {wo.status}")
mat = sum((it.get("amount") or 0) for it in wo.required_items)
print(f"  成本(按BOM单价): 材料 {mat} / 工序 {wo.total_operating_cost}  |  实际完工入库金额见完工单")
se = frappe.get_doc("Stock Entry", "MAT-STE-2026-00004")
print(f"  完工单实际金额: 耗料 {se.total_outgoing_value} → 成品 {se.total_incoming_value}（单位成本 {(se.total_incoming_value or 0)/2:.2f}）")
for op in wo.operations:
    print(f"   工序 {op.get('operation'):<6} 工位 {op.get('workstation') or '-'} 计划费用 {op.get('planned_operating_cost')} 完成数 {op.completed_qty} 用时 {op.get('actual_operation_time')}min 状态 {op.status}")
print("  领料明细:")
for it in wo.required_items:
    print(f"    {it.item_code:<10} 需求 {it.required_qty} 已领 {it.transferred_qty} 已消耗 {it.consumed_qty} 仓库 {it.source_warehouse}")

print("\n" + "=" * 78)
print("3. Job Card 工时记录")
print("=" * 78)
for jc_name in ("PO-JOB00001", "PO-JOB00002"):
    jc = frappe.get_doc("Job Card", jc_name)
    print(f"  {jc.name} 工序={jc.operation} 状态={jc.status} 完成={jc.total_completed_qty}/{jc.for_quantity} 总工时={jc.total_time_in_mins}min")
    for tl in jc.time_logs:
        print(f"     员工 {tl.employee} {tl.from_time} ~ {tl.to_time} 完成 {tl.completed_qty} 用时 {tl.time_in_mins}min")

print("\n" + "=" * 78)
print("4. 库存台账 SLE（本 POC 相关物料）")
print("=" * 78)
rows = frappe.db.sql("""
    select posting_date, posting_time, item_code, warehouse, actual_qty, qty_after_transaction,
           valuation_rate, stock_value, voucher_type, voucher_no
    from `tabStock Ledger Entry`
    where item_code in ('ASSY-X1','RACK','SENSOR','FASTENER') and is_cancelled=0
    order by item_code, timestamp(posting_date, posting_time), creation
""", as_dict=1)
for r in rows:
    print(f"  {r['item_code']:<10} {r['warehouse']:<14} 变动 {r['actual_qty']:>7} 结存 {r['qty_after_transaction']:>6} "
          f"单位成本 {r['valuation_rate'] or 0:>9.2f} | {r['voucher_type']} {r['voucher_no']}")

print("\n" + "=" * 78)
print("5. 总账 GL（销售发票 + 收款）")
print("=" * 78)
for r in frappe.db.sql("""
    select posting_date, account, debit, credit, voucher_type, voucher_no, against
    from `tabGL Entry` where voucher_no in ('ACC-SINV-2026-00002','ACC-PAY-2026-00002') and is_cancelled=0
    order by voucher_no, account
""", as_dict=1):
    print(f"  {r['voucher_no']:<20} {r['account']:<24} 借 {r['debit']:>10.2f} 贷 {r['credit']:>10.2f} ({r['voucher_type']})")

print("\n" + "=" * 78)
print("6. 财务与库存终态")
print("=" * 78)
print("  应收:", frappe.db.sql("""select sum(outstanding_amount) from `tabSales Invoice`
                                where docstatus=1 and company=%s""", (CO,))[0][0])
print("  收入:", frappe.db.sql("""select sum(credit-debit) from `tabGL Entry`
                              where account like '销售%%' and is_cancelled=0 and company=%s""", (CO,))[0][0])
print("  销货成本:", frappe.db.sql("""select sum(debit-credit) from `tabGL Entry`
                              where account like '销货成本%%' and is_cancelled=0 and company=%s""", (CO,))[0][0])
print("  库存总值:", frappe.db.sql("""select sum(stock_value) from `tabBin` where warehouse like '%%QC'""")[0][0])
print("  工单状态分布:", frappe.db.sql("""select status, count(*) c from `tabWork Order` group by status""", as_dict=1))
print("  销售订单状态:", frappe.db.sql("""select name, status, per_delivered, per_billed from `tabSales Order` order by name""", as_dict=1))
