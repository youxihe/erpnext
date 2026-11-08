# -*- coding: utf-8 -*-
"""BUILD-92 真实测试：订单执行概览聚合、按角色财务隔离、单据链、四类订单不回退。"""
import json
import traceback

import frappe

frappe.init(site="erpnext-poc.localhost", sites_path="/workspace/development/frappe-bench/sites")
frappe.connect()

from cn_mfg_poc import order_execution  # noqa: E402

SO = "SAL-ORD-2026-00006"
EXPECTED = {
    "bom": "BOM-ASSY-X1-002",
    "material_request": "MAT-MR-2026-00002",
    "purchase_order": "PUR-ORD-2026-00002",
    "purchase_receipt": "MAT-PRE-2026-00016",
    "work_order": "MFG-WO-2026-00004",
    "material_transfer": "MAT-STE-2026-00010",
    "manufacture": "MAT-STE-2026-00011",
    "delivery_note": "MAT-DN-2026-00005",
    "sales_invoice": "ACC-SINV-2026-00006",
    "payment_entry": "ACC-PAY-2026-00006",
    "project": "PROJ-0003",
}
SALES = "wangming@erpnext-poc.localhost"
STOCK = "zhanggong@erpnext-poc.localhost"
PURCHASE = "chengong@erpnext-poc.localhost"
PRODUCTION = "liugong@erpnext-poc.localhost"
ACCOUNTS = "zhoukaiji@erpnext-poc.localhost"

out = {"steps": [], "errors": [], "ids": EXPECTED}


def step(name, ok, detail=""):
    out["steps"].append({"name": name, "ok": bool(ok), "detail": str(detail)[:500]})
    print(("PASS " if ok else "FAIL ") + name + " | " + str(detail)[:260])


def as_user(u):
    frappe.set_user(u)


def no_amount(docs):
    return all("grand_total" not in d for d in docs)


try:
    # ------------------------------------------------------------ 1. 管理员全量聚合
    as_user("Administrator")
    r = order_execution.order_summary(SO)
    out["summary_sample"] = {
        "order": r["order"], "materials": r["materials"]["components"],
        "progress": r["progress"], "physical": r["physical"], "finance": r["finance"],
    }
    step("概览返回真实订单/BOM/金额", r["order"]["name"] == SO
         and r["order"]["grand_total"] == 5000 and r["boms"][0]["name"] == EXPECTED["bom"],
         {"so": r["order"]["name"], "bom": r["boms"][0]["name"], "total": r["order"]["grand_total"]})

    docs = r["documents"]
    step("订单选用 BOM 与 SO 行一致", r["items"][0]["bom_no"] == EXPECTED["bom"],
         r["items"][0]["bom_no"])

    for key, field in [("material_request", "material_request"), ("purchase_order", "purchase_order"),
                       ("purchase_receipt", "purchase_receipt"), ("work_order", "work_order"),
                       ("delivery_note", "delivery_note"), ("sales_invoice", "sales_invoice"),
                       ("payment_entry", "payment_entry")]:
        names = [d["name"] for d in docs[field]]
        step("单据链可见 %s" % field, EXPECTED[key] in names, names)

    se_names = [d["name"] for d in docs["stock_entry"]]
    step("领料 + 完工入库两段式原生 Stock Entry",
         EXPECTED["material_transfer"] in se_names and EXPECTED["manufacture"] in se_names,
         se_names)
    step("整机一次发货且完工/发货数量均为 1",
         r["physical"]["once_delivery"] and r["physical"]["produced_qty"] == 1
         and r["physical"]["delivered_qty"] == 1 and r["physical"]["job_cards"] == 0,
         r["physical"])

    comp = {c["item_code"]: c for c in r["materials"]["components"]}
    step("缺料→采购→入库→领料→消耗全程可追溯",
         comp["RACK"]["requested_qty"] == 2 and comp["RACK"]["purchased_qty"] == 2
         and comp["RACK"]["received_qty"] == 2 and comp["RACK"]["issued_qty"] == 2
         and comp["RACK"]["consumed_qty"] == 2 and comp["RACK"]["shortage"] == 0,
         comp["RACK"])
    step("全部组件预计缺料为 0（闭环后）", r["materials"]["total_shortage"] == 0,
         {"total_shortage": r["materials"]["total_shortage"],
          "formula": r["materials"]["shortage_formula"]})
    step("生产进度来自同一 Project/Task",
         r["progress"]["project"] == EXPECTED["project"] and r["progress"]["total"] == 9,
         r["progress"])
    step("财务字段对管理员可见且已回款结清",
         r["finance_visible"] and r["finance"]["paid_amount"] == 5000
         and r["finance"]["outstanding_amount"] == 0,
         r["finance"])

    # ------------------------------------------------------------ 2. 分角色金额隔离
    for user, label in [(SALES, "销售"), (STOCK, "仓库"), (PURCHASE, "采购"),
                        (PRODUCTION, "生产")]:
        as_user(user)
        v = order_execution.order_summary(SO)
        all_docs = sum((v["documents"][k] for k in
                        ("material_request", "purchase_order", "purchase_receipt",
                         "delivery_note", "sales_invoice")), [])
        step("%s角色可读单据链但金额被隐藏" % label,
             (not v["finance_visible"]) and v["finance"] is None
             and v["order"]["grand_total"] is None
             and all(i["rate"] is None for i in v["items"])
             and no_amount(all_docs)
             and any(d["name"] == EXPECTED["delivery_note"] for d in v["documents"]["delivery_note"]),
             {"finance_visible": v["finance_visible"], "documents": len(all_docs)})

    as_user(ACCOUNTS)
    f = order_execution.order_summary(SO)
    step("财务角色可见金额", f["finance_visible"] and f["finance"]["paid_amount"] == 5000,
         f["finance"])

    # ------------------------------------------------------------ 3. 未登录/无权
    as_user("Guest")
    try:
        order_execution.order_summary(SO)
        step("Guest 不能读订单执行概览", False, "未拒绝")
    except Exception as e:
        step("Guest 不能读订单执行概览", "无权" in str(e) or "PermissionError" in type(e).__name__,
             "%s: %s" % (type(e).__name__, str(e)[:100]))

    # ------------------------------------------------------------ 4. 缺料契约
    as_user(ADMIN := "Administrator")
    ms = order_execution.materials_shortage(limit=20)
    step("materials.shortage 返回真实来源与公式",
         "shortage_formula" in ms and isinstance(ms["orders"], list) and ms["user"] == ADMIN,
         {"count": ms["count"], "formula": ms["shortage_formula"]})

    # ------------------------------------------------------------ 5. 四类订单不回退 + 服务不扣库存
    counts = {t: frappe.db.count("Sales Order", {"business_type": t})
              for t in ("生产", "耗材", "零部件", "服务")}
    service = "SAL-ORD-2026-00004"
    service_dn = frappe.db.count("Delivery Note Item", {"against_sales_order": service})
    service_se = frappe.db.sql(
        "select count(*) from `tabStock Ledger Entry` where voucher_type='Delivery Note' "
        "and voucher_no in (select parent from `tabDelivery Note Item` where against_sales_order=%s)",
        service)[0][0]
    service_wo = frappe.db.count("Work Order", {"sales_order": service})
    step("四类订单仍在且服务单不出库/不生产",
         all(v >= 1 for v in counts.values()) and service_dn == 0
         and service_se == 0 and service_wo == 0,
         {"counts": counts, "service_dn": service_dn, "service_sle": service_se,
          "service_wo": service_wo})

    for name, label in [("SAL-ORD-2026-00002", "耗材"), ("SAL-ORD-2026-00003", "零部件")]:
        dn = frappe.db.count("Delivery Note Item", {"against_sales_order": name})
        wo = frappe.db.count("Work Order", {"sales_order": name})
        step("%s订单直接出库且不触发生产" % label, dn >= 1 and wo == 0,
             {"dn_items": dn, "work_orders": wo})

    # ------------------------------------------------------------ 6. 任务不触发库存
    hooks = frappe.get_hooks("doc_events") or {}
    step("Task/Project 仍无库存 doc_events",
         not (hooks.get("Task") or hooks.get("Project")),
         {"Task": hooks.get("Task"), "Project": hooks.get("Project")})

except Exception:
    err = traceback.format_exc()
    out["errors"].append(err)
    print("EXCEPTION\n" + err[-2200:])

out["summary"] = {"passed": sum(1 for s in out["steps"] if s["ok"]),
                  "total": len(out["steps"]), "errors": len(out["errors"])}
with open("/hostshare/build92-verify.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1, default=str)
print("RESULT %d/%d ERRORS=%d" % (out["summary"]["passed"], out["summary"]["total"],
                                  out["summary"]["errors"]))
