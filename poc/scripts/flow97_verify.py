# -*- coding: utf-8 -*-
"""FLOW-97 本地回归：合并采购样本 + 单订单 + 手工采购不可证实 + 权限 + 库存零变动。

用法：cd sites && ../env/bin/python /path/flow97_verify.py
前置：先跑 flow97_local_sample.py 造合并样本。
"""
import os

import frappe

SITE = os.environ.get("FLOW97_SITE", "erpnext-poc.localhost")
SITES = os.environ.get("FLOW97_SITES", "/workspace/development/frappe-bench/sites")
SO_MERGED_A = "SAL-ORD-2026-00015"
SO_MERGED_B = "SAL-ORD-2026-00016"
SO_SINGLE = "SAL-ORD-2026-00001"
SO_CONSUMABLE = "SAL-ORD-2026-00002"
PO_MERGED = "PUR-ORD-2026-00006"
PO_SINGLE = "PUR-ORD-2026-00001"
MGR = "zhaojingli@erpnext-poc.localhost"
WORKER = "ligong@erpnext-poc.localhost"

PASS = FAIL = 0
ERRORS = []


def step(name, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print("PASS %s%s" % (name, ("  | " + str(detail)) if detail else ""))
    else:
        FAIL += 1
        ERRORS.append(name)
        print("FAIL %s%s" % (name, ("  | " + str(detail)) if detail else ""))


def snapshot_stock():
    return (
        frappe.db.count("Stock Ledger Entry"),
        round(float(frappe.db.sql("select coalesce(sum(actual_qty),0) from tabBin")[0][0] or 0), 4),
        frappe.db.count("Bin"),
    )


def as_user(user, fn):
    old = frappe.session.user
    frappe.set_user(user)
    try:
        return fn()
    finally:
        frappe.set_user(old)


def expect_denied(name, fn):
    try:
        fn()
        step(name, False, "应当被拒绝但成功")
    except (frappe.PermissionError, frappe.ValidationError) as exc:
        step(name, True, "%s: %s" % (type(exc).__name__, str(exc)[:70]))
    except Exception as exc:  # noqa: BLE001
        step(name, False, "%s: %s" % (type(exc).__name__, str(exc)[:90]))


def component(trace, code):
    return next((c for c in trace["components"] if c["item_code"] == code), None)


def ensure_manual_po():
    """一张无 MR、无订单引用的手工采购订单：用来验证「来源不可证实」。"""
    exist = frappe.get_all("Purchase Order", filters={"title": "FLOW97-MANUAL", "docstatus": 1},
                           fields=["name"])
    if exist:
        return exist[0]["name"]
    po = frappe.new_doc("Purchase Order")
    po.supplier = "昆山精工零部件有限公司"
    po.company = frappe.db.get_value("Company", {}, "name")
    po.transaction_date = frappe.utils.nowdate()
    po.title = "FLOW97-MANUAL"
    po.append("items", {"item_code": "RACK", "qty": 1, "rate": 200,
                        "warehouse": "原材料仓 - QC",
                        "schedule_date": frappe.utils.nowdate()})
    po.insert()
    po.submit()
    return po.name


def main():
    global PASS, FAIL
    os.chdir(SITES)
    frappe.init(site=SITE)
    frappe.connect()
    frappe.set_user("Administrator")

    from cn_mfg_poc import procurement_trace as pt
    from cn_mfg_poc.api import CONTRACTS

    before = snapshot_stock()
    manual_po = ensure_manual_po()
    frappe.db.commit()

    # ---------- 合约登记
    for name in ("materials.trace", "purchase.options", "purchase.trace"):
        step("契约已登记 %s" % name, name in CONTRACTS)

    # ---------- 1. 合并计划识别
    ta = pt.order_material_trace(SO_MERGED_A)
    tb = pt.order_material_trace(SO_MERGED_B)
    step("合并订单 A 命中生产计划", len(ta["plans"]) == 1,
         [(p["name"], p["share"]) for p in ta["plans"]])
    step("计划标记为多订单合并", ta["plans"][0]["shared"] is True
         and SO_MERGED_B in ta["plans"][0]["other_orders"],
         ta["plans"][0]["other_orders"])
    step("本单占比 = 50%", abs(ta["plans"][0]["share"] - 0.5) < 1e-6, ta["plans"][0]["share"])
    step("B 单也命中同一计划且互相可见",
         tb["plans"][0]["name"] == ta["plans"][0]["name"]
         and SO_MERGED_A in tb["plans"][0]["other_orders"])

    # ---------- 2. 组件级数字（按计划比例估算）
    a_rack = component(ta, "RACK")
    b_rack = component(tb, "RACK")
    step("A 单 RACK 需求 2（1 台 × 2）", a_rack["required_qty"] == 2.0, a_rack["required_qty"])
    step("A 单 RACK 已申请 2（计划共享折算）", a_rack["requested_qty"] == 2.0, a_rack["requested_qty"])
    step("A 单 RACK 已下单 2", a_rack["ordered_qty"] == 2.0, a_rack["ordered_qty"])
    step("A 单 RACK 已到货 2", a_rack["received_qty"] == 2.0, a_rack["received_qty"])
    step("A 单 RACK 待收货 0", a_rack["pending_qty"] == 0.0, a_rack["pending_qty"])
    step("B 单 RACK 数字与 A 相同（同计划同比例）",
         b_rack["required_qty"] == a_rack["required_qty"]
         and b_rack["ordered_qty"] == a_rack["ordered_qty"],
         (b_rack["required_qty"], b_rack["ordered_qty"]))

    # ---------- 3. 来源标注
    step("申请行标为「计划共享」", a_rack["demand"][0]["source"] == "plan_shared"
         and "计划共享" in a_rack["demand"][0]["source_label"],
         a_rack["demand"][0]["source_label"])
    step("申请行保留计划原始数量 4", a_rack["demand"][0]["qty"] == 4.0,
         a_rack["demand"][0]["qty"])
    step("采购行标为「经采购申请行」且分摊 2",
         a_rack["purchase"][0]["source"] == "via_mr"
         and a_rack["purchase"][0]["estimated_qty"] == 2.0,
         (a_rack["purchase"][0]["source"], a_rack["purchase"][0]["estimated_qty"]))
    step("入库行同样按比例折算 2", a_rack["receipt"][0]["estimated_qty"] == 2.0,
         a_rack["receipt"][0]["estimated_qty"])

    # ---------- 4. 领料（合并工单）
    step("合并工单被识别为共享", a_rack["issued_shared"] is True)
    step("工单原始领料 4 / 本单约 2",
         a_rack["issued_qty"] == 4.0 and a_rack["issued_estimated"] == 2.0,
         (a_rack["issued_qty"], a_rack["issued_estimated"]))
    step("提示工单合并不可分单", any("共用一张工单" in w for w in a_rack["warnings"]),
         a_rack["warnings"])

    # ---------- 5. 单订单 00001（真实历史单据）
    t1 = pt.order_material_trace(SO_SINGLE)
    step("00001 命中计划但缺订单引用表",
         len(t1["plans"]) == 1 and t1["plans"][0]["refs_missing"] is True,
         [(p["name"], p.get("refs_missing")) for p in t1["plans"]])
    r1 = component(t1, "RACK")
    step("00001 RACK 需求 4 / 申请 3 / 领 4",
         r1["required_qty"] == 4.0 and r1["requested_qty"] == 3.0 and r1["issued_qty"] == 4.0,
         (r1["required_qty"], r1["requested_qty"], r1["issued_qty"]))
    step("00001 RACK 申请行是直接引用", r1["demand"][0]["source"] == "direct",
         r1["demand"][0]["source_label"])
    step("00001 入库行含已取消单据且不重复计数",
         any(r["docstatus"] == 2 for r in r1["receipt"]) and r1["received_qty"] == 3.0,
         ([(x["doc"], x["docstatus"]) for x in r1["receipt"]], r1["received_qty"]))
    f1 = component(t1, "FASTENER")
    step("00001 FASTENER 无采购但已领 8（公共库存）",
         f1["purchase"] == [] and f1["issued_qty"] == 8.0, f1["issued_qty"])

    # ---------- 6. 非生产订单不受影响
    t2 = pt.order_material_trace(SO_CONSUMABLE)
    step("耗材订单无 BOM 组件且不报错", t2["components"] == [], len(t2["components"]))

    # ---------- 7. 采购反查
    p1 = pt.purchase_trace(PO_MERGED)
    item = p1["items"][0]
    step("PO 行可反查到采购申请行", item["material_request"]["name"] == "MAT-MR-2026-00004",
         item["material_request"]["name"])
    step("PO 行反查到合并生产计划", item["plan"]["name"] == "MFG-PP-2026-00002"
         and item["plan"]["shared"] is True, item["plan"])
    step("PO 行分摊到两张订单各 2",
         sorted((o["name"], o["estimated_qty"]) for o in item["plan_orders"])
         == [(SO_MERGED_A, 2.0), (SO_MERGED_B, 2.0)],
         [(o["name"], o["estimated_qty"]) for o in item["plan_orders"]])
    step("PO 行收货 4 且在途 0",
         item["received_qty"] == 4.0 and item["pending_qty"] == 0.0,
         (item["received_qty"], item["pending_qty"]))

    p0 = pt.purchase_trace(PO_SINGLE)
    it0 = p0["items"][0]
    step("单订单 PO 反查到订单行", it0["direct_order"]["name"] == SO_SINGLE,
         it0["direct_order"]["name"])
    step("单订单 PO 反查到 MR 行", it0["material_request"]["name"] == "MAT-MR-2026-00001")
    step("单订单 PO 入库含取消单", any(r["docstatus"] == 2 for r in it0["receipts"]))

    pm = pt.purchase_trace(manual_po)
    step("手工 PO 标为来源不可证实",
         pm["items"][0]["source"] == "unverified"
         and "不可证实" in pm["items"][0]["source_label"],
         pm["items"][0]["source_label"])
    step("手工 PO 产生告警", len(pm["warnings"]) == 1, pm["warnings"])

    # ---------- 8. 权限
    expect_denied("生产人员不能查集中采购来源", lambda: as_user(WORKER, pt.po_options))
    expect_denied("生产人员不能查任意采购订单来源",
                  lambda: as_user(WORKER, lambda: pt.purchase_trace(PO_SINGLE)))
    expect_denied("生产人员不能查他人订单物料追溯",
                  lambda: as_user(WORKER, lambda: pt.order_material_trace(SO_MERGED_A)))
    step("采购/管理角色可查订单物料追溯",
         as_user(MGR, lambda: len(pt.order_material_trace(SO_MERGED_A)["components"])) == 3)

    # ---------- 9. 库存零变动（全程只读）
    after = snapshot_stock()
    step("追溯调用不产生库存过账", before == after, (before, after))

    print("SUMMARY pass=%d fail=%d" % (PASS, FAIL))
    if ERRORS:
        print("FAILED:", "; ".join(ERRORS))


if __name__ == "__main__":
    main()
