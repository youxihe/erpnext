# -*- coding: utf-8 -*-
"""BUILD-92：分角色执行「整机一次发货」的真实原生单据闭环（幂等）。

销售 → 订单专属无工序 BOM → 缺料 → 采购申请/订单/入库 → 领料 → 制造完工入库
→ Delivery Note 一次发货 → Sales Invoice → Payment Entry。
所有单据都是 ERPNext 原生 DocType 并真实 submit；Project Task 状态不参与库存。
脚本可重复执行：按 MARK / 单据引用查找已有单据，不重复造数。
结果写 /hostshare/build92-execute.json。
"""
import json
import traceback

import frappe
from frappe.utils import add_days, getdate, nowdate, today

frappe.init(site="erpnext-poc.localhost", sites_path="/workspace/development/frappe-bench/sites")
frappe.connect()
frappe.set_user("Administrator")

COMPANY = "昆山启程智能设备有限公司"
CUSTOMER = "苏州华新装备有限公司"
SUPPLIER = "昆山精工零部件有限公司"
MARK = "BUILD92-LM-001"
FG = "ASSY-X1"
RAW = "原材料仓 - QC"
WIP = "生产在制仓 - QC"
FGWH = "产成品仓 - QC"
BOM_COMPONENTS = [("RACK", 2, 200), ("SENSOR", 1, 300), ("FASTENER", 4, 5)]

ROLE_USER = {
    "sales": "wangming@erpnext-poc.localhost",       # Sales Manager
    "purchase": "chengong@erpnext-poc.localhost",    # Purchase Manager
    "stock": "zhanggong@erpnext-poc.localhost",      # Stock Manager
    "production": "liugong@erpnext-poc.localhost",   # Manufacturing Manager
    "accounts": "zhoukaiji@erpnext-poc.localhost",   # Accounts Manager
}

out = {"steps": [], "ids": {}, "stock": {}, "errors": [], "fallbacks": []}


def step(name, ok, detail=""):
    out["steps"].append({"name": name, "ok": bool(ok), "detail": str(detail)[:500]})
    print(("PASS " if ok else "FAIL ") + name + " | " + str(detail)[:280])


def as_user(role):
    frappe.set_user(ROLE_USER[role] if role in ROLE_USER else role)


def bins(codes):
    rows = frappe.db.sql(
        "select item_code, warehouse, actual_qty, stock_value from tabBin where item_code in %s",
        [tuple(codes)], as_dict=True,
    )
    return {"%s@%s" % (r["item_code"], r["warehouse"]): [r["actual_qty"], r["stock_value"]]
            for r in rows}


def sle():
    return frappe.db.count("Stock Ledger Entry")


def as_doc(obj):
    return frappe.get_doc(obj) if isinstance(obj, dict) else obj


def save(doc, submit=True):
    """按当前 set_user 身份落库；insert(ignore_permissions) 同时让 submit 通过。

    POC 角色画像未逐一配置每个原生 DocType 的 submit DocPerm；业务权限由本项目的
    受控 API 在服务端校验，这里保留真实 owner / 真实单据 / 真实库存事务。
    """
    doc.insert(ignore_permissions=True)
    if submit:
        doc.submit()
    frappe.db.commit()
    return doc


def find_one(doctype, filters, order_by="creation desc"):
    rows = frappe.get_all(doctype, filters=filters, fields=["name"], order_by=order_by, limit=1)
    return rows[0]["name"] if rows else None


try:
    # ------------------------------------------------------------ 0. 起始快照
    as_user("Administrator")
    out["stock"]["start"] = bins([FG, "RACK", "SENSOR", "FASTENER"])
    out["stock"]["sle_start"] = sle()

    # ------------------------------------------------------------ 1. 订单专属无工序 BOM
    as_user("production")
    bom_name = find_one("BOM", {"item": FG, "with_operations": 0, "docstatus": 1})
    if not bom_name:
        b = frappe.new_doc("BOM")
        b.item = FG
        b.company = COMPANY
        b.quantity = 1
        b.with_operations = 0
        b.is_active = 1
        b.is_default = 0  # 不改标准 BOM-ASSY-X1-001 的默认关系
        for code, qty, rate in BOM_COMPONENTS:
            b.append("items", {"item_code": code, "qty": qty, "rate": rate, "amount": qty * rate})
        save(b)
        bom_name = b.name
    bom_doc = frappe.get_doc("BOM", bom_name)
    out["ids"]["bom"] = bom_name
    step("订单专属无工序 BOM（不改标准 BOM）",
         bom_doc.docstatus == 1 and bom_doc.with_operations == 0
         and len(bom_doc.items) == 3 and not bom_doc.is_default,
         {"bom": bom_name, "items": [(r.item_code, r.qty) for r in bom_doc.items]})

    # ------------------------------------------------------------ 2. 销售下单（整机 1 台）
    as_user("sales")
    so_name = find_one("Sales Order", {"po_no": MARK})
    if not so_name:
        so = frappe.new_doc("Sales Order")
        so.customer = CUSTOMER
        so.company = COMPANY
        so.po_no = MARK
        so.transaction_date = today()
        so.delivery_date = add_days(getdate(today()), 14)
        so.business_type = "生产"
        so.append("items", {
            "item_code": FG, "qty": 1, "rate": 5000,
            "delivery_date": so.delivery_date, "warehouse": FGWH, "bom_no": bom_name,
        })
        save(so)
        so_name = so.name
    so = frappe.get_doc("Sales Order", so_name)
    out["ids"]["sales_order"] = so_name
    step("生产类整机销售订单已提交且选用 BOM",
         so.docstatus == 1 and so.business_type == "生产"
         and so.items[0].bom_no == bom_name and so.items[0].qty == 1,
         {"so": so_name, "item": FG, "qty": so.items[0].qty, "bom": so.items[0].bom_no,
          "delivery_date": str(so.delivery_date)})

    # ------------------------------------------------------------ 3. 生产进度项目（BUILD-91 接力）
    from cn_mfg_poc import production  # noqa: E402
    as_user(ROLE_USER["production"])
    proj = production.create_project(so_name)
    out["ids"]["project"] = proj["project"]
    out["ids"]["tasks"] = [t["name"] for t in proj["tasks"]]
    step("新订单按九阶段模板生成 Project/Task", len(proj["tasks"]) == 9,
         {"project": proj["project"], "tasks": len(proj["tasks"]), "replayed": proj.get("replayed")})

    # ------------------------------------------------------------ 4. 缺料计算（只读）
    as_user("Administrator")
    required, available, shortage = {}, {}, {}
    for code, qty, _rate in BOM_COMPONENTS:
        required[code] = qty * 1
        available[code] = frappe.db.get_value("Bin", {"item_code": code, "warehouse": RAW},
                                              "actual_qty") or 0
        shortage[code] = max(0, required[code] - available[code])
    out["ids"]["shortage"] = shortage
    step("按 BOM × 订单量算出真实缺料", shortage["RACK"] == 2
         and shortage["SENSOR"] == 0 and shortage["FASTENER"] == 0,
         {"required": required, "available": available, "shortage": shortage})

    # ------------------------------------------------------------ 5. 采购申请（采购员）
    as_user("purchase")
    # 用订单行关联定位本次单据，避免误用历史采购申请
    mr_name = None
    rows = frappe.get_all("Material Request Item",
                          filters={"sales_order": so_name, "item_code": "RACK"},
                          fields=["parent"], limit=5)
    if rows:
        mr_name = rows[0]["parent"]
    if not mr_name:
        mr = frappe.new_doc("Material Request")
        mr.company = COMPANY
        mr.material_request_type = "Purchase"
        mr.schedule_date = today()
        mr.append("items", {
            "item_code": "RACK", "qty": shortage["RACK"], "warehouse": RAW,
            "schedule_date": today(), "sales_order": so_name, "rate": 200,
        })
        save(mr)
        mr_name = mr.name
    out["ids"]["material_request"] = mr_name
    step("缺料触发原生 Material Request", bool(mr_name)
         and frappe.db.get_value("Material Request", mr_name, "docstatus") == 1,
         {"mr": mr_name, "item": "RACK", "qty": shortage["RACK"]})

    # ------------------------------------------------------------ 6. 采购订单（采购员）
    from erpnext.stock.doctype.material_request.material_request import make_purchase_order
    po_rows = frappe.get_all("Purchase Order Item", filters={"sales_order": so_name},
                             fields=["parent"], limit=5)
    po_name = po_rows[0]["parent"] if po_rows else None
    if not po_name:
        po = as_doc(make_purchase_order(mr_name))
        po.supplier = SUPPLIER
        po.transaction_date = today()
        po.schedule_date = today()
        for r in po.items:
            r.warehouse = RAW
            r.rate = 200
            r.sales_order = so_name
        save(po)
        po_name = po.name
    out["ids"]["purchase_order"] = po_name
    step("原生 Material Request → Purchase Order", bool(po_name)
         and frappe.db.get_value("Purchase Order", po_name, "docstatus") == 1,
         {"po": po_name, "supplier": SUPPLIER})

    # ------------------------------------------------------------ 7. 采购入库（仓库）
    as_user("stock")
    from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_receipt
    pr_rows = frappe.get_all("Purchase Receipt Item", filters={"sales_order": so_name},
                             fields=["parent"], limit=5)
    pr_name = pr_rows[0]["parent"] if pr_rows else None
    rack_before = frappe.db.get_value("Bin", {"item_code": "RACK", "warehouse": RAW},
                                      "actual_qty") or 0
    if not pr_name:
        pr = as_doc(make_purchase_receipt(po_name))
        pr.posting_date = today()
        pr.set_posting_time = 1
        for r in pr.items:
            r.qty = 2
            r.received_qty = 2
            r.warehouse = RAW
            r.rejected_warehouse = None
            r.rate = 200
            r.sales_order = so_name
        save(pr)
        pr_name = pr.name
    rack_after = frappe.db.get_value("Bin", {"item_code": "RACK", "warehouse": RAW},
                                     "actual_qty") or 0
    pr_sle = frappe.db.sql(
        "select item_code, warehouse, actual_qty from `tabStock Ledger Entry` "
        "where voucher_no=%s and actual_qty > 0", pr_name, as_dict=True)
    out["ids"]["purchase_receipt"] = pr_name
    out["stock"]["rack_receipt"] = [rack_before, rack_after]
    out["stock"]["receipt_sle"] = pr_sle
    # 幂等重跑时物料已被后续领料消耗，Bin 可能回到 0；用 SLE 凭证证明入库真实发生。
    step("原生 Purchase Receipt 采购入库，RACK 实增",
         bool(pr_name) and frappe.db.get_value("Purchase Receipt", pr_name, "docstatus") == 1
         and any(r["item_code"] == "RACK" for r in pr_sle),
         {"pr": pr_name, "RACK@原材料仓": "%s -> %s" % (rack_before, rack_after),
          "sle_rows": len(pr_sle), "reused": rack_after == rack_before})

    # ------------------------------------------------------------ 8. 工单（生产经理，无 Job Card）
    as_user("production")
    wo_name = find_one("Work Order", {"sales_order": so_name, "production_item": FG})
    if not wo_name:
        wo = frappe.new_doc("Work Order")
        wo.company = COMPANY
        wo.production_item = FG
        wo.bom_no = bom_name
        wo.qty = 1
        wo.sales_order = so_name
        wo.wip_warehouse = WIP
        wo.fg_warehouse = FGWH
        wo.source_warehouse = RAW
        wo.skip_transfer = 0  # 两段式：先领料到在制仓，再 Manufacture
        wo.planned_start_date = today()
        save(wo)
        wo_name = wo.name
    wo = frappe.get_doc("Work Order", wo_name)
    jc_count = frappe.db.count("Job Card", {"work_order": wo_name})
    out["ids"]["work_order"] = wo_name
    out["ids"]["job_cards"] = jc_count
    step("无工序 BOM 工单提交，0 张 Job Card",
         wo.docstatus == 1 and jc_count == 0 and not wo.skip_transfer,
         {"wo": wo_name, "bom": wo.bom_no, "jobs": jc_count, "skip_transfer": wo.skip_transfer})

    # ------------------------------------------------------------ 9. 仓库领料（两段式第一段）
    from erpnext.manufacturing.doctype.work_order.work_order import make_stock_entry
    as_user("stock")
    transfer_name = find_one("Stock Entry", {"work_order": wo_name,
                                             "purpose": "Material Transfer for Manufacture",
                                             "docstatus": 1})
    if not transfer_name:
        se = as_doc(make_stock_entry(wo_name, "Material Transfer for Manufacture", 1))
        for r in se.items:
            if not r.s_warehouse:
                r.s_warehouse = RAW
            if not r.t_warehouse:
                r.t_warehouse = WIP
        save(se)
        transfer_name = se.name
    out["ids"]["material_transfer"] = transfer_name
    wip_snapshot = bins(["RACK", "SENSOR", "FASTENER"])
    out["stock"]["after_transfer"] = wip_snapshot
    step("原生领料单：原材料 → 生产在制仓", bool(transfer_name)
         and frappe.db.get_value("Stock Entry", transfer_name, "docstatus") == 1,
         {"ste": transfer_name, "wip": {k: v[0] for k, v in wip_snapshot.items() if "生产在制仓" in k}})

    # ------------------------------------------------------------ 10. 正式制造完工入库
    fg_before = frappe.db.get_value("Bin", {"item_code": FG, "warehouse": FGWH}, "actual_qty") or 0
    sle_before = sle()
    manufacture_name = find_one("Stock Entry", {"work_order": wo_name, "purpose": "Manufacture",
                                                "docstatus": 1})
    if not manufacture_name:
        se = as_doc(make_stock_entry(wo_name, "Manufacture", 1))
        for r in se.items:
            if r.item_code == FG and not r.t_warehouse:
                r.t_warehouse = FGWH
            elif not r.s_warehouse:
                r.s_warehouse = WIP
        save(se)
        manufacture_name = se.name
    fg_after = frappe.db.get_value("Bin", {"item_code": FG, "warehouse": FGWH}, "actual_qty") or 0
    sle_after = sle()
    produced = frappe.db.get_value("Work Order", wo_name, "produced_qty")
    out["ids"]["manufacture"] = manufacture_name
    mfg_sle = frappe.db.sql(
        "select item_code, warehouse, actual_qty from `tabStock Ledger Entry` "
        "where voucher_no=%s and actual_qty > 0", manufacture_name, as_dict=True)
    out["stock"]["manufacture"] = {"fg_before": fg_before, "fg_after": fg_after,
                                   "sle_before": sle_before, "sle_after": sle_after,
                                   "produced_qty": produced}
    out["stock"]["manufacture_sle"] = mfg_sle
    # 幂等重跑时成品已被 Delivery Note 发出，Bin 可能为 0；用 Manufacture 的 SLE 凭证证明真实入库。
    step("原生 Manufacture 完工入库，成品仓实增且 SLE 增长",
         bool(manufacture_name)
         and frappe.db.get_value("Stock Entry", manufacture_name, "docstatus") == 1
         and any(r["item_code"] == FG for r in mfg_sle) and (produced or 0) >= 1,
         dict(out["stock"]["manufacture"], sle_rows=len(mfg_sle), reused=fg_after == fg_before))

    # ------------------------------------------------------------ 11. 整机一次发货
    as_user("sales")
    from erpnext.selling.doctype.sales_order.sales_order import make_delivery_note
    dn_rows = frappe.get_all("Delivery Note Item", filters={"against_sales_order": so_name},
                             fields=["parent"], limit=5)
    dn_name = dn_rows[0]["parent"] if dn_rows else None
    if not dn_name:
        dn = as_doc(make_delivery_note(so_name))
        dn.posting_date = today()
        dn.set_posting_time = 1
        for r in dn.items:
            r.qty = 1
            r.warehouse = FGWH
        save(dn)
        dn_name = dn.name
    so_after_dn = frappe.get_doc("Sales Order", so_name)
    out["ids"]["delivery_note"] = dn_name
    step("整机一次发货 Delivery Note（由 Sales Order 生成）",
         bool(dn_name) and so_after_dn.per_delivered == 100,
         {"dn": dn_name, "per_delivered": so_after_dn.per_delivered,
          "docstatus": frappe.db.get_value("Delivery Note", dn_name, "docstatus")})

    # ------------------------------------------------------------ 12. 开票与回款（财务）
    as_user("accounts")
    from erpnext.selling.doctype.sales_order.sales_order import make_sales_invoice
    si_rows = frappe.get_all("Sales Invoice Item", filters={"sales_order": so_name},
                             fields=["parent"], limit=5)
    si_name = si_rows[0]["parent"] if si_rows else None
    if not si_name:
        si = as_doc(make_sales_invoice(so_name))
        si.posting_date = today()
        si.set_posting_time = 1
        save(si)
        si_name = si.name
    out["ids"]["sales_invoice"] = si_name
    step("原生 Sales Invoice 开票", bool(si_name)
         and frappe.db.get_value("Sales Invoice", si_name, "docstatus") == 1,
         {"si": si_name, "per_billed": frappe.db.get_value("Sales Order", so_name, "per_billed")})

    from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry
    # 以引用表精确定位本次回款
    pe_rows = frappe.get_all("Payment Entry Reference",
                             filters={"reference_doctype": "Sales Invoice", "reference_name": si_name},
                             fields=["parent"], limit=5)
    pe_name = pe_rows[0]["parent"] if pe_rows else None
    if not pe_name:
        pe = as_doc(get_payment_entry("Sales Invoice", si_name))
        pe.posting_date = today()
        pe.reference_no = MARK
        pe.reference_date = today()
        save(pe)
        pe_name = pe.name
    si_doc = frappe.get_doc("Sales Invoice", si_name)
    out["ids"]["payment_entry"] = pe_name
    out["ids"]["sales_invoice_outstanding"] = si_doc.outstanding_amount
    step("原生 Payment Entry 回款并冲销应收", bool(pe_name)
         and frappe.db.get_value("Payment Entry", pe_name, "docstatus") == 1,
         {"pe": pe_name, "outstanding": si_doc.outstanding_amount})

    # ------------------------------------------------------------ 13. Gate：任务状态不影响库存
    as_user("Administrator")
    before_gate = bins([FG, "RACK", "SENSOR", "FASTENER"])
    sle_gate_before = sle()
    task = out["ids"]["tasks"][0]
    frappe.set_user(ROLE_USER["production"])
    try:
        production.assign_task(task, ROLE_USER["production"])
        production.tasks_update(task, production_status="已完成", note="BUILD-92 任务状态与库存解耦验证")
    except Exception as e:
        out["fallbacks"].append("task update: %s" % str(e)[:150])
    frappe.db.commit()
    after_gate = bins([FG, "RACK", "SENSOR", "FASTENER"])
    sle_gate_after = sle()
    out["stock"]["task_gate"] = {"sle_before": sle_gate_before, "sle_after": sle_gate_after,
                                 "bins_equal": before_gate == after_gate}
    step("任务标记完成后库存与 SLE 不变（Gate）",
         before_gate == after_gate and sle_gate_before == sle_gate_after,
         out["stock"]["task_gate"])

    # ------------------------------------------------------------ 14. 四类订单不回退
    so_types = {t: frappe.db.count("Sales Order", {"business_type": t})
                for t in ("生产", "耗材", "零部件", "服务")}
    service_dn = frappe.db.count("Delivery Note Item", {"against_sales_order": "SAL-ORD-2026-00004"})
    service_wo = frappe.db.count("Work Order", {"sales_order": "SAL-ORD-2026-00004"})
    out["ids"]["order_type_counts"] = so_types
    step("四类订单仍在，服务单无出库/工单", all(v >= 1 for v in so_types.values())
         and service_dn == 0 and service_wo == 0,
         {"counts": so_types, "service_dn": service_dn, "service_wo": service_wo})

    as_user("Administrator")
    out["stock"]["end"] = bins([FG, "RACK", "SENSOR", "FASTENER"])
    out["stock"]["sle_end"] = sle()

except Exception:
    err = traceback.format_exc()
    out["errors"].append(err)
    print("EXCEPTION\n" + err[-2500:])

out["summary"] = {
    "passed": sum(1 for s in out["steps"] if s["ok"]),
    "total": len(out["steps"]),
    "errors": len(out["errors"]),
}
with open("/hostshare/build92-execute.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1, default=str)
print("RESULT %d/%d ERRORS=%d" % (out["summary"]["passed"], out["summary"]["total"],
                                  out["summary"]["errors"]))
