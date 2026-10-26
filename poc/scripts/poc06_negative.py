#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""POC-06 负面测试：验证系统在越界操作下会拦截。

覆盖：
N1 超卖：库存 40 包，卖 100 包并交货 → 应拦截（负库存禁止）
N2 越权：销售用户直连财务单据（GL Entry / Payment Entry）→ 应拦截
N3 无工单/无 BOM 直接完工入库 → 视结果记录（若放行则为 GAP）
N4 服务类物料建工单 → 应拦截（无 BOM）
N5 非法数量：数量 0 的销售订单行 → 应拦截
N6 超额收款：对已结清发票再收一次款 → 应拦截

用法：docker exec -w /workspace/development/frappe-bench poc-frappe \
        /workspace/development/frappe-bench/env/bin/python /tmp/poc06_negative.py
"""
import frappe
from frappe.utils import nowdate, add_days

frappe.init(site="erpnext-poc.localhost", sites_path="/workspace/development/frappe-bench/sites")
frappe.connect()
frappe.set_user("Administrator")

from erpnext.selling.doctype.sales_order.sales_order import make_delivery_note
from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

results = []


def record(code, title, blocked, detail):
    results.append((code, title, blocked, detail))
    print(f"  [{'拦截' if blocked else '放行'}] {code} {title}\n         -> {detail}")


def expect_blocked(code, title, fn):
    try:
        fn()
        frappe.db.rollback()
        record(code, title, False, "操作未报错，系统放行")
    except Exception as e:
        frappe.db.rollback()
        lines = [l for l in str(e).splitlines() if l.strip()]
        msg = f"{type(e).__name__}: {lines[0][:160] if lines else '(无消息)'}"
        record(code, title, True, msg)


def cleanup_so(name):
    try:
        d = frappe.get_doc("Sales Order", name)
        if d.docstatus == 1:
            d.flags.ignore_permissions = True
            d.cancel()
        elif d.docstatus == 0:
            frappe.delete_doc("Sales Order", name, force=1, ignore_permissions=True)
        frappe.db.commit()
    except Exception:
        frappe.db.rollback()


print("=" * 78)
print("POC-06 负面测试")
print("=" * 78)
print(f"库存设置 allow_negative_stock = {frappe.db.get_single_value('Stock Settings', 'allow_negative_stock')}（0=禁止负库存）\n")

# ------------------------------------------------------------------ N1 超卖
print("N1 超卖（库存 40 包，卖 100 包后交货）")


def n1():
    so = frappe.new_doc("Sales Order")
    so.customer = "苏州华新装备有限公司"
    so.company = "昆山启程智能设备有限公司"
    so.transaction_date = nowdate()
    so.delivery_date = add_days(nowdate(), 3)
    so.business_type = "耗材"
    so.po_no = "POC06-NEG-OVERSELL"
    so.append("items", {"item_code": "FILTER-KIT", "qty": 100, "rate": 80, "delivery_date": so.delivery_date})
    so.flags.ignore_permissions = True
    so.insert()
    so.submit()
    frappe.db.commit()
    dn = make_delivery_note(so.name)
    dn = frappe.get_doc(dn) if isinstance(dn, dict) else dn
    dn.flags.ignore_permissions = True
    dn.insert()
    dn.submit()          # ← 期望在这里因库存不足被拦


try:
    n1()
    frappe.db.rollback()
    record("N1", "超卖", False, "交货单提交成功（系统放行负库存）")
except Exception as e:
    frappe.db.rollback()
    record("N1", "超卖", True, f"{type(e).__name__}: {str(e).splitlines()[0][:160]}")

# 清理测试订单（若被拦，SO 可能已提交）
for r in frappe.get_all("Sales Order", filters={"po_no": "POC06-NEG-OVERSELL"}, pluck="name"):
    cleanup_so(r)

# ------------------------------------------------------------------ N2 越权
print("\nN2 越权直连（销售用户 wangming 访问财务单据）")
SALES_USER = "wangming@erpnext-poc.localhost"


def n2():
    frappe.set_user(SALES_USER)
    try:
        if frappe.has_permission("GL Entry", "read"):
            raise AssertionError("销售用户对总账凭证有读权限")
        raise frappe.PermissionError("has_permission('GL Entry','read') = False")
    finally:
        frappe.set_user("Administrator")


expect_blocked("N2-a", "读取总账凭证 GL Entry", n2)


def n2b():
    frappe.set_user(SALES_USER)
    try:
        if frappe.has_permission("Payment Entry", "read"):
            raise AssertionError("销售用户对收款单有读权限")
        raise frappe.PermissionError("has_permission('Payment Entry','read') = False")
    finally:
        frappe.set_user("Administrator")


expect_blocked("N2-b", "读取收款单 Payment Entry", n2b)


def n2c():
    frappe.set_user(SALES_USER)
    try:
        pe = frappe.get_doc(get_payment_entry("Sales Invoice", "ACC-SINV-2026-00002"))
        if pe:
            raise AssertionError("销售用户拿到了收款单草稿")
    finally:
        frappe.set_user("Administrator")


expect_blocked("N2-c", "销售用户创建收款单", n2c)


POSITIVE = []


def n2d():
    """对照项：销售用户应能读销售订单（证明权限是按角色精细控制，不是一刀切全拦）。"""
    frappe.set_user(SALES_USER)
    try:
        ok = frappe.has_permission("Sales Order", "read")
        POSITIVE.append(("N2-d", "对照：销售用户可读销售订单", ok))
        print(f"  [对照] N2-d 销售用户可读销售订单 -> {ok}")
        if not ok:
            raise AssertionError("销售用户读不到销售订单，权限收得过紧")
    finally:
        frappe.set_user("Administrator")


def n2e():
    frappe.set_user(SALES_USER)
    try:
        je = frappe.new_doc("Journal Entry")
        je.company = "昆山启程智能设备有限公司"
        je.voucher_type = "Journal Entry"
        je.posting_date = nowdate()
        je.append("accounts", {"account": "现金 - QC", "debit_in_account_currency": 100})
        je.append("accounts", {"account": "销售 - QC", "credit_in_account_currency": 100})
        je.insert()
        je.submit()
    finally:
        frappe.set_user("Administrator")


expect_blocked("N2-e", "销售用户直接做总账凭证", n2e)

# ------------------------------------------------------------------ N3 无工单完工
print("\nN3 无工单/无 BOM 直接完工入库")


def n3():
    se = frappe.new_doc("Stock Entry")
    se.purpose = "Manufacture"
    se.company = "昆山启程智能设备有限公司"
    se.set_stock_entry_type()
    se.append("items", {"item_code": "ASSY-X1", "qty": 5, "t_warehouse": "产成品仓 - QC"})
    se.flags.ignore_permissions = True
    se.insert()
    se.submit()


expect_blocked("N3", "无工单完工入库 5 台", n3)

# ------------------------------------------------------------------ N4 服务类建工单
print("\nN4 服务类物料建生产工单")


def n4():
    wo = frappe.new_doc("Work Order")
    wo.company = "昆山启程智能设备有限公司"
    wo.production_item = "INSTALL-SVC"
    wo.qty = 1
    wo.fg_warehouse = "产成品仓 - QC"
    wo.wip_warehouse = "生产在制仓 - QC"
    wo.source_warehouse = "原材料仓 - QC"
    wo.flags.ignore_permissions = True
    wo.insert()


expect_blocked("N4", "服务项 INSTALL-SVC 建工单", n4)

# ------------------------------------------------------------------ N5 非法数量
print("\nN5 非 法数量订单行（数量 0 / 负数）")


def n5():
    so = frappe.new_doc("Sales Order")
    so.customer = "苏州华新装备有限公司"
    so.company = "昆山启程智能设备有限公司"
    so.transaction_date = nowdate()
    so.delivery_date = add_days(nowdate(), 3)
    so.business_type = "生产"
    so.po_no = "POC06-NEG-QTY"
    so.append("items", {"item_code": "ASSY-X1", "qty": -1, "rate": 8800, "delivery_date": so.delivery_date})
    so.flags.ignore_permissions = True
    so.insert()
    so.submit()


expect_blocked("N5", "数量 -1 的订单行", n5)
for r in frappe.get_all("Sales Order", filters={"po_no": "POC06-NEG-QTY"}, pluck="name"):
    cleanup_so(r)

# ------------------------------------------------------------------ N6 超额收款
print("\nN6 对已结清发票超额收款")


def n6a():
    """已结清发票：get_payment_entry 不给可收金额，直接提交应被拦。"""
    pe = frappe.get_doc(get_payment_entry("Sales Invoice", "ACC-SINV-2026-00002"))
    print(f"         已结清发票生成收款单草稿：paid_amount={pe.paid_amount} 是否可提交")
    pe.reference_no = "POC06-NEG-OVERPAY"
    pe.reference_date = nowdate()
    pe.flags.ignore_permissions = True
    pe.insert()
    pe.submit()


expect_blocked("N6-a", "对已结清发票再收款", n6a)


def n6b():
    """已有收款记录的发票不允许直接取消（保护账务链条）。"""
    si = frappe.get_doc("Sales Invoice", "ACC-SINV-2026-00002")
    si.flags.ignore_permissions = True
    si.cancel()


# N6-b 为已知缺口（GAP-06-01）：本探针在事务内执行后回滚，不影响数据。
try:
    n6b()
    frappe.db.rollback()
    record("N6-b", "取消已有收款的销售发票（已知缺口 GAP-06-01）", False,
           "v16 未拦截取消动作，已回滚未影响数据；建议收紧取消权限并走红冲流程")
except Exception as e:
    frappe.db.rollback()
    lines = [l for l in str(e).splitlines() if l.strip()]
    record("N6-b", "取消已有收款的销售发票", True, f"{type(e).__name__}: {lines[0][:160] if lines else ''}")

# ------------------------------------------------------------------ 汇总
print("\n" + "=" * 78)
blocked = sum(1 for r in results if r[2])
print(f"结果：{blocked}/{len(results)} 项被系统拦截")
for code, title, ok in POSITIVE:
    print(f"  {code:<6} {'PASS' if ok else 'FAIL'}  {title}")
for code, title, ok, detail in results:
    print(f"  {code:<6} {'PASS' if ok else 'FAIL(放行)'}  {title}")
print("=" * 78)

# 彻底清理测试订单（cancel → force delete）
for name in frappe.get_all("Sales Order", filters={"po_no": ["like", "POC06-%"]}, pluck="name"):
    try:
        d = frappe.get_doc("Sales Order", name)
        if d.docstatus == 1:
            d.flags.ignore_permissions = True
            d.cancel()
        frappe.delete_doc("Sales Order", name, force=1, ignore_permissions=True)
        frappe.db.commit()
        print(f"  [清理] 删除测试订单 {name}")
    except Exception as e:
        frappe.db.rollback()
        print(f"  [清理失败] {name}: {type(e).__name__}")

# 数据未留污染检查
print("\n测试后残留检查：")
print("  订单（POC06 测试单）:", frappe.get_all("Sales Order", filters={"po_no": ["like", "POC06-%"]}, pluck="name"))
print("  Stock Entry 总数:", frappe.db.count("Stock Entry"), "（正常应为 4）")
print("  Work Order 总数:", frappe.db.count("Work Order"), "（正常应为 1）")
print("  应收余额:", frappe.db.sql("select ifnull(sum(outstanding_amount),0) from `tabSales Invoice` where docstatus=1")[0][0])
