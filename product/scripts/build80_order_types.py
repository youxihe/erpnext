# -*- coding: utf-8 -*-
"""BUILD-80 四类订单类型化配置（幂等，可重复执行）。

复用 POC-04 已建的 Sales Order.business_type（生产/耗材/零部件/服务），只补产品化缺口：
1. 字段中文标签改「订单类型」，列表显示 + 标准筛选可见；
2. 四个分类入口由 /cn_portal 的 cn_portal.py 虚拟注入（Frappe v16 Workspace Link
   只支持 DocType/Page/Report，不能放带 query 的 URL，故不改 Workspace 数据）；
3. 现有订单类型保持不动，仅统计打印。

流程约束在 cn_mfg_poc/order_rules.py（hooks.doc_events），BOM 相关约束等用户确认口径后再加。
"""
import frappe

frappe.init(site="erpnext-poc.localhost", sites_path="/workspace/development/frappe-bench/sites")
frappe.connect()
frappe.set_user("Administrator")

TYPES = ["生产", "耗材", "零部件", "服务"]

# ---------------------------------------------------------------- 1. 自定义字段
cf_name = frappe.db.get_value("Custom Field", {"dt": "Sales Order", "fieldname": "business_type"}, "name")
if not cf_name:
    raise SystemExit("缺少 Sales Order.business_type，请先执行 poc/scripts/poc04_master.py")

cf = frappe.get_doc("Custom Field", cf_name)
changed = []
for field, val in [
    ("label", "订单类型"),
    ("fieldtype", "Select"),
    # 首行留空：Select 默认取第一项，留空才能真正强制用户四选一
    ("options", "\n" + "\n".join(TYPES)),
    ("insert_after", "order_type"),
    ("in_list_view", 1),
    ("in_standard_filter", 1),
    ("reqd", 0),  # 必填改由 order_rules 服务端统一校验，中文提示更清楚
]:
    if cf.get(field) != val:
        cf.set(field, val)
        changed.append(field)
if changed:
    cf.flags.ignore_permissions = True
    cf.save()
    frappe.db.commit()
    print(f"[更新] Custom Field Sales Order.business_type: {changed}")
else:
    print("[跳过] 自定义字段已是目标状态")

# ---------------------------------------------------------------- 2. 四类分类入口
print("[说明] 四个分类入口在 /cn_portal 菜单中注入（cn_portal.py），无需改 Workspace 数据")

# ---------------------------------------------------------------- 3. 打印现状
rows = frappe.db.sql(
    "select name, business_type, status, grand_total from `tabSales Order` order by name", as_dict=True
)
print("订单类型分布：")
for r in rows:
    print(f"  {r['name']} | {r['business_type']} | {r['status']} | {r['grand_total']}")
print("类型计数：", {t: sum(1 for r in rows if r["business_type"] == t) for t in TYPES})

frappe.clear_cache()
print("完成")
