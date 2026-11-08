# -*- coding: utf-8 -*-
"""BUILD-91 真实测试：九任务模板、一单一项目幂等、分角色权限、预警、库存解耦。

结果写 /hostshare/build91-verify.json，日志输出到 stdout。
"""
import json
import traceback

import frappe
from frappe.utils import add_days, getdate, nowdate, today

frappe.init(site="erpnext-poc.localhost", sites_path="/workspace/development/frappe-bench/sites")
frappe.connect()

from cn_mfg_poc import production  # noqa: E402

ADMIN = "Administrator"
MANAGER = "liugong@erpnext-poc.localhost"   # 刘工：Manufacturing Manager
MEMBER = "ligong@erpnext-poc.localhost"     # 李工：Employee / Manufacturing User
SALES = "wangming@erpnext-poc.localhost"    # 王明：Sales（负例）
SO = "SAL-ORD-2026-00005"                  # 生产类、未交付、未开票

out = {"steps": [], "errors": [], "ids": {}}


def step(name, ok, detail=""):
    out["steps"].append({"name": name, "ok": bool(ok), "detail": str(detail)[:500]})
    print(("PASS " if ok else "FAIL ") + name + " | " + str(detail)[:260])


def expect_denied(name, fn):
    try:
        r = fn()
        step(name, False, "未拒绝，返回=%s" % str(r)[:180])
    except Exception as e:
        msg = str(e)
        step(name, ("无权" in msg or "不是您" in msg or "PermissionError" in type(e).__name__
                    or "角色" in msg), "%s: %s" % (type(e).__name__, msg[:180]))


def as_user(user):
    frappe.set_user(user)


def stock_snapshot():
    return {
        "sle": frappe.db.count("Stock Ledger Entry"),
        "bins": frappe.db.sql(
            "select concat(item_code,'@',warehouse) k, actual_qty from tabBin order by k", as_dict=True
        ),
    }


try:
    # ------------------------------------------------------------ 1. 模板配置
    as_user(ADMIN)
    tmpl = frappe.get_doc("Project Template", production.TEMPLATE_TYPE)
    subjects = [frappe.db.get_value("Task", t.task, "subject") for t in tmpl.tasks]
    step("九阶段模板共 9 项", len(tmpl.tasks) == 9, subjects)
    step("阶段名称与决策一致", subjects == [s["subject"] for s in production.STAGES], subjects)
    step("五个最小自定义字段就位", all(
        frappe.db.exists("Custom Field", "Task-%s" % f) for f, *_ in production.CUSTOM_FIELDS
    ), [f for f, *_ in production.CUSTOM_FIELDS])

    # ------------------------------------------------------------ 2. 生产经理创建（幂等）
    as_user(MANAGER)
    try:
        created = production.create_project(SO)
        creator = MANAGER
    except Exception as e:
        out["manager_create_note"] = "%s: %s" % (type(e).__name__, str(e)[:300])
        as_user(ADMIN)
        created = production.create_project(SO)
        creator = ADMIN
    out["ids"]["created_by"] = creator
    project = created["project"]
    out["ids"]["project"] = project
    # 可重复执行：首次为新建，重跑为幂等复用，两种都必须是同一项目且 9 个任务。
    step("生产类订单建立/复用生产进度 Project",
         bool(project) and len(created.get("tasks", [])) == 9,
         "%s replayed=%s" % (project, created.get("replayed")))
    tasks = frappe.get_all(
        "Task", filters={"project": project},
        fields=["name", "subject", "exp_start_date", "exp_end_date", "production_status",
                "production_owner", "source_sales_order", "status", "template_task"],
        order_by="exp_start_date, name",
    )
    out["ids"]["tasks"] = [t["name"] for t in tasks]
    step("按模板生成 9 个 Task", len(tasks) == 9, [t["name"] for t in tasks])
    # 重跑时任务可能已被之前的验证改过状态，只校验来源订单回填与状态取值合法。
    step("Task 回填来源订单且状态合法", all(
        t["source_sales_order"] == SO
        and t["production_status"] in ("待开始", "进行中", "已完成", "异常") for t in tasks
    ), [(t["name"], t["production_status"], t["source_sales_order"]) for t in tasks[:2]])
    step("目标日期由模板 start/duration 自动计算", all(t["exp_end_date"] for t in tasks),
         [(t["subject"], str(t["exp_start_date"]), str(t["exp_end_date"])) for t in tasks[:3]])
    step("Sales Order.project 原生回写",
         frappe.db.get_value("Sales Order", SO, "project") == project,
         frappe.db.get_value("Sales Order", SO, "project"))

    # 幂等：重复点击
    before_count = frappe.db.count("Task", {"project": project})
    again = production.create_project(SO)
    after_count = frappe.db.count("Task", {"project": project})
    step("重复创建幂等（不重复生成）",
         again.get("replayed") and again["project"] == project and before_count == after_count == 9,
         "replayed=%s project=%s tasks %s->%s" % (again.get("replayed"), again["project"], before_count, after_count))

    # ------------------------------------------------------------ 3. 分派与负责人
    as_user(MANAGER)
    t_member, t_manager = tasks[0]["name"], tasks[1]["name"]
    production.assign_task(t_member, MEMBER)
    production.assign_task(t_manager, MANAGER)
    step("生产经理可分派负责人",
         frappe.db.get_value("Task", t_member, "production_owner") == MEMBER
         and frappe.db.get_value("Task", t_manager, "production_owner") == MANAGER,
         {"member_task": t_member, "manager_task": t_manager})

    # ------------------------------------------------------------ 4. 权限负例
    as_user(SALES)
    expect_denied("销售角色不能创建生产进度项目", lambda: production.create_project(SO))
    expect_denied("销售角色不能查看生产任务", lambda: production.tasks_mine())

    as_user(MEMBER)
    expect_denied("不能代他人更新任务",
                  lambda: production.tasks_update(t_manager, production_status="已完成"))
    mine = production.tasks_mine()
    step("我的任务只见本人负责", all(t["production_owner"] == MEMBER for t in mine["tasks"])
         and len(mine["tasks"]) == 1, [t["name"] for t in mine["tasks"]])

    # ------------------------------------------------------------ 5. 本人更新 + 预警
    snap_before = stock_snapshot()
    upd = production.tasks_update(t_member, production_status="进行中", note="机架已上工装")
    step("本人更新状态/备注成功", upd["production_status"] == "进行中" and upd["stock_unchanged"],
         {"task": t_member, "status": upd["production_status"], "note": upd.get("production_note")})
    step("原生 Task.status 同步映射", frappe.db.get_value("Task", t_member, "status") == "Working",
         frappe.db.get_value("Task", t_member, "status"))
    done = production.tasks_update(t_member, production_status="已完成", note="焊接完成")
    step("本人完成任务并记录完成时间",
         done["production_status"] == "已完成" and bool(done.get("completed_on")),
         {"completed_on": str(done.get("completed_on")), "native_status": done.get("status")})

    # 预警：调整目标日期（经理动作）
    as_user(MANAGER)
    yesterday = str(add_days(getdate(today()), -1))
    soon = str(add_days(getdate(today()), 2))
    later = str(add_days(getdate(today()), 10))
    production.assign_task(t_manager, MANAGER, exp_end_date=yesterday)
    production.assign_task(tasks[2]["name"], MANAGER, exp_end_date=soon)
    production.assign_task(tasks[3]["name"], MANAGER, exp_end_date=later)
    all_rows = production.tasks_mine(limit=100)
    by_name = {t["name"]: t for t in all_rows["tasks"]}
    step("逾期判定（目标日期已过且未完成）", by_name[t_manager]["due_state"] == "逾期",
         {k: by_name[k]["due_state"] for k in [t_manager, tasks[2]["name"], tasks[3]["name"]]})
    step("临期判定（3 日内，可配置）",
         by_name[tasks[2]["name"]]["due_state"] == "临期" and all_rows["due_soon_days"] == 3,
         "due_soon_days=%s" % all_rows["due_soon_days"])
    step("正常判定（3 日外）", by_name[tasks[3]["name"]]["due_state"] == "正常",
         by_name[tasks[3]["name"]]["due_state"])
    step("已完成任务不再计入逾期", by_name[t_member]["due_state"] == "已完成",
         by_name[t_member]["due_state"])
    step("汇总含逾期/临期/完成数",
         all_rows["summary"]["overdue"] >= 1 and all_rows["summary"]["due_soon"] >= 1
         and all_rows["summary"]["completed"] >= 1,
         all_rows["summary"])

    # 订单进度概览（只读）
    prog = production.order_progress(SO)
    step("订单生产进度只读聚合",
         prog["started"] and prog["total"] == 9 and prog["project"] == project,
         {"total": prog["total"], "completed": prog["completed"], "overdue": prog["overdue"], "due_soon": prog["due_soon"]})

    # ------------------------------------------------------------ 6. Gate：库存解耦
    snap_after = stock_snapshot()
    step("任务状态/分派/完成全程不改动库存与 SLE",
         snap_before["sle"] == snap_after["sle"] and snap_before["bins"] == snap_after["bins"],
         "SLE %s -> %s" % (snap_before["sle"], snap_after["sle"]))
    step("Task/Project 无库存 doc_events",
         not ((frappe.get_hooks("doc_events") or {}).get("Task")
              or (frappe.get_hooks("doc_events") or {}).get("Project")),
         "hooks.Task/Project = None")

    # 非生产类订单不生成项目
    as_user(ADMIN)
    for so_name, btype in [("SAL-ORD-2026-00002", "耗材"), ("SAL-ORD-2026-00004", "服务")]:
        try:
            production.create_project(so_name)
            step("非生产订单被拒 %s(%s)" % (so_name, btype), False, "未拒绝")
        except Exception as e:
            step("非生产订单被拒 %s(%s)" % (so_name, btype), "只有生产类" in str(e), str(e)[:120])

except Exception:
    err = traceback.format_exc()
    out["errors"].append(err)
    print("EXCEPTION\n" + err[-1800:])

out["summary"] = {
    "passed": sum(1 for s in out["steps"] if s["ok"]),
    "total": len(out["steps"]),
    "errors": len(out["errors"]),
}
with open("/hostshare/build91-verify.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1, default=str)
print("RESULT %d/%d ERRORS=%d" % (out["summary"]["passed"], out["summary"]["total"], out["summary"]["errors"]))
