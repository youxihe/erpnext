# -*- coding: utf-8 -*-
"""BUILD-94 分角色联合验收：一笔新订单走完整链路，每步由对应岗位操作。

关键顺序（与 BUILD-92 不同）：**两名生产人员先把 9 个任务全部完成 → 成品仓必须不变 →
仓库再做原生 Manufacture 完工入库 → 成品仓 +1**。这样「任务完成 ≠ 库存入库」是被实测出来的，
不是靠话术声明。

角色：销售(wangming) → 工艺/生产经理(liugong) → 采购(chengong) → 仓库(zhanggong)
      → 生产李工(ligong)+刘工(liugong) → 仓库入库 → 销售发货 → 财务(zhoukaiji)。
脚本幂等，可重复执行；结果写 /hostshare/build94-execute.json。
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
MARK = "BUILD94-UAT-001"
FG = "ASSY-X1"
RAW = "原材料仓 - QC"
WIP = "生产在制仓 - QC"
FGWH = "产成品仓 - QC"
BOM_COMPONENTS = [("RACK", 2, 200), ("SENSOR", 1, 300), ("FASTENER", 4, 5)]

ROLE_USER = {
    "sales": "wangming@erpnext-poc.localhost",        # Sales Manager
    "purchase": "chengong@erpnext-poc.localhost",      # Purchase Manager
    "stock": "zhanggong@erpnext-poc.localhost",        # Stock Manager
    "manager": "liugong@erpnext-poc.localhost",        # Manufacturing Manager / 工艺
    "worker": "ligong@erpnext-poc.localhost",          # Manufacturing User / 李工
    "accounts": "zhoukaiji@erpnext-poc.localhost",     # Accounts Manager
}

out = {"steps": [], "ids": {}, "stock": {}, "errors": [], "roles": ROLE_USER}


def step(name, ok, detail=""):
    out["steps"].append({"name": name, "ok": bool(ok), "detail": str(detail)[:520]})
    print(("PASS " if ok else "FAIL ") + name + " | " + str(detail)[:300])


def as_user(role):
    frappe.set_user(ROLE_USER.get(role, role))


def bins(codes):
    rows = frappe.db.sql(
        "select item_code, warehouse, actual_qty from tabBin where item_code in %s",
        [tuple(codes)], as_dict=True,
    )
    return {"%s@%s" % (r["item_code"], r["warehouse"]): float(r["actual_qty"] or 0) for r in rows}


def sle():
    return frappe.db.count("Stock Ledger Entry")


def fg_qty():
    return float(frappe.db.get_value("Bin", {"item_code": FG, "warehouse": FGWH},
                                     "actual_qty") or 0)


def as_doc(obj):
    return frappe.get_doc(obj) if isinstance(obj, dict) else obj


def save(doc, submit=True):
    doc.insert(ignore_permissions=True)
    if submit:
        doc.submit()
    frappe.db.commit()
    return doc


def find_one(doctype, filters, order_by="creation desc"):
    rows = frappe.get_all(doctype, filters=filters, fields=["name"], order_by=order_by, limit=1)
    return rows[0]["name"] if rows else None


def ensure_binding(wecom_userid, erp_user):
    """生产经理也要能在机器人里查自己的任务，补一条企微绑定（幂等）。"""
    if frappe.db.exists("WeCom User Binding", {"wecom_userid": wecom_userid}):
        return False
    corp_id = frappe.db.get_value("WeCom User Binding", {}, "corp_id") or "LOCAL-MOCK-CORP"
    doc = frappe.new_doc("WeCom User Binding")
    doc.corp_id = corp_id
    doc.wecom_userid = wecom_userid
    doc.erp_user = erp_user
    doc.enabled = 1
    doc.note = "BUILD-94 UAT：生产经理机器人查询本人任务"
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return True


try:
    # ------------------------------------------------------------ 0. 起始快照
    out["stock"]["start"] = bins([FG, "RACK", "SENSOR", "FASTENER"])
    out["stock"]["sle_start"] = sle()
    out["ids"]["binding_liugong_created"] = ensure_binding("liugong", ROLE_USER["manager"])

    # ------------------------------------------------------------ 1. 销售下单
    as_user("sales")
    so_name = frappe.db.get_value("Sales Order", {"po_no": MARK}, "name")
    if not so_name:
        # 订单专属无工序 BOM（工艺出，不改标准 BOM 的默认关系）
        as_user("manager")
        src = frappe.get_doc("BOM", "BOM-ASSY-X1-002")
        bom = frappe.copy_doc(src)
        bom.company = COMPANY
        bom.is_default = 0
        bom.is_active = 1
        bom.insert(ignore_permissions=True)
        bom.submit()
        frappe.db.commit()
        out["ids"]["bom"] = bom.name

        as_user("sales")
        so = frappe.new_doc("Sales Order")
        so.customer = CUSTOMER
        so.company = COMPANY
        so.po_no = MARK
        so.transaction_date = today()
        so.delivery_date = add_days(getdate(today()), 14)
        so.business_type = "生产"
        so.append("items", {
            "item_code": FG, "qty": 1, "rate": 5000,
            "delivery_date": so.delivery_date, "warehouse": FGWH, "bom_no": bom.name,
        })
        save(so)
        so_name = so.name
    so = frappe.get_doc("Sales Order", so_name)
    bom_no = so.items[0].bom_no or frappe.db.get_value("BOM", {"item": FG, "is_active": 1,
                                                               "with_operations": 0}, "name")
    out["ids"].update({"sales_order": so_name, "bom": bom_no})
    step("销售下单：生产类订单提交并选用订单专属 BOM",
         so.docstatus == 1 and so.business_type == "生产" and so.items[0].bom_no == bom_no,
         {"so": so_name, "bom": bom_no, "qty": so.items[0].qty,
          "delivery_date": str(so.delivery_date), "amount": so.grand_total})

    # ------------------------------------------------------------ 2. 九阶段任务
    as_user("manager")
    from cn_mfg_poc import production
    proj = production.create_project(so_name)
    project = proj["project"]
    task_rows = frappe.get_all("Task", filters={"project": project,
                                                "status": ("not in", ["Template", "Cancelled"])},
                               fields=["name", "subject", "production_owner"],
                               order_by="exp_start_date, name")
    # 分派：前三个工序给李工，其余由刘工负责（两名生产人员）
    for i, t in enumerate(task_rows):
        owner = ROLE_USER["worker"] if i < 3 else ROLE_USER["manager"]
        if t["production_owner"] != owner:
            production.assign_task(t["name"], owner)
    task_rows = frappe.get_all("Task", filters={"project": project,
                                               "status": ("not in", ["Template", "Cancelled"])},
                               fields=["name", "subject", "production_owner"],
                               order_by="exp_start_date, name")
    out["ids"]["project"] = project
    out["ids"]["tasks"] = {t["name"]: t["subject"] for t in task_rows}
    out["ids"]["task_owners"] = {"worker": [t["name"] for t in task_rows[:3]],
                                 "manager": [t["name"] for t in task_rows[3:]]}
    step("工艺/生产经理建九阶段项目并按人分派",
         project and len(task_rows) == 9
         and sum(1 for t in task_rows if t["production_owner"] == ROLE_USER["worker"]) == 3,
         {"project": project, "tasks": len(task_rows),
          "worker_tasks": len(out["ids"]["task_owners"]["worker"])})

    # ------------------------------------------------------------ 3. 采购三单
    as_user("purchase")
    required = {"RACK": 2, "SENSOR": 1, "FASTENER": 4}
    available = {c: float(frappe.db.get_value("Bin", {"item_code": c, "warehouse": RAW},
                                              "actual_qty") or 0) for c in required}
    shortage = {c: max(0.0, required[c] - available[c]) for c in required}
    out["ids"]["shortage"] = shortage

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
        mr.append("items", {"item_code": "RACK", "qty": shortage["RACK"] or 2, "warehouse": RAW,
                            "schedule_date": today(), "sales_order": so_name, "rate": 200})
        save(mr)
        mr_name = mr.name
    out["ids"]["material_request"] = mr_name
    step("采购：缺料转原生 Material Request",
         bool(mr_name) and frappe.db.get_value("Material Request", mr_name, "docstatus") == 1,
         {"mr": mr_name, "shortage": shortage})

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
    step("采购：原生 Purchase Order 已提交",
         bool(po_name) and frappe.db.get_value("Purchase Order", po_name, "docstatus") == 1,
         {"po": po_name, "supplier": SUPPLIER})

    as_user("stock")
    from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_receipt
    pr_rows = frappe.get_all("Purchase Receipt Item", filters={"sales_order": so_name},
                             fields=["parent"], limit=5)
    pr_name = pr_rows[0]["parent"] if pr_rows else None
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
    out["ids"]["purchase_receipt"] = pr_name
    pr_sle = frappe.db.sql("select item_code, actual_qty from `tabStock Ledger Entry` "
                           "where voucher_no=%s and actual_qty>0", pr_name, as_dict=True)
    step("仓库：原生 Purchase Receipt 入库（RACK 实收）",
         bool(pr_name) and any(r["item_code"] == "RACK" for r in pr_sle),
         {"pr": pr_name, "sle": pr_sle})

    # ------------------------------------------------------------ 4. 工单 + 领料
    as_user("manager")
    wo_name = find_one("Work Order", {"sales_order": so_name, "production_item": FG})
    if not wo_name:
        wo = frappe.new_doc("Work Order")
        wo.company = COMPANY
        wo.production_item = FG
        wo.bom_no = bom_no
        wo.qty = 1
        wo.sales_order = so_name
        wo.wip_warehouse = WIP
        wo.fg_warehouse = FGWH
        wo.source_warehouse = RAW
        wo.skip_transfer = 0
        wo.planned_start_date = today()
        save(wo)
        wo_name = wo.name
    out["ids"]["work_order"] = wo_name
    step("生产：无工序工单提交，0 张 Job Card",
         frappe.db.get_value("Work Order", wo_name, "docstatus") == 1
         and frappe.db.count("Job Card", {"work_order": wo_name}) == 0,
         {"wo": wo_name, "job_cards": frappe.db.count("Job Card", {"work_order": wo_name})})

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
    step("仓库：原生领料单 原材料→在制仓",
         bool(transfer_name)
         and frappe.db.get_value("Stock Entry", transfer_name, "docstatus") == 1,
         {"ste": transfer_name})

    # ------------------------------------------------------------ 5. 两名生产人员完成全部任务
    fg_before_tasks = fg_qty()
    sle_before_tasks = sle()
    # 李工（H5 同一端点）
    as_user("worker")
    from cn_mfg_poc import api
    worker_done = []
    for name in out["ids"]["task_owners"]["worker"]:
        r = api.production_tasks_update(task=name, production_status="已完成",
                                        note="BUILD-94 UAT：李工在 H5 完成")
        worker_done.append((name, r["production_status"]))
    # 刘工（PC）
    as_user("manager")
    manager_done = []
    for name in out["ids"]["task_owners"]["manager"]:
        r = api.production_tasks_update(task=name, production_status="已完成",
                                        note="BUILD-94 UAT：刘工在 PC 完成")
        manager_done.append((name, r["production_status"]))
    frappe.db.commit()
    fg_after_tasks = fg_qty()
    sle_after_tasks = sle()
    all_tasks_completed = frappe.db.count("Task", {"project": project, "production_status": "已完成"})
    out["stock"]["task_gate"] = {
        "fg_before": fg_before_tasks, "fg_after": fg_after_tasks,
        "sle_before": sle_before_tasks, "sle_after": sle_after_tasks,
        "completed": all_tasks_completed,
    }
    step("两名生产人员完成任务（李工 3 项 / 刘工 6 项）",
         len(worker_done) == 3 and len(manager_done) == 6
         and all(v == "已完成" for _, v in worker_done + manager_done),
         {"worker": worker_done, "manager": manager_done})
    step("九项任务全部完成，成品仓仍为 0、SLE 不变（关键 Gate）",
         all_tasks_completed == 9 and fg_after_tasks == fg_before_tasks == 0
         and sle_after_tasks == sle_before_tasks,
         out["stock"]["task_gate"])

    # ------------------------------------------------------------ 6. 仓库正式完工入库
    fg_before = fg_qty()
    sle_before = sle()
    manufacture_name = find_one("Stock Entry", {"work_order": wo_name, "purpose": "Manufacture",
                                                "docstatus": 1})
    if not manufacture_name:
        as_user("stock")
        se = as_doc(make_stock_entry(wo_name, "Manufacture", 1))
        for r in se.items:
            if r.item_code == FG and not r.t_warehouse:
                r.t_warehouse = FGWH
            elif not r.s_warehouse:
                r.s_warehouse = WIP
        save(se)
        manufacture_name = se.name
    fg_after = fg_qty()
    sle_after = sle()
    mfg_sle = frappe.db.sql("select item_code, warehouse, actual_qty from `tabStock Ledger Entry` "
                            "where voucher_no=%s", manufacture_name, as_dict=True)
    out["ids"]["manufacture"] = manufacture_name
    out["stock"]["manufacture"] = {"fg_before": fg_before, "fg_after": fg_after,
                                   "sle_before": sle_before, "sle_after": sle_after,
                                   "produced_qty": frappe.db.get_value("Work Order", wo_name,
                                                                       "produced_qty")}
    step("仓库：原生 Manufacture 完工入库，成品仓 0→1",
         bool(manufacture_name)
         and frappe.db.get_value("Stock Entry", manufacture_name, "docstatus") == 1
         and any(r["item_code"] == FG and r["warehouse"] == FGWH and r["actual_qty"] > 0
                 for r in mfg_sle)
         and float(frappe.db.get_value("Work Order", wo_name, "produced_qty") or 0) >= 1,
         dict(out["stock"]["manufacture"], sle_rows=len(mfg_sle)))

    # ------------------------------------------------------------ 7. 一次发货
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
    so_after = frappe.get_doc("Sales Order", so_name)
    out["ids"]["delivery_note"] = dn_name
    step("销售：整机一次发货，成品仓 1→0、交付 100%",
         bool(dn_name) and so_after.per_delivered == 100 and fg_qty() == 0,
         {"dn": dn_name, "per_delivered": so_after.per_delivered, "fg_now": fg_qty()})

    # ------------------------------------------------------------ 8. 开票回款
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
    from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry
    pe_rows = frappe.get_all("Payment Entry Reference",
                             filters={"reference_doctype": "Sales Invoice",
                                      "reference_name": si_name}, fields=["parent"], limit=5)
    pe_name = pe_rows[0]["parent"] if pe_rows else None
    if not pe_name:
        pe = as_doc(get_payment_entry("Sales Invoice", si_name))
        pe.posting_date = today()
        pe.reference_no = MARK
        pe.reference_date = today()
        save(pe)
        pe_name = pe.name
    si_doc = frappe.get_doc("Sales Invoice", si_name)
    out["ids"].update({"sales_invoice": si_name, "payment_entry": pe_name})
    out["ids"]["outstanding"] = si_doc.outstanding_amount
    step("财务：原生发票 + 收款，应收清零",
         frappe.db.get_value("Sales Invoice", si_name, "docstatus") == 1
         and bool(pe_name) and float(si_doc.outstanding_amount) == 0.0,
         {"si": si_name, "pe": pe_name, "outstanding": si_doc.outstanding_amount})

    out["stock"]["end"] = bins([FG, "RACK", "SENSOR", "FASTENER"])
    out["stock"]["sle_end"] = sle()
except Exception as e:
    out["errors"].append({"error": repr(e), "trace": traceback.format_exc()[-1800:]})
    print("FATAL", repr(e))
finally:
    frappe.set_user("Administrator")

passed = sum(1 for s in out["steps"] if s["ok"])
out["summary"] = {"passed": passed, "total": len(out["steps"]),
                  "failed": [s["name"] for s in out["steps"] if not s["ok"]]}
print("RESULT %s/%s" % (passed, len(out["steps"])))
print(json.dumps({"summary": out["summary"], "ids": out["ids"]}, ensure_ascii=False, indent=1))
with open("/hostshare/build94-execute.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1, default=str)
