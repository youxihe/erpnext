# -*- coding: utf-8 -*-
"""POC-04 四类订单与库存验证（幂等）。

1) 初始化库存（Stock Reconciliation / Opening Stock）：过滤耗材包、替换法兰组件。
2) 创建四类销售订单各一张并提交：生产 / 耗材 / 零部件 / 服务。
3) 耗材、零部件分别建交货单并 submit，验证真实库存下降；服务类不建任何库存/工单。

运行：
  docker cp poc04_orders.py poc-frappe:/tmp/poc04_orders.py
  docker exec -w /workspace/development/frappe-bench poc-frappe \\
      /workspace/development/frappe-bench/env/bin/python /tmp/poc04_orders.py
"""
import frappe
from datetime import date, timedelta

frappe.init(site="erpnext-poc.localhost",
            sites_path="/workspace/development/frappe-bench/sites")
frappe.connect()
frappe.set_user("Administrator")

COMPANY = "昆山启程智能设备有限公司"
CUST = "苏州华新装备有限公司"
SUPP = "昆山精工零部件有限公司"


def wh(name):
    return frappe.db.get_value("Warehouse",
                               {"warehouse_name": name, "company": COMPANY}, "name")


def qty_of(item):
    return frappe.db.get_value("Bin", {"item_code": item, "warehouse": wh("贸易品仓")},
                               "actual_qty") or 0


def make_so(code, title, items, btype):
    """items: list of (item_code, qty, rate). 返回 SO name 或 None(已存在)。"""
    existing = frappe.db.get_value("Sales Order",
                                   {"customer": CUST, "po_no": code}, "name")
    if existing:
        print(f"  [跳过] 销售订单已存在: {existing} ({title})")
        return existing
    so = frappe.new_doc("Sales Order")
    so.customer = CUST
    so.company = COMPANY
    so.transaction_date = date.today()
    so.delivery_date = date.today() + timedelta(days=30)
    so.po_no = code
    so.business_type = btype
    for item_code, qty, rate in items:
        so.append("items", {
            "item_code": item_code,
            "qty": qty,
            "rate": rate,
            "delivery_date": date.today() + timedelta(days=30),
        })
    so.insert(ignore_permissions=True)
    so.submit()
    frappe.db.commit()
    print(f"  [创建] 销售订单 {so.name} ({title}) 业务类型={btype}")
    return so.name


def make_dn(so_name, title):
    if frappe.db.exists("Delivery Note", {"against_sales_order": so_name}):
        dn = frappe.db.get_value("Delivery Note", {"against_sales_order": so_name}, "name")
        print(f"  [跳过] 交货单已存在: {dn} ({title})")
        return dn
    dn = frappe.new_doc("Delivery Note")
    dn.customer = CUST
    dn.company = COMPANY
    dn.posting_date = date.today()
    so = frappe.get_doc("Sales Order", so_name)
    for it in so.items:
        dn.append("items", {
            "item_code": it.item_code,
            "qty": it.qty,
            "against_sales_order": so_name,
            "so_detail": it.name,
            "warehouse": it.warehouse,
            "rate": it.rate,
        })
    dn.insert(ignore_permissions=True)
    dn.submit()
    frappe.db.commit()
    print(f"  [创建] 交货单 {dn.name} ({title})")
    return dn.name


print("=== A. 初始化库存（Stock Reconciliation）===")
trade = wh("贸易品仓")
for item_code, qty, rate in [("FILTER-KIT", 50, 50), ("FLANGE-ASSY", 8, 120)]:
    marker = f"POC04-INIT-{item_code}"
    # 幂等：只要该物料在贸易品仓已有库存台账(Bin)，即视为已初始化，绝不重复设置数量
    if frappe.db.exists("Bin", {"item_code": item_code, "warehouse": trade}):
        print(f"  [跳过] 库存已初始化(Bin 存在): {item_code} 现量="
              f"{frappe.db.get_value('Bin', {'item_code': item_code, 'warehouse': trade}, 'actual_qty')}")
        continue
    sr = frappe.new_doc("Stock Reconciliation")
    sr.purpose = "Stock Reconciliation"
    sr.company = COMPANY
    sr.posting_date = date.today()
    sr.remarks = marker
    # 站点首笔无 SLE 会被视作 Opening，差异科目须为资产负债表科目
    sr.expense_account = "临时开账 - QC"
    sr.append("items", {"item_code": item_code, "qty": qty,
                        "valuation_rate": rate, "warehouse": trade})
    sr.insert(ignore_permissions=True)
    sr.submit()
    frappe.db.commit()
    print(f"  [创建] 库存初始化 {sr.name}: {item_code} x{qty} @ {trade}")

print("初始化后库存(贸易品仓): 过滤耗材包=", qty_of("FILTER-KIT"),
      " 替换法兰组件=", qty_of("FLANGE-ASSY"))

print("\n=== B. 四类销售订单 ===")
so_prod = make_so("POC04-PROD", "生产类-设备装配X1",
                  [("ASSY-X1", 2, 8800)], "生产")
so_cons = make_so("POC04-CONS", "耗材类-过滤耗材包",
                  [("FILTER-KIT", 10, 80)], "耗材")
so_part = make_so("POC04-PART", "零部件类-替换法兰组件",
                  [("FLANGE-ASSY", 5, 150)], "零部件")
so_svc = make_so("POC04-SVC", "服务类-设备安装服务",
                 [("INSTALL-SVC", 1, 800)], "服务")

print("\n=== C. 库存类交货（验证真实库存下降）===")
dn_cons = make_dn(so_cons, "耗材类交货")
dn_part = make_dn(so_part, "零部件类交货")
print("交货后库存(贸易品仓): 过滤耗材包=", qty_of("FILTER-KIT"),
      "(应=40) 替换法兰组件=", qty_of("FLANGE-ASSY"), "(应=3)")

print("\n=== D. 服务类：不建库存/工单 ===")
wo_svc = frappe.db.count("Work Order", {"production_item": "INSTALL-SVC"}) if \
    frappe.db.exists("Work Order") else 0
se_svc = frappe.db.sql(
    "SELECT COUNT(*) c FROM `tabStock Entry` se JOIN `tabStock Entry Detail` sed "
    "ON sed.parent=se.name WHERE sed.item_code='INSTALL-SVC'", as_dict=True)
print(f"  服务物料 INSTALL-SVC 的 Work Order 数={wo_svc}（应=0）")
print(f"  服务物料 INSTALL-SVC 的 Stock Entry 数={se_svc[0].c if se_svc else 0}（应=0）")

print("\n=== POC-04 订单与验证完成 ===")
print("生产 SO:", so_prod, "| 耗材 SO:", so_cons, "| 零部件 SO:", so_part, "| 服务 SO:", so_svc)
print("耗材 DN:", dn_cons, "| 零部件 DN:", dn_part)
