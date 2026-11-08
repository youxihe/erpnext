# -*- coding: utf-8 -*-
"""FLOW-97 本地 POC 合并采购样本（仅本地 erpnext-poc.localhost，不碰线上）。

链路：2 张 SO → 1 张合并 Production Plan（Consolidate Sales Order Items）
     → 2 张 MR（原生按 Sales Order 分组）→ 1 张 PO（两个 MR 行拉进同一 PO）
     → 1 张 PR（部分行收货）→ 2 张 WO → 领料/完工。

幂等：已存在同标记样本时直接复用并打印。
"""
import os

import frappe
from frappe.utils import add_days, nowdate

SITE = os.environ.get("FLOW97_SITE", "erpnext-poc.localhost")
SITES = os.environ.get("FLOW97_SITES", "/workspace/development/frappe-bench/sites")
MARK = "FLOW97-MERGE"
CUSTOMER = "苏州华新装备有限公司"
SUPPLIER = "昆山精工零部件有限公司"


def log(*a):
    print(*a)


def _cancel_delete(doctype, names):
    for n in names:
        try:
            d = frappe.get_doc(doctype, n)
            if d.docstatus == 1:
                d.cancel()
            frappe.delete_doc(doctype, n, force=1, ignore_permissions=True)
        except Exception as exc:  # noqa: BLE001
            log("  skip", doctype, n, type(exc).__name__, str(exc)[:80])


def wipe():
    """清掉上一轮样本（仅本地 POC，按标记/计划链接定位，不动其它单据）。

    合并计划下 MR/PO 行的 sales_order 可能为空（原生按计划合并），
    因此必须同时用 production_plan / material_request / purchase_order 反查。
    """
    sos = frappe.get_all("Sales Order", filters={"po_no": ["like", MARK + "%"]}, pluck="name")
    pps = sorted({r["parent"] for r in frappe.get_all(
        "Production Plan Item Reference", filters={"sales_order": ["in", sos or ["__x__"]]},
        fields=["parent"])})
    mrs = sorted({r["parent"] for r in frappe.get_all(
        "Material Request Item", filters={"sales_order": ["in", sos or ["__x__"]]},
        fields=["parent"])}
        | {r["parent"] for r in frappe.get_all(
            "Material Request Item", filters={"production_plan": ["in", pps or ["__x__"]]},
            fields=["parent"])})
    wos = sorted(set(frappe.get_all("Work Order", filters={"sales_order": ["in", sos or ["__x__"]]},
                                    pluck="name"))
                 | set(frappe.get_all("Work Order",
                                      filters={"production_plan": ["in", pps or ["__x__"]]},
                                      pluck="name")))
    ses = sorted(frappe.get_all("Stock Entry", filters={"work_order": ["in", wos or ["__x__"]]},
                                pluck="name")) if wos else []
    pos = sorted({r["parent"] for r in frappe.get_all(
        "Purchase Order Item", filters={"sales_order": ["in", sos or ["__x__"]]}, fields=["parent"])}
        | {r["parent"] for r in frappe.get_all(
            "Purchase Order Item", filters={"material_request": ["in", mrs or ["__x__"]]},
            fields=["parent"])})
    prs = sorted({r["parent"] for r in frappe.get_all(
        "Purchase Receipt Item", filters={"sales_order": ["in", sos or ["__x__"]]},
        fields=["parent"])}
        | {r["parent"] for r in frappe.get_all(
            "Purchase Receipt Item", filters={"purchase_order": ["in", pos or ["__x__"]]},
            fields=["parent"])})
    if not sos and not pps:
        return
    _cancel_delete("Stock Entry", ses)
    _cancel_delete("Work Order", wos)
    _cancel_delete("Purchase Receipt", prs)
    _cancel_delete("Purchase Order", pos)
    _cancel_delete("Material Request", mrs)
    _cancel_delete("Production Plan", pps)
    _cancel_delete("Sales Order", sos)
    log("wiped previous sample:", len(sos), "SO /", len(pps), "PP")


def make_so(tag):
    so = frappe.new_doc("Sales Order")
    so.customer = CUSTOMER
    so.company = frappe.db.get_value("Company", {}, "name")
    so.transaction_date = nowdate()
    so.delivery_date = add_days(nowdate(), 10)
    so.business_type = "生产"
    so.po_no = "%s-%s" % (MARK, tag)
    so.append("items", {"item_code": "ASSY-X1", "qty": 1, "rate": 1800,
                        "delivery_date": add_days(nowdate(), 10)})
    so.insert()
    so.submit()
    return so


def main():
    os.chdir(SITES)
    frappe.init(site=SITE)
    frappe.connect()
    frappe.set_user("Administrator")
    wipe()

    exist = frappe.get_all("Sales Order", filters={"po_no": ["like", MARK + "%"]},
                           fields=["name"], order_by="name asc")
    if len(exist) >= 2:
        log("REUSE sales orders:", [r["name"] for r in exist])
        sos = [frappe.get_doc("Sales Order", r["name"]) for r in exist[:2]]
    else:
        sos = [make_so("A"), make_so("B")]
        log("CREATED sales orders:", [s.name for s in sos])

    pp_name = frappe.db.get_value("Production Plan",
                                  {"sales_orders.sales_order": sos[0].name,
                                   "docstatus": ["<", 2]}, "name")
    if not pp_name:
        from erpnext.manufacturing.doctype.production_plan.production_plan import (
            get_items_for_material_requests)
        pp = frappe.new_doc("Production Plan")
        pp.company = frappe.db.get_value("Company", {}, "name")
        pp.get_items_from = "Sales Order"
        pp.posting_date = nowdate()
        pp.combine_items = 1
        for so in sos:
            pp.append("sales_orders", {
                "sales_order": so.name, "sales_order_date": so.transaction_date,
                "customer": so.customer, "grand_total": so.grand_total, "status": so.status})
        pp.get_items()
        mr_rows = get_items_for_material_requests(pp.as_json(), warehouses=[])
        pp.set("mr_items", mr_rows)
        pp.insert()
        pp.submit()
        pp_name = pp.name
        log("CREATED plan:", pp_name,
            "refs=", [(r.sales_order, r.sales_order_item, r.qty) for r in pp.prod_plan_references],
            "po_items=", [(i.item_code, i.planned_qty, i.sales_order) for i in pp.po_items],
            "mr_items=", [(i.item_code, i.quantity, i.sales_order) for i in pp.mr_items])
    else:
        log("REUSE plan:", pp_name)

    pp = frappe.get_doc("Production Plan", pp_name)
    mrs = frappe.get_all("Material Request Item", filters={"production_plan": pp_name},
                         fields=["parent"], distinct=True)
    mr_names = sorted({r["parent"] for r in mrs})
    if not mr_names:
        pp.make_material_request()
        mr_names = sorted({r["parent"] for r in frappe.get_all(
            "Material Request Item", filters={"production_plan": pp_name},
            fields=["parent"])})
        for n in mr_names:
            d = frappe.get_doc("Material Request", n)
            if d.docstatus == 0:
                d.submit()
        log("CREATED MRs:", mr_names)
    else:
        log("REUSE MRs:", mr_names)

    mr_items = frappe.get_all(
        "Material Request Item", filters={"parent": ["in", mr_names]},
        fields=["name", "parent", "item_code", "qty", "sales_order", "warehouse"],
        order_by="parent asc, idx asc")
    log("MR items:", [(r["parent"], r["item_code"], r["qty"], r["sales_order"]) for r in mr_items])

    po_name = frappe.db.get_value("Purchase Order Item", {"sales_order": sos[0].name}, "parent")
    if not po_name:
        po = frappe.new_doc("Purchase Order")
        po.supplier = SUPPLIER
        po.company = frappe.db.get_value("Company", {}, "name")
        po.transaction_date = nowdate()
        for r in mr_items:
            po.append("items", {
                "item_code": r["item_code"], "qty": r["qty"], "rate": 200,
                "warehouse": r["warehouse"],
                "schedule_date": add_days(nowdate(), 3),
                "sales_order": r["sales_order"],
                "material_request": r["parent"],
                "material_request_item": r["name"],
            })
        po.insert()
        po.submit()
        po_name = po.name
        log("CREATED PO:", po_name, "items=", [(i.item_code, i.qty, i.sales_order) for i in po.items])
    else:
        log("REUSE PO:", po_name)

    prs = frappe.get_all("Purchase Receipt Item", filters={"purchase_order": po_name},
                         fields=["parent"], distinct=True)
    if not prs:
        from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_receipt
        pr = make_purchase_receipt(po_name)
        for i in pr.items:
            i.received_qty = i.qty
            i.warehouse = i.warehouse or "原材料仓 - QC"
        pr.posting_date = nowdate()
        pr.insert()
        pr.submit()
        log("CREATED PR:", pr.name, [(i.item_code, i.qty) for i in pr.items])
    else:
        log("REUSE PRs:", [r["parent"] for r in prs])

    wos = frappe.get_all("Work Order", filters={"production_plan": pp_name}, fields=["name"])
    if not wos:
        pp.reload()
        pp.make_work_order()
        wos = frappe.get_all("Work Order", filters={"production_plan": pp_name},
                             fields=["name", "docstatus"])
        log("CREATED WOs:", [(w["name"], w["docstatus"]) for w in wos])
    else:
        log("REUSE WOs:", [w["name"] for w in wos])

    # 工单提交 + 领料（合并工单：一张工单承载两张订单的实物）
    for w in wos:
        wo = frappe.get_doc("Work Order", w["name"])
        if wo.docstatus == 0:
            wo.wip_warehouse = wo.wip_warehouse or "生产在制仓 - QC"
            wo.fg_warehouse = wo.fg_warehouse or "产成品仓 - QC"
            wo.source_warehouse = wo.source_warehouse or "原材料仓 - QC"
            wo.save()
            wo.submit()
            log("SUBMITTED WO:", wo.name, "sales_order=", wo.sales_order,
                "sales_order_item=", wo.sales_order_item, "plan=", wo.production_plan)
        wo.reload()
        if wo.docstatus == 1 and not frappe.db.exists(
                "Stock Entry", {"work_order": wo.name, "purpose": "Material Transfer for Manufacture",
                                "docstatus": 1}):
            from erpnext.manufacturing.doctype.work_order.work_order import (
                make_stock_entry as wo_make_stock_entry)
            se = frappe.get_doc(wo_make_stock_entry(
                wo.name, "Material Transfer for Manufacture",
                wo.qty - wo.material_transferred_for_manufacturing))
            se.insert()
            se.submit()
            log("CREATED transfer:", se.name, "wo=", wo.name,
                [(i.item_code, i.qty) for i in se.items])

    frappe.db.commit()
    log("FLOW97_LOCAL_SAMPLE_DONE")
    log("PLAN=%s" % pp_name)
    log("SOS=%s" % ",".join(s.name for s in sos))
    log("MRS=%s" % ",".join(mr_names))
    log("PO=%s" % po_name)
    log("WOS=%s" % ",".join(w["name"] for w in wos))


if __name__ == "__main__":
    main()
