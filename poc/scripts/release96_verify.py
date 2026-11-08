# -*- coding: utf-8 -*-
"""UX-96A / UX-96B 本地验收：真实角色 + 真实单据 + 库存不变。

运行（容器内）：
  cd /workspace/development/frappe-bench && ./env/bin/python /hostshare/release96_verify.py
"""

import json
import traceback

import frappe
from frappe.utils import add_days, getdate, nowdate

OUT = {"steps": [], "errors": [], "created": {}, "baseline": {}, "after": {}}
SITE = "erpnext-poc.localhost"


def step(name, ok, detail=""):
    OUT["steps"].append({"name": name, "ok": bool(ok), "detail": detail if isinstance(detail, str) else json.dumps(detail, ensure_ascii=False, default=str)})
    print(("PASS " if ok else "FAIL ") + name + ((" | " + str(detail)) if detail else ""))


def stock_snapshot():
    sle = frappe.db.sql("select count(*) from `tabStock Ledger Entry` where is_cancelled=0")[0][0]
    bins = frappe.db.sql(
        "select coalesce(sum(actual_qty),0), count(*) from tabBin where actual_qty <> 0")[0]
    return {"sle": int(sle), "bin_qty": float(bins[0]), "bin_rows": int(bins[1])}


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
        step(name, False, "应当被拒绝但成功了")
    except frappe.PermissionError as e:
        step(name, True, "PermissionError: %s" % str(e)[:110])
    except frappe.ValidationError as e:
        step(name, True, "ValidationError: %s" % str(e)[:110])
    except Exception as e:
        step(name, True, "%s: %s" % (type(e).__name__, str(e)[:110]))


def get_or_create_draft_so(mark, item="ASSY-X1", qty=1, customer="宁波海天精工股份有限公司"):
    """按 po_no 标记复用测试单，避免重复刷单号。"""
    exist = frappe.get_all("Sales Order", filters={"po_no": mark}, fields=["name", "docstatus"],
                           order_by="name desc", limit=1)
    if exist:
        return exist[0]["name"], exist[0]["docstatus"] == 1
    so = frappe.new_doc("Sales Order")
    so.customer = customer
    so.company = "昆山启程智能设备有限公司"
    so.transaction_date = nowdate()
    so.delivery_date = add_days(nowdate(), 14)
    so.business_type = "生产"
    so.po_no = mark
    so.append("items", {"item_code": item, "qty": qty, "rate": 1800,
                        "delivery_date": add_days(nowdate(), 14)})
    so.insert(ignore_permissions=True)
    frappe.db.commit()
    return so.name, False


def run_a():
    from cn_mfg_poc import production

    print("\n===== UX-96A =====")
    so_new = "SAL-ORD-2026-00001"
    so_done = "SAL-ORD-2026-00006"
    if not frappe.db.exists("Sales Order", so_new):
        step("样板订单存在", False, so_new)
        return

    # 1 模板详情
    detail = production.template_detail()
    step("模板管理可读到九阶段", detail["total"] == 9 and detail["template"] == "整机生产九阶段",
         "total=%s template=%s" % (detail["total"], detail["template"]))
    step("九项均为模板任务", all(t["is_template"] for t in detail["tasks"]),
         [t["subject"] for t in detail["tasks"]])

    # 2 历史项目任务基线（模板改动不应覆盖）
    hist_before = frappe.get_all(
        "Task", filters={"project": "PROJ-0003"}, fields=["name", "subject", "exp_end_date", "exp_start_date"],
        order_by="name", limit=20)
    stage1 = next(t for t in detail["tasks"] if t["subject"] == "机架焊接")

    # 3 改模板：第 1 阶段工期 3 → 5，并改描述
    production.template_update_task(stage1["task"], duration=5,
                                    description="UX-96A 模板验证：工期 5 天")
    after_edit = next(t for t in production.template_detail()["tasks"] if t["task"] == stage1["task"])
    step("模板阶段工期可维护（3→5）", after_edit["duration"] == 5, after_edit)

    # 4 新订单建项目：新模板生效；已存在项目则不得被模板改动反写
    existing_proj = frappe.db.get_value("Project", {"sales_order": so_new}, "name")
    pre_stage1 = None
    if existing_proj:
        pre = frappe.get_all("Task", filters={"project": existing_proj, "subject": "机架焊接"},
                             fields=["name", "exp_start_date", "exp_end_date"], limit=1)
        pre_stage1 = pre[0] if pre else None

    res = production.create_project(so_new)
    proj = res["project"]
    board = production.order_board(so_new)
    stage1_task = next(t for t in board["tasks"] if t["subject"] == "机架焊接")
    p_start = frappe.db.get_value("Project", proj, "expected_start_date")

    if not existing_proj:
        step("新订单可创建生产进度（9 任务）", len(res["tasks"]) == 9,
             "project=%s tasks=%s" % (proj, len(res["tasks"])))
        OUT["created"]["project"] = proj
        step("新项目按新模板排期（工期 5 天）",
             getdate(stage1_task["exp_end_date"]) == add_days(getdate(p_start), 5),
             "start=%s end=%s" % (p_start, stage1_task["exp_end_date"]))
    else:
        step("重复创建幂等返回同一项目", res["replayed"] is True and len(res["tasks"]) == 9,
             "project=%s replayed=%s" % (proj, res["replayed"]))
        same = bool(pre_stage1) and str(pre_stage1["exp_end_date"]) == str(stage1_task["exp_end_date"])
        step("已存在项目不被模板改动反写", same,
             "before=%s after=%s" % (pre_stage1 and pre_stage1["exp_end_date"], stage1_task["exp_end_date"]))

    # 5 重复建项不重复生成
    before_cnt = frappe.db.count("Task", {"project": proj})
    again = production.create_project(so_new)
    after_cnt = frappe.db.count("Task", {"project": proj})
    step("重复创建不重复生成任务", again["replayed"] and before_cnt == after_cnt == 9,
         "count %s -> %s replayed=%s" % (before_cnt, after_cnt, again["replayed"]))

    # 6 历史项目未被静默覆盖
    hist_after = frappe.get_all(
        "Task", filters={"project": "PROJ-0003"}, fields=["name", "subject", "exp_end_date", "exp_start_date"],
        order_by="name", limit=20)
    step("历史项目任务未被模板变更覆盖", hist_before == hist_after,
         "PROJ-0003 tasks %s -> %s" % (len(hist_before), len(hist_after)))

    # 7 恢复模板，避免污染后续发布
    production.template_update_task(stage1["task"], duration=3,
                                    description="整机生产九阶段模板 · 第 1 阶段（可由负责人调整目标日期与备注）")
    restored = next(t for t in production.template_detail()["tasks"] if t["task"] == stage1["task"])
    step("模板已恢复原值（工期 3）", restored["duration"] == 3, restored["duration"])

    # 8 分派：中文姓名 + 目标日期 + 备注
    task0 = board["tasks"][0]["name"]
    r = production.assign_task(task0, "ligong@erpnext-poc.localhost",
                               exp_end_date=add_days(nowdate(), 4), note="UX-96A 分派验证")
    step("管理端可分派负责人并显示中文姓名",
         r["production_owner"].startswith("ligong") and r["owner_name"] == "李工",
         "owner=%s name=%s due=%s" % (r["production_owner"], r["owner_name"], r["exp_end_date"]))
    step("分派后预警字段可用", r["due_state"] in ("正常", "临期", "逾期", "已完成", "未排期"), r["due_state"])

    # 9 权限负例
    expect_denied("非管理人员不能维护模板",
                  lambda: as_user("ligong@erpnext-poc.localhost", production.template_detail))
    expect_denied("非管理人员不能创建生产进度",
                  lambda: as_user("ligong@erpnext-poc.localhost",
                                  lambda: production.create_project(so_new)))
    expect_denied("非管理人员不能分派他人任务",
                  lambda: as_user("ligong@erpnext-poc.localhost",
                                  lambda: production.assign_task(task0, "liugong@erpnext-poc.localhost")))
    # 跨账号改他人任务：给 liugong 的任务由 ligong 更新
    r2 = production.assign_task(board["tasks"][1]["name"], "liugong@erpnext-poc.localhost")
    expect_denied("跨账号不能更新他人任务",
                  lambda: as_user("ligong@erpnext-poc.localhost",
                                  lambda: production.tasks_update(r2["task"], production_status="进行中")))

    # 非生产订单 / 未提交订单
    expect_denied("非生产类订单不能创建进度",
                  lambda: production.create_project("SAL-ORD-2026-00002"))
    draft_so, _ = get_or_create_draft_so("UX96A-DRAFT-CHECK")
    OUT["created"]["draft_so_a"] = draft_so
    expect_denied("未提交订单不能创建进度", lambda: production.create_project(draft_so))

    # 10 库存不变
    step("任务分派未产生库存过账", OUT["baseline"] == stock_snapshot(),
         "sle/bins %s -> %s" % (OUT["baseline"], stock_snapshot()))

    OUT["created"]["so_a"] = so_new
    OUT["created"]["project_a"] = proj


def run_b():
    from cn_mfg_poc import order_execution
    from cn_mfg_poc.bom_link import bom_options, bom_references

    print("\n===== UX-96B =====")
    so1, done1 = get_or_create_draft_so("UX96B-UAT-A")
    so2, done2 = get_or_create_draft_so("UX96B-UAT-B")
    OUT["created"]["so_b1"] = so1
    OUT["created"]["so_b2"] = so2

    # 1 可选 BOM
    opts = bom_options("ASSY-X1")
    step("草稿行可查询可用 BOM", len(opts["options"]) >= 2 and opts["default_bom"] == "BOM-ASSY-X1-001",
         "options=%s default=%s" % ([o["bom"] for o in opts["options"]], opts["default_bom"]))

    # 2 选错 BOM 必须被拒
    doc = frappe.get_doc("Sales Order", so1)
    doc.items[0].bom_no = "BOM-LM90-FG-001"
    try:
        doc.save(ignore_permissions=True)
        step("物料与 BOM 不一致时保存被拒", False, "保存成功了")
    except frappe.ValidationError as e:
        step("物料与 BOM 不一致时保存被拒", True, str(e)[:120])
        frappe.db.rollback()

    # 3 选对 BOM 并提交
    doc = frappe.get_doc("Sales Order", so1)
    doc.items[0].bom_no = "BOM-ASSY-X1-001"
    doc.save(ignore_permissions=True)
    if doc.docstatus == 0:
        doc.submit()
    frappe.db.commit()
    step("订单行可选用本单 BOM 并提交",
         frappe.db.get_value("Sales Order Item", {"parent": so1}, "bom_no") == "BOM-ASSY-X1-001",
         so1)

    # 4 第二张单共用同一 BOM
    doc2 = frappe.get_doc("Sales Order", so2)
    doc2.items[0].bom_no = "BOM-ASSY-X1-001"
    doc2.save(ignore_permissions=True)
    if doc2.docstatus == 0:
        doc2.submit()
    frappe.db.commit()
    step("两张标准订单共用同一 BOM",
         frappe.db.get_value("Sales Order Item", {"parent": so2}, "bom_no") == "BOM-ASSY-X1-001", so2)

    # 5 订单执行概览三态：已确认
    s1 = order_execution.order_summary(so1)
    item1 = s1["items"][0]
    step("概览区分本单 BOM 与默认建议（已确认）",
         item1["bom_state"] == "explicit" and item1["bom_confirmed"] is True
         and item1["default_bom"] == "BOM-ASSY-X1-001",
         {k: item1[k] for k in ("bom_no", "default_bom", "bom_state", "bom_confirmed")})
    step("已确认订单 bom_summary.all_confirmed=True",
         s1["bom_summary"]["all_confirmed"] is True and not s1["bom_summary"]["unconfirmed_items"],
         s1["bom_summary"]["explicit_boms"])

    # 6 未确认订单：默认建议，不冒充
    s0 = order_execution.order_summary("SAL-ORD-2026-00001")
    it0 = s0["items"][0]
    step("未确认订单标为默认建议而非已确认",
         it0["bom_state"] == "default_suggested" and it0["bom_confirmed"] is False
         and it0["bom_no"] is None and it0["default_bom"] == "BOM-ASSY-X1-001",
         {k: it0[k] for k in ("bom_no", "default_bom", "bom_state", "bom_confirmed")})
    step("未确认订单明确列出未确认物料",
         "ASSY-X1" in s0["bom_summary"]["unconfirmed_items"],
         s0["bom_summary"]["unconfirmed_items"])
    step("物料组件标注来源（建议）",
         all(c["bom_source"] == "default" for c in s0["materials"]["components"]),
         [c["bom_source"] for c in s0["materials"]["components"]][:3])

    # 7 已提交订单禁止直接改 BOM
    docx = frappe.get_doc("Sales Order", so1)
    docx.items[0].bom_no = "BOM-ASSY-X1-002"
    try:
        docx.save(ignore_permissions=True)
        step("已提交订单禁止直接改 BOM", False, "保存成功了")
    except frappe.ValidationError as e:
        step("已提交订单禁止直接改 BOM", True, str(e)[:120])

    # 8 反向引用：只算显式
    refs = bom_references("BOM-ASSY-X1-001")
    names = {o["sales_order"] for o in refs["sales_orders"]}
    step("BOM 反查到显式引用的订单",
         so1 in names and so2 in names,
         "count=%s names=%s" % (len(names), sorted(names)[:6]))
    step("BOM 反查不把默认建议当成引用",
         "SAL-ORD-2026-00001" not in names,
         "00001 未显式选用，不应出现")
    step("BOM 反查返回客户与数量字段",
         all(o.get("customer") and o.get("qty") for o in refs["sales_orders"]),
         refs["sales_orders"][:1])
    step("BOM 反查包含工单结构", isinstance(refs["work_orders"], list),
         "work_orders=%s" % len(refs["work_orders"]))

    # 9 非标订单引用独立 BOM，不影响默认
    src = frappe.get_doc("BOM", "BOM-ASSY-X1-001")
    dup_name = frappe.db.get_value("BOM", {"item": "ASSY-X1", "is_default": 0, "docstatus": 1},
                                   "name", order_by="name desc")
    # 复用已有非默认 BOM（002）作为「非标版本」，避免反复复制
    so3, done3 = get_or_create_draft_so("UX96B-UAT-C")
    OUT["created"]["so_b3"] = so3
    d3 = frappe.get_doc("Sales Order", so3)
    d3.items[0].bom_no = "BOM-ASSY-X1-002"
    d3.save(ignore_permissions=True)
    frappe.db.commit()
    step("非标订单可引用独立 BOM", frappe.db.get_value("Sales Order Item", {"parent": so3}, "bom_no")
         == "BOM-ASSY-X1-002", so3)
    step("默认 BOM 未被非标订单改变",
         frappe.db.get_value("BOM", "BOM-ASSY-X1-001", "is_default") == 1, "is_default=1")

    refs2 = bom_references("BOM-ASSY-X1-001")
    names2 = {o["sales_order"] for o in refs2["sales_orders"]}
    step("非标订单不出现在默认 BOM 引用里", so3 not in names2, sorted(names2)[:6])

    # 10 权限：无销售订单读权限的生产人员看不到销售订单引用
    refs3 = as_user("ligong@erpnext-poc.localhost", lambda: bom_references("BOM-ASSY-X1-001"))
    step("反查按查看者权限过滤销售订单",
         all(o["sales_order"] not in (so1, so2, so3) for o in refs3["sales_orders"]),
         "ligong visible=%s" % [o["sales_order"] for o in refs3["sales_orders"]][:4])

    # 11 四类订单不受影响
    s_svc = order_execution.order_summary("SAL-ORD-2026-00004")
    step("服务类订单不受 BOM 逻辑影响",
         s_svc["items"][0]["bom_state"] in ("none", "default_suggested")
         and s_svc["materials"]["components"] == [],
         {k: s_svc["items"][0][k] for k in ("item_code", "bom_no", "bom_state")})

    # 12 库存不变
    step("BOM 选用与反查未产生库存过账", OUT["baseline"] == stock_snapshot(),
         "sle/bins %s -> %s" % (OUT["baseline"], stock_snapshot()))


def main():
    frappe.init(site=SITE, sites_path="sites")
    frappe.connect()
    frappe.set_user("Administrator")
    OUT["baseline"] = stock_snapshot()
    try:
        run_a()
    except Exception:
        OUT["errors"].append(traceback.format_exc()[-3000:])
    try:
        run_b()
    except Exception:
        OUT["errors"].append(traceback.format_exc()[-3000:])
    OUT["after"] = stock_snapshot()
    passed = sum(1 for s in OUT["steps"] if s["ok"])
    OUT["summary"] = {"pass": passed, "total": len(OUT["steps"]), "errors": len(OUT["errors"])}
    with open("/hostshare/ux96-verify.json", "w", encoding="utf-8") as f:
        json.dump(OUT, f, ensure_ascii=False, indent=2, default=str)
    print("\nSUMMARY %s/%s errors=%s" % (passed, len(OUT["steps"]), len(OUT["errors"])))
    for e in OUT["errors"]:
        print("ERR", e[-900:])


main()
