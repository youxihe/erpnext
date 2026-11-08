# -*- coding: utf-8 -*-
"""RELEASE-95 P0-1：BOM 缺料口径修复验证（单元 + 真实原生单据）

背景（Review 发现）：旧公式 `required - available_now - received_qty - issued_net`
把已经进入 Bin 的采购入库数量又减了一次，导致**低报缺料**。
新口径：`max(0, 需求*(1-已完工比例) - 源仓当前可用 - 已领未耗)`。

本脚本做两层验证：
1. 纯函数 `compute_shortage()` 的边界用例（无 DB 依赖）。
2. 在本地 POC Site 上对真实订单 SAL-ORD-2026-00007 造真实 Purchase Receipt /
   Work Order / Material Transfer，读取真实的 Bin 与 order_summary 结果，
   并在结束时全部 cancel，恢复原库存与缺料值。

运行：bench 环境内 python 执行，结果写 /hostshare/release95-shortage.json
"""
import json
import traceback

import frappe
from frappe.utils import add_days, today

frappe.init(site="erpnext-poc.localhost", sites_path="/workspace/development/frappe-bench/sites")
frappe.connect()
frappe.set_user("Administrator")

COMPANY = "昆山启程智能设备有限公司"
SUPPLIER = "昆山精工零部件有限公司"
SO = "SAL-ORD-2026-00007"
DONE_SO = "SAL-ORD-2026-00008"
ITEM = "RACK"
RAW = "原材料仓 - QC"
WIP = "生产在制仓 - QC"
FGWH = "产成品仓 - QC"
MARK = "RELEASE95-P01"

out = {"cases": [], "unit": [], "steps": [], "created": [], "errors": []}


def case(name, ok, detail=""):
    out["cases"].append({"name": name, "ok": bool(ok), "detail": str(detail)[:600]})
    print(("PASS " if ok else "FAIL ") + name + " | " + str(detail)[:300])


def bin_qty(item, wh):
    return float(frappe.db.get_value("Bin", {"item_code": item, "warehouse": wh},
                                     "actual_qty") or 0)


def sle_count():
    return frappe.db.count("Stock Ledger Entry")


def component(so, item):
    from cn_mfg_poc.order_execution import order_summary
    s = order_summary(so)
    for c in s["materials"]["components"]:
        if c["item_code"] == item:
            return s, c
    return s, None


def unique_suffix():
    n = frappe.db.count("Purchase Receipt", {"supplier": SUPPLIER})
    return "%s-%03d" % (MARK, n + 1)


# ---------------------------------------------------------------- 1. 纯函数单测
from cn_mfg_poc.order_execution import compute_shortage  # noqa: E402

UNIT = [
    # (说明, 参数, 期望)
    ("P0-1 核心：需求4/源仓可用2(已含收货2)/已收2/无领料 => 仍缺2", (4, 0, 2, 0), 2),
    ("库存充足：需求4/可用6 => 缺0", (4, 0, 6, 0), 0),
    ("已领未耗覆盖：需求4/可用0/已领未耗4 => 缺0", (4, 0, 0, 4), 0),
    ("已领未耗部分覆盖：需求4/可用1/已领未耗1 => 缺2", (4, 0, 1, 1), 2),
    ("整单已完工：需求4/已完工比例1 => 缺0", (4, 1.0, 0, 0), 0),
    ("部分完工50%：需求4/已完工0.5/可用0 => 缺2", (4, 0.5, 0, 0), 2),
    ("全部没有：需求4 => 缺4", (4, 0, 0, 0), 4),
    ("负数保护：可用大于需求 => 缺0", (2, 0, 5, 0), 0),
]
for desc, args, expect in UNIT:
    got = compute_shortage(*args)
    out["unit"].append({"desc": desc, "args": args, "expect": expect, "got": got})
    case("单元 " + desc, abs(got - float(expect)) < 1e-6, "expect=%s got=%s" % (expect, got))


def old_formula(required, available, received, issued_net):
    """旧实现（Review 指出的重复扣减），用于前后对照。"""
    return max(0.0, float(required) - float(available) - float(received) - float(issued_net))


# ------------------------------------------------- 2. 真实单据：基线 & 采购入库
def run():
    base_bin = bin_qty(ITEM, RAW)
    base_wip = bin_qty(ITEM, WIP)
    base_sle = sle_count()
    s0, c0 = component(SO, ITEM)
    case("基线读取 SAL-ORD-2026-00007 的 RACK 缺料",
         c0 is not None, "%s" % {k: c0 and c0.get(k) for k in
                                 ("required_qty", "remaining_qty", "available_now",
                                  "received_qty", "issued_net", "shortage")} if c0 else "无组件")
    if not c0:
        return
    base_shortage = c0["shortage"]
    case("基线：需求2/可用0 => 缺2", abs(base_shortage - 2) < 1e-6, "shortage=%s" % base_shortage)

    # --- 真采购入库 1 件（linked to SO），验证不重复扣减
    pr1 = frappe.get_doc({
        "doctype": "Purchase Receipt", "company": COMPANY, "supplier": SUPPLIER,
        "posting_date": today(), "set_warehouse": RAW,
        "remarks": unique_suffix() + " 缺料口径验证-1",
        "items": [{"item_code": ITEM, "qty": 1, "rate": 200, "warehouse": RAW,
                   "sales_order": SO}],
    })
    pr1.insert(ignore_permissions=True)
    pr1.submit()
    out["created"].append(pr1.name)

    s1, c1 = component(SO, ITEM)
    case("采购入库1件后 Bin 实际库存 +1", abs(bin_qty(ITEM, RAW) - (base_bin + 1)) < 1e-6,
         "bin %s -> %s" % (base_bin, bin_qty(ITEM, RAW)))
    case("采购入库1件后 available_now=1、received_qty=1",
         abs(c1["available_now"] - 1) < 1e-6 and abs(c1["received_qty"] - 1) < 1e-6,
         "available=%s received=%s" % (c1["available_now"], c1["received_qty"]))
    case("P0-1 修复生效：真实缺料=1（旧公式会算成0，低报缺料）",
         abs(c1["shortage"] - 1) < 1e-6 and old_formula(c1["required_qty"], c1["available_now"],
                                                        c1["received_qty"], c1["issued_net"]) == 0,
         "new=%s old=%s" % (c1["shortage"],
                            old_formula(c1["required_qty"], c1["available_now"],
                                        c1["received_qty"], c1["issued_net"])))

    # --- 再入库 1 件，缺料应归零
    pr2 = frappe.get_doc({
        "doctype": "Purchase Receipt", "company": COMPANY, "supplier": SUPPLIER,
        "posting_date": today(), "set_warehouse": RAW,
        "remarks": unique_suffix() + " 缺料口径验证-2",
        "items": [{"item_code": ITEM, "qty": 1, "rate": 200, "warehouse": RAW,
                   "sales_order": SO}],
    })
    pr2.insert(ignore_permissions=True)
    pr2.submit()
    out["created"].append(pr2.name)
    s2, c2 = component(SO, ITEM)
    case("入库2件后缺料归零", abs(c2["shortage"]) < 1e-6,
         "available=%s shortage=%s" % (c2["available_now"], c2["shortage"]))

    # --- 多订单共用库存：按交期顺序分配，不允许每单都拿同一批库存
    from cn_mfg_poc.api import materials_shortage as api_shortage
    ms = api_shortage(limit=50)
    rack_alloc = []
    for o in ms["orders"]:
        for s in o["shortages"]:
            if s["item_code"] == ITEM:
                rack_alloc.append((o["sales_order"], s.get("allocated_from_stock"),
                                   s.get("shortage")))
    total_alloc = sum(float(a[1] or 0) for a in rack_alloc)
    case("多订单共用库存：RACK 分配合计不超过当前库存",
         total_alloc <= bin_qty(ITEM, RAW) + 1e-6,
         "alloc=%s bin=%s rows=%s" % (total_alloc, bin_qty(ITEM, RAW), rack_alloc))
    case("缺料接口返回口径说明", bool(ms.get("shortage_basis")) and bool(ms.get("allocation")),
         "basis_len=%s allocation=%s" % (len(ms.get("shortage_basis") or ""), ms.get("allocation")))

    # --- 真实 Work Order + 领料，验证已领未耗抵扣缺料
    wo = frappe.get_doc({
        "doctype": "Work Order", "company": COMPANY, "production_item": "ASSY-X1",
        "bom_no": frappe.db.get_value("BOM", {"item": "ASSY-X1", "is_active": 1,
                                              "docstatus": 1, "is_default": 1}, "name"),
        "qty": 1, "sales_order": SO, "use_multi_level_bom": 0,
        "source_warehouse": RAW, "wip_warehouse": WIP, "fg_warehouse": FGWH,
        "skip_transfer": 0,
    })
    wo.insert(ignore_permissions=True)
    wo.submit()
    out["created"].append(wo.name)

    from erpnext.manufacturing.doctype.work_order.work_order import (
        make_stock_entry as wo_make_stock_entry,
    )
    se = wo_make_stock_entry(wo.name, "Material Transfer for Manufacture", 1)
    se = frappe.get_doc(se)
    se.company = COMPANY
    for row in se.items:
        row.s_warehouse = RAW
        row.t_warehouse = WIP
    se.insert(ignore_permissions=True)
    se.submit()
    out["created"].append(se.name)

    s3, c3 = component(SO, ITEM)
    case("领料2件到在制仓后 issued_net=2、源仓可用=0",
         abs(c3["issued_net"] - 2) < 1e-6 and abs(c3["available_now"]) < 1e-6,
         "issued_net=%s available=%s" % (c3["issued_net"], c3["available_now"]))
    case("已领未耗抵扣缺料：需求2全部在制 => 缺0", abs(c3["shortage"]) < 1e-6,
         "shortage=%s" % c3["shortage"])
    case("在制仓实际收到 2 件（库存权威仍走原生 Stock Entry）",
         abs(bin_qty(ITEM, WIP) - (base_wip + 2)) < 1e-6,
         "wip_bin %s -> %s" % (base_wip, bin_qty(ITEM, WIP)))

    # --- 已完工订单不再显示缺料
    sd, cd = component(DONE_SO, ITEM)
    case("已完工订单 SAL-ORD-2026-00008 剩余需求归零、缺料为0",
         cd is not None and abs(cd["remaining_qty"]) < 1e-6 and abs(cd["shortage"]) < 1e-6,
         "produced_factor=%s remaining=%s shortage=%s" % (
             cd and cd["produced_factor"], cd and cd["remaining_qty"], cd and cd["shortage"]))

    # --- 不同仓库：缺料只看 BOM 源仓，其他仓库存仅做展示（保守，不低报）
    case("缺料按 BOM 源仓判定，并单列全仓库存供对照",
         c3["warehouse"] == RAW and "stock_all_warehouses" in c3,
         "warehouse=%s all=%s" % (c3["warehouse"], c3.get("stock_all_warehouses")))

    # --- 权限：销售角色不能查缺料；生产人员只能看自己有任务的单
    frappe.set_user("wangming@erpnext-poc.localhost")
    try:
        api_shortage(limit=5)
        case("销售角色查缺料应被拒绝", False, "未抛权限异常")
    except frappe.PermissionError as e:
        case("销售角色查缺料被拒绝", True, str(e)[:120])
    finally:
        frappe.set_user("Administrator")

    return {"base_bin": base_bin, "base_sle": base_sle, "base_shortage": base_shortage,
            "docs": list(out["created"])}


def cleanup():
    """按逆序 cancel，恢复库存与缺料；任何一步失败只记录不掩盖。"""
    for name in reversed(out["created"]):
        try:
            doc = None
            for dt in ("Stock Entry", "Purchase Receipt", "Work Order"):
                if frappe.db.exists(dt, name):
                    doc = frappe.get_doc(dt, name)
                    break
            if doc is None:
                continue
            if doc.docstatus == 1:
                doc.cancel()
        except Exception as e:
            out["errors"].append("cancel %s: %r" % (name, e))
    frappe.db.commit()
    # 删除本次验证产生的已取消单据，避免 naming series 与追溯数据被测试污染
    removed = 0
    for dt in ("Stock Entry", "Purchase Receipt", "Work Order"):
        for name in frappe.get_all(dt, filters={"docstatus": 2, "name": ["in", out["created"]]},
                                   pluck="name"):
            try:
                frappe.delete_doc(dt, name, force=True, ignore_permissions=True)
                removed += 1
            except Exception as e:
                out["errors"].append("delete %s %s: %r" % (dt, name, e))
    frappe.db.commit()
    out["cleaned_docs"] = removed


try:
    run()
except Exception:
    out["errors"].append(traceback.format_exc()[-1500:])
    frappe.db.rollback()
finally:
    cleanup()
    try:
        frappe.set_user("Administrator")
        s, c = component(SO, ITEM)
        ok = abs(bin_qty(ITEM, RAW)) < 1e-6 and abs(c["shortage"] - 2) < 1e-6
        case("清理后库存与缺料恢复（RACK 源仓0、缺料2）", ok,
             "bin=%s shortage=%s docs=%s" % (bin_qty(ITEM, RAW), c["shortage"], out["created"]))
    except Exception:
        out["errors"].append(traceback.format_exc()[-800:])

    passed = sum(1 for x in out["cases"] if x["ok"])
    out["summary"] = {"pass": passed, "total": len(out["cases"]),
                      "errors": len(out["errors"])}
    with open("/hostshare/release95-shortage.json", "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=2, default=str)
    print("SUMMARY %s/%s errors=%s" % (passed, len(out["cases"]), len(out["errors"])))
    for e in out["errors"]:
        print("ERR", e[:300])
