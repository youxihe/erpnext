# -*- coding: utf-8 -*-
"""BUILD-94 库存流水回溯：把一笔订单的库存变化逐张单据、逐条流水列出来。

执行脚本会幂等重跑，因此「首跑增量」不能从最后一次 JSON 快照读，
必须回到不可变的 Stock Ledger Entry 凭证。本脚本只读。
"""
import json

import frappe

frappe.init(site="erpnext-poc.localhost", sites_path="/workspace/development/frappe-bench/sites")
frappe.connect()

SO = "SAL-ORD-2026-00008"
VOUCHERS = ["MAT-PRE-2026-00017", "MAT-STE-2026-00012", "MAT-STE-2026-00013",
            "MAT-DN-2026-00006"]
PURPOSE = {
    "MAT-PRE-2026-00017": "采购入库（RACK 到原材料仓）",
    "MAT-STE-2026-00012": "领料（原材料仓 → 生产在制仓）",
    "MAT-STE-2026-00013": "Manufacture 完工入库（在制仓耗料 + 成品入成品仓）",
    "MAT-DN-2026-00006": "整机一次发货（成品仓出库）",
}

out = {"sales_order": SO, "vouchers": [], "totals": {}, "task_gate": {}}
for v in VOUCHERS:
    rows = frappe.db.sql(
        "select item_code, warehouse, actual_qty, qty_after_transaction, posting_date, creation "
        "from `tabStock Ledger Entry` where voucher_no=%s order by creation", v, as_dict=True)
    out["vouchers"].append({
        "voucher_no": v, "purpose": PURPOSE[v], "sle_count": len(rows),
        "rows": [{"item_code": r["item_code"], "warehouse": r["warehouse"],
                  "actual_qty": float(r["actual_qty"]),
                  "qty_after": float(r["qty_after_transaction"]),
                  "posting_date": str(r["posting_date"])} for r in rows],
    })

out["totals"]["sle_total"] = frappe.db.count("Stock Ledger Entry")
out["totals"]["sle_for_this_order"] = sum(v["sle_count"] for v in out["vouchers"])
out["totals"]["job_cards"] = frappe.db.count("Job Card", {"work_order": "MFG-WO-2026-00005"})
out["task_gate"] = {
    "tasks_completed": frappe.db.count("Task", {"project": "PROJ-0005",
                                                "production_status": "已完成"}),
    "fg_now": float(frappe.db.get_value("Bin", {"item_code": "ASSY-X1",
                                                "warehouse": "产成品仓 - QC"},
                                        "actual_qty") or 0),
    "manufacture_produced_qty": float(frappe.db.get_value("Work Order", "MFG-WO-2026-00005",
                                                          "produced_qty") or 0),
    "note": "9 项任务全部完成时成品仓仍是 0；+1 只发生在 MAT-STE-2026-00013 过账时",
}
out["residual_wip"] = frappe.db.sql(
    "select item_code, actual_qty from tabBin where warehouse='生产在制仓 - QC' "
    "and actual_qty > 0 order by item_code", as_dict=True)

print(json.dumps({"vouchers": [(v["voucher_no"], v["sle_count"]) for v in out["vouchers"]],
                  "totals": out["totals"], "task_gate": out["task_gate"],
                  "residual_wip": out["residual_wip"]}, ensure_ascii=False, indent=1))
with open("/hostshare/build94-stock-trace.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1, default=str)
