# -*- coding: utf-8 -*-
"""BUILD-10 权限负例与「我的车间任务」按人过滤验证。只读+事务回滚，不产生数据。"""
import frappe

frappe.init(site="erpnext-poc.localhost", sites_path="/workspace/development/frappe-bench/sites")
frappe.connect()

results = []


def probe(code, title, user, doctype, ptype, expect):
    frappe.set_user(user)
    try:
        got = frappe.has_permission(doctype, ptype)
    except Exception:
        got = False
    ok = (got == expect)
    results.append((code, title, user, doctype, ptype, expect, got, ok))
    frappe.set_user("Administrator")


ADMIN = "Administrator"
WANG = "wangming@erpnext-poc.localhost"   # 销售
LI = "ligong@erpnext-poc.localhost"       # 制造员工
LIU = "liugong@erpnext-poc.localhost"     # 制造经理
ZHOU = "zhoukaiji@erpnext-poc.localhost"  # 财务
CHEN = "chengong@erpnext-poc.localhost"   # 采购
ZHANG = "zhanggong@erpnext-poc.localhost" # 仓储

# --- 允许（正例） ---
probe("P1", "销售可建客户报备(Lead)", WANG, "Lead", "create", True)
probe("P2", "制造员工可读写任务单(Job Card)", LI, "Job Card", "write", True)
probe("P3", "采购可读采购订单", CHEN, "Purchase Order", "read", True)
probe("P4", "仓储可写库存过账(Stock Entry)", ZHANG, "Stock Entry", "create", True)
probe("P5", "财务可读总账(GL Entry)", ZHOU, "GL Entry", "read", True)
probe("P6", "制造经理可建生产工单", LIU, "Work Order", "create", True)

# --- 拒绝（负例） ---
probe("N1", "制造员工不得建客户报备", LI, "Lead", "create", False)
probe("N2", "制造员工不得建客户", LI, "Customer", "create", False)
probe("N3", "销售不得读生产工单", WANG, "Work Order", "read", False)
probe("N4", "销售不得读写任务单", WANG, "Job Card", "read", False)
probe("N5", "财务不得建库存过账", ZHOU, "Stock Entry", "create", False)
probe("N6", "采购不得开销售发票", CHEN, "Sales Invoice", "create", False)
probe("N7", "制造员工不得读总账", LI, "GL Entry", "read", False)
probe("N8", "仓储不得建客户报备", ZHANG, "Lead", "create", False)

print(f"{'编号':<4} {'结果':<5} {'用户':<36} {'DocType':<16} {'权限':<8} {'期望':<6} {'实际':<6}  说明")
fails = 0
for code, title, user, dt, pt, expect, got, ok in results:
    if not ok:
        fails += 1
    print(f"{code:<4} {'PASS' if ok else 'FAIL':<5} {user:<36} {dt:<16} {pt:<8} {str(expect):<6} {str(got):<6}  {title}")
print(f"\n合计 {len(results)} 项，失败 {fails} 项")

# --- 我的任务报表按人过滤 ---
from frappe.desk.query_report import run
print("\n我的车间任务（按登录人过滤）：")
for u in (LI, "zhanggong@erpnext-poc.localhost", WANG):
    frappe.set_user(u)
    try:
        r = run("我的车间任务", filters={})
        rows = [x for x in r["result"] if isinstance(x, dict)]
        who = rows[0]["employee_name"] if rows else "-"
        print(f"  {u}: {len(rows)} 行 → {set(x['job_card'] for x in rows)}（员工 {who}）")
    except Exception as e:
        print(f"  {u}: 异常 {type(e).__name__}: {str(e)[:80]}")
    frappe.set_user("Administrator")

frappe.db.rollback()
print("\n（探针均只读，已回滚）")
