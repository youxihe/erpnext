# -*- coding: utf-8 -*-
"""BUILD-80 四类订单类型化验证（只读 + 事务回滚，不产生正式单据）。"""
import frappe
from frappe.utils import add_days, nowdate

frappe.init(site="erpnext-poc.localhost", sites_path="/workspace/development/frappe-bench/sites")
frappe.connect()
frappe.set_user("Administrator")

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("PASS " if cond else "FAIL ") + name + (" | " + str(detail) if detail else ""))


# ---------------------------------------------------------------- 字段配置
cf = frappe.get_doc("Custom Field", "Sales Order-business_type")
check("字段标签=订单类型", cf.label == "订单类型", cf.label)
check("列表可见", cf.in_list_view == 1, cf.in_list_view)
check("标准筛选可见", cf.in_standard_filter == 1, cf.in_standard_filter)
check("选项为四类且首项为空", (cf.options or "").split("\n") == ["", "生产", "耗材", "零部件", "服务"], cf.options)

# ---------------------------------------------------------------- 数据分布
rows = frappe.db.sql(
    "select name, business_type, status from `tabSales Order` order by name", as_dict=True
)
types = {r["business_type"] for r in rows}
check("样本订单覆盖四类", types == {"生产", "耗材", "零部件", "服务"}, types)
check("全部订单均有类型", all(r["business_type"] for r in rows))

# ---------------------------------------------------------------- hooks 与服务端约束
hooks = frappe.get_hooks("doc_events").get("Sales Order", {}) or {}
validators = hooks.get("validate") or []
check("doc_events.validate 已加载", "cn_mfg_poc.order_rules.validate_sales_order" in validators, validators)

stock_item = frappe.db.get_value("Item", {"is_stock_item": 1, "disabled": 0}, "name")
service_item = frappe.db.get_value("Item", {"is_stock_item": 0, "disabled": 0}, "name")
check("存在库存物料", bool(stock_item), stock_item)
check("存在服务物料", bool(service_item), service_item)

CUSTOMER = "苏州华新装备有限公司"
COMPANY = "昆山启程智能设备有限公司"


def try_so(btype, item_code):
    """尝试保存一张草稿销售订单，始终回滚，不产生数据。"""
    frappe.db.rollback()
    so = frappe.new_doc("Sales Order")
    so.customer = CUSTOMER
    so.company = COMPANY
    so.transaction_date = nowdate()
    so.delivery_date = add_days(nowdate(), 30)
    so.po_no = "BUILD80-VERIFY"
    if btype is not None:
        so.business_type = btype
    so.append("items", {
        "item_code": item_code, "qty": 1, "rate": 100,
        "delivery_date": add_days(nowdate(), 30),
    })
    err = None
    try:
        so.insert(ignore_permissions=True)
    except Exception as e:
        err = str(e)
    finally:
        frappe.db.rollback()
    return err


e1 = try_so(None, stock_item)
check("未选类型被拦截", e1 is not None and "订单类型" in e1, str(e1)[:150])
e2 = try_so("服务", stock_item)
check("服务类混入库存物料被拦截", e2 is not None and "服务类" in e2, str(e2)[:150])
e3 = try_so("耗材", service_item)
check("耗材类混入服务项被拦截", e3 is not None and "耗材类" in e3, str(e3)[:150])
e4 = try_so("生产", stock_item)
check("生产类正常单据可保存", e4 is None, str(e4)[:200])
e5 = try_so("服务", service_item)
check("服务类正常单据可保存", e5 is None, str(e5)[:200])

# ---------------------------------------------------------------- 三入口数据契约
from cn_mfg_poc import api, bot

res_api = api.my_orders(limit=10)
check("H5/PC 订单接口返回订单类型",
      bool(res_api["orders"]) and all("business_type" in o for o in res_api["orders"]),
      [o.get("business_type") for o in res_api["orders"]])
res_bot = bot._my_orders({"limit": 10})
check("Bot 订单工具返回订单类型",
      bool(res_bot["orders"]) and all("business_type" in o for o in res_bot["orders"]),
      [o.get("business_type") for o in res_bot["orders"]])

print(f"RESULT {len(PASS)}/{len(PASS) + len(FAIL)}")
if FAIL:
    raise SystemExit(2)
