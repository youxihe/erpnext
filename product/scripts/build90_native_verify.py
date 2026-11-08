# -*- coding: utf-8 -*-
"""BUILD-90 关键技术验证：BOM 无 Operations / 无 Job Card 时能否合法完工入库。

在隔离 POC Site 上新建独立的 LM90-* 测试物料与单据（不影响既有演示物料），
真实提交并记录单号与库存前后值；同时验证 Task 状态变更不触发任何库存过账。
输出 docs/product/evidence/build90-native-verify.json。
可重复执行：已存在同名测试单据时复用，不重复造数。
"""
import json
import traceback

import frappe
from frappe.utils import add_days, nowdate

frappe.init(site="erpnext-poc.localhost", sites_path="/workspace/development/frappe-bench/sites")
frappe.connect()
frappe.set_user("Administrator")

COMPANY = "昆山启程智能设备有限公司"
RAW = "原材料仓 - QC"
WIP = "生产在制仓 - QC"
FGWH = "产成品仓 - QC"
FG = "LM90-FG"
RM = "LM90-RM"
PROJECT_NAME = "LM90-进度与库存解耦验证"

out = {"steps": [], "errors": []}


def step(name, ok, detail=""):
    out["steps"].append({"step": name, "ok": bool(ok), "detail": str(detail)[:400]})
    print(("PASS " if ok else "FAIL ") + name + " | " + str(detail)[:300])


def bins(item_codes):
    rows = frappe.db.sql(
        "select item_code, warehouse, actual_qty, stock_value from tabBin where item_code in %s",
        [tuple(item_codes)],
        as_dict=True,
    )
    return {"%s@%s" % (r["item_code"], r["warehouse"]): [r["actual_qty"], r["stock_value"]] for r in rows}


def sle_count():
    return frappe.db.count("Stock Ledger Entry")


def ensure_item(code, name):
    if frappe.db.exists("Item", code):
        return frappe.get_doc("Item", code)
    group = frappe.db.get_value("Item Group", {"is_group": 0}, "name") or "All Item Groups"
    d = frappe.new_doc("Item")
    d.item_code = code
    d.item_name = name
    d.item_group = group
    d.stock_uom = "Nos"
    d.is_stock_item = 1
    d.include_item_in_manufacturing = 1
    d.valuation_rate = 100
    d.insert()
    frappe.db.commit()
    return d


try:
    # ---------------------------------------------------------- 1. 独立测试物料
    ensure_item(FG, "BUILD90 验证成品")
    ensure_item(RM, "BUILD90 验证原料")
    step("独立测试物料就绪", frappe.db.exists("Item", FG) and frappe.db.exists("Item", RM), f"{FG} / {RM}")

    # ---------------------------------------------------------- 2. 无工序 BOM
    bom_name = frappe.db.get_value("BOM", {"item": FG, "with_operations": 0}, "name")
    if not bom_name:
        b = frappe.new_doc("BOM")
        b.item = FG
        b.company = COMPANY
        b.quantity = 1
        b.with_operations = 0
        b.is_active = 1
        b.is_default = 1
        b.append("items", {"item_code": RM, "qty": 1, "rate": 100, "amount": 100})
        b.insert()
        b.submit()
        frappe.db.commit()
        bom_name = b.name
    b = frappe.get_doc("BOM", bom_name)
    op_rows = frappe.db.count("BOM Operation", {"parent": b.name, "parenttype": "BOM"}) if frappe.db.exists("DocType", "BOM Operation") else 0
    step("无工序单层 BOM 已提交", b.docstatus == 1 and b.with_operations == 0 and op_rows == 0,
         f"{bom_name} with_operations={b.with_operations} operations={op_rows} docstatus={b.docstatus}")

    # ---------------------------------------------------------- 3. 原料初始入库（真实库存）
    before_receipt = bins([FG, RM])
    existing_receipt = None
    for se in frappe.get_all("Stock Entry", filters={"purpose": "Material Receipt"}, fields=["name"], limit=50):
        if frappe.db.exists("Stock Entry Detail", {"parent": se["name"], "item_code": RM}):
            existing_receipt = se["name"]
            break
    if not existing_receipt:
        se = frappe.new_doc("Stock Entry")
        se.stock_entry_type = se.purpose = "Material Receipt"
        se.company = COMPANY
        se.append("items", {"item_code": RM, "qty": 10, "basic_rate": 100, "t_warehouse": RAW})
        se.insert()
        se.submit()
        frappe.db.commit()
        existing_receipt = se.name
    after_receipt = bins([FG, RM])
    step("原料真实入库", "%s@%s" % (RM, RAW) in after_receipt and after_receipt["%s@%s" % (RM, RAW)][0] >= 10,
         f"单号={existing_receipt} 前后={before_receipt} -> {after_receipt}")

    # ---------------------------------------------------------- 4. 无工序 Work Order（不产生 Job Card）
    wo_name = frappe.db.get_value("Work Order", {"production_item": FG, "bom_no": bom_name}, "name")
    if not wo_name:
        w = frappe.new_doc("Work Order")
        w.company = COMPANY
        w.production_item = FG
        w.bom_no = bom_name
        w.qty = 1
        w.wip_warehouse = WIP
        w.fg_warehouse = FGWH
        w.source_warehouse = RAW
        w.skip_transfer = 1  # 直接从源仓消耗，无需先做 Material Transfer
        w.insert()
        w.submit()
        frappe.db.commit()
        wo_name = w.name
    w = frappe.get_doc("Work Order", wo_name)
    wo_ops = frappe.db.count("Work Order Operation", {"parent": w.name, "parenttype": "Work Order"}) if frappe.db.exists("DocType", "Work Order Operation") else 0
    wo_jc = frappe.db.count("Job Card", {"work_order": w.name})
    step("无工序工单已提交且无 Job Card", w.docstatus == 1 and wo_ops == 0 and wo_jc == 0,
         f"{wo_name} docstatus={w.docstatus} operations={wo_ops} job_cards={wo_jc} skip_transfer={w.skip_transfer}")

    # ---------------------------------------------------------- 5. Manufacture 完工入库
    before = bins([FG, RM])
    sle_before = sle_count()
    manufacture_name = None
    for se in frappe.get_all("Stock Entry", filters={"purpose": "Manufacture", "work_order": wo_name, "docstatus": 1}, fields=["name"], limit=10):
        manufacture_name = se["name"]
        break
    if not manufacture_name:
        from erpnext.manufacturing.doctype.work_order.work_order import make_stock_entry
        # v16 make_stock_entry returns stock_entry.as_dict(); rebuild a Document.
        se = frappe.get_doc(make_stock_entry(wo_name, "Manufacture", 1))
        # ensure source warehouse is set when skip_transfer=1
        for row in se.items:
            if row.item_code == RM and not row.s_warehouse:
                row.s_warehouse = RAW
            if row.item_code == FG and not row.t_warehouse:
                row.t_warehouse = FGWH
        se.insert()
        se.submit()
        frappe.db.commit()
        manufacture_name = se.name
    after = bins([FG, RM])
    sle_after = sle_count()
    wo_after = frappe.db.get_value("Work Order", wo_name, "produced_qty")
    finished_ok = (
        after.get("%s@%s" % (FG, FGWH), [0])[0] > before.get("%s@%s" % (FG, FGWH), [0])[0]
        and sle_after > sle_before
    )
    step("无 Job Card 也能原生 Manufacture 完工入库", finished_ok,
         f"单号={manufacture_name} SLE {sle_before}->{sle_after} 成品仓 {before.get(FG+'@'+FGWH)} -> {after.get(FG+'@'+FGWH)} produced_qty={wo_after}")
    out["manufacture"] = {
        "work_order": wo_name, "bom": bom_name, "stock_entry": manufacture_name,
        "bins_before": before, "bins_after": after,
        "sle_before": sle_before, "sle_after": sle_after, "produced_qty": wo_after,
    }

    # ---------------------------------------------------------- 6. Gate：Task 状态变更不触发库存
    hooks = frappe.get_hooks("doc_events") or {}
    no_task_hooks = not (hooks.get("Task") or hooks.get("Project"))
    step("Task/Project 无库存相关 doc_events", no_task_hooks, {"Task": hooks.get("Task"), "Project": hooks.get("Project")})

    proj_name = frappe.db.get_value("Project", {"project_name": PROJECT_NAME}, "name")
    if not proj_name:
        p = frappe.new_doc("Project")
        p.project_name = PROJECT_NAME
        p.company = COMPANY
        p.status = "Open"
        p.is_active = "Yes"
        p.insert()
        frappe.db.commit()
        proj_name = p.name
    task_name = frappe.db.get_value("Task", {"project": proj_name, "subject": "LM90 验证任务"}, "name")
    if not task_name:
        t = frappe.new_doc("Task")
        t.subject = "LM90 验证任务"
        t.project = proj_name
        t.status = "Open"
        t.exp_end_date = add_days(nowdate(), -1)
        t.insert()
        frappe.db.commit()
        task_name = t.name
    t = frappe.get_doc("Task", task_name)
    snap_before = bins([FG, RM])
    sle_task_before = sle_count()
    if t.status != "Completed":
        t.status = "Completed"
        t.completed_on = nowdate()
        t.save()
        frappe.db.commit()
    snap_after = bins([FG, RM])
    sle_task_after = sle_count()
    unchanged = snap_before == snap_after and sle_task_before == sle_task_after
    step("任务状态改为完成不改动库存/SLE", unchanged,
         f"Task={task_name} {t.status} Bin一致={snap_before == snap_after} SLE {sle_task_before}->{sle_task_after}")
    out["task_gate"] = {
        "project": proj_name, "task": task_name, "status": t.status,
        "bins_before": snap_before, "bins_after": snap_after,
        "sle_before": sle_task_before, "sle_after": sle_task_after,
    }

except Exception:
    err = traceback.format_exc()
    out["errors"].append(err)
    print("EXCEPTION\n" + err[-1500:])

out["summary"] = {
    "passed": sum(1 for s in out["steps"] if s["ok"]),
    "total": len(out["steps"]),
    "errors": len(out["errors"]),
}
with open("/hostshare/build90-native-verify.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1, default=str)
print("RESULT %d/%d ERRORS=%d" % (out["summary"]["passed"], out["summary"]["total"], out["summary"]["errors"]))
