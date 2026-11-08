# -*- coding: utf-8 -*-
"""BUILD-93 真实测试：三入口（PC/H5/Bot）共用同一套轻量契约。

覆盖：契约自检、订单执行汇总、九阶段任务（本人可见/越权拒绝/库存解耦）、
BOM 缺料、机器人签名通道与 API 数值一致。
"""
import hashlib
import hmac
import json
import secrets
import time
import traceback
import urllib.error
import urllib.request
from urllib.parse import quote, urlencode

import frappe

frappe.init(site="erpnext-poc.localhost", sites_path="/workspace/development/frappe-bench/sites")
frappe.connect()

from cn_mfg_poc import api, bot, order_execution, production  # noqa: E402

BASE = "http://127.0.0.1:8000"
CFG = json.load(open("/workspace/bot_adapter.local.json", encoding="utf-8"))

SO = "SAL-ORD-2026-00006"
PROJECT = "PROJ-0003"
MANAGER = "liugong@erpnext-poc.localhost"
MEMBER = "ligong@erpnext-poc.localhost"
SALES = "wangming@erpnext-poc.localhost"
ACCOUNTS = "zhaojingli@erpnext-poc.localhost"

out = {"steps": [], "errors": [], "ids": {}, "samples": {}}


def step(name, ok, detail=""):
    out["steps"].append({"name": name, "ok": bool(ok), "detail": str(detail)[:600]})
    print(("PASS " if ok else "FAIL ") + name + " | " + str(detail)[:300])


def denied(fn):
    """服务端拒绝即为通过：越权应抛 PermissionError，非法入参应抛 ValidationError。"""
    try:
        fn()
        return False, "未拒绝"
    except (frappe.PermissionError, frappe.ValidationError) as e:
        return True, "%s: %s" % (type(e).__name__, str(e)[:110])
    except Exception as e:  # noqa: BLE001
        return False, "%s: %s" % (type(e).__name__, str(e))[:120]


def bot_call(tool, params):
    path = "/api/method/cn_mfg_poc.bot.%s" % tool
    ts, nonce = str(int(time.time())), secrets.token_hex(12)
    body = "&".join(
        "%s=%s" % (quote(str(k), safe=""), quote(str(v), safe="")) for k, v in sorted(params.items())
    )
    sig = hmac.new(
        CFG["bot_adapter_secret"].encode(),
        "\n".join(["POST", path, ts, nonce, body]).encode(),
        hashlib.sha256,
    ).hexdigest()
    req = urllib.request.Request(
        BASE + path, data=urlencode(params).encode(), method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": "token %s:%s" % (CFG["api_key"], CFG["api_secret"]),
            "X-Cn-Bot-Timestamp": ts, "X-Cn-Bot-Nonce": nonce, "X-Cn-Bot-Signature": sig,
        },
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        return json.loads(opener.open(req, timeout=30).read().decode())["message"]
    except urllib.error.HTTPError as e:
        return {"ok": False, "code": "HTTP_%s" % e.code, "message": e.read().decode()[:200]}


def stock_snapshot():
    rows = frappe.db.sql(
        "select warehouse, sum(actual_qty) from tabBin group by warehouse", as_dict=True
    )
    return {r["warehouse"]: float(r["sum(actual_qty)"] or 0) for r in rows}


try:
    # ------------------------------------------------------------ 1. 契约自检
    frappe.set_user("Administrator")
    c = api.contracts()
    out["ids"]["contracts"] = c["contracts"]
    step("四个轻量契约已注册且指向真实端点",
         set(c["contracts"]) == {"orders.summary", "production.tasks.mine",
                                 "production.tasks.update", "materials.shortage"}
         and all(v.startswith("cn_mfg_poc.api.") for v in c["contracts"].values()),
         c["contracts"])

    # ------------------------------------------------------------ 2. orders.summary
    lst = api.orders_summary(limit=20)
    names = [o["name"] for o in lst["orders"]]
    step("orders.summary 列表返回可见生产订单",
         lst["count"] >= 2 and SO in names, names)
    detail = api.orders_summary(sales_order=SO)
    so = frappe.db.get_value("Sales Order", SO, ["status", "per_delivered", "per_billed",
                                                 "delivery_date"], as_dict=True)
    step("orders.summary 详情与销售订单一致",
         detail["order"]["status"] == so["status"]
         and detail["order"]["per_delivered"] == so["per_delivered"]
         and detail["order"]["business_type"] == "生产",
         {"api": detail["order"]["status"], "db": so["status"]})

    docs = detail["documents"]
    chain = {k: [d["name"] for d in v] for k, v in docs.items()}
    out["ids"]["vouchers"] = chain
    step("执行概览覆盖采购→领料→完工→发货→应收全链",
         all(chain[k] for k in ("purchase_receipt", "work_order", "stock_entry",
                                "delivery_note", "sales_invoice", "payment_entry")),
         {k: v for k, v in chain.items() if v})

    tasks_db = frappe.get_all("Task", filters={"project": PROJECT,
                                               "status": ("not in", ["Template", "Cancelled"])},
                              fields=["name", "status", "production_status"])
    prog = detail["progress"]
    step("任务进度来自 Project Task 实时聚合",
         prog["project"] == PROJECT and prog["total"] == len(tasks_db) == 9,
         {"project": prog["project"], "api_total": prog["total"], "db": len(tasks_db),
          "completed": prog["completed"], "overdue": prog["overdue"]})

    produced = frappe.db.sql(
        "select coalesce(sum(produced_qty),0) from `tabWork Order` where sales_order=%s", SO
    )[0][0]
    step("实物完工数量取自 Work Order，不由任务数推断",
         float(detail["physical"]["produced_qty"] or 0) == float(produced) == 1.0
         and prog["total"] == 9 and int(detail["physical"]["produced_qty"]) != prog["total"],
         {"produced_qty": detail["physical"]["produced_qty"], "task_total": prog["total"],
          "task_completed": prog["completed"]})
    step("一次发货：单张 Delivery Note 且已交付 100%",
         detail["physical"]["once_delivery"] is True and len(docs["delivery_note"]) == 1
         and so["per_delivered"] == 100,
         {"dn": chain["delivery_note"], "per_delivered": so["per_delivered"]})
    step("Job Card 为 0 张仍完成入库（轻制造口径）",
         detail["physical"]["job_cards"] == 0,
         {"job_cards": detail["physical"]["job_cards"]})

    # ------------------------------------------------------------ 3. 财务隔离
    frappe.set_user(SALES)
    sales_view = api.orders_summary(sales_order=SO)
    frappe.set_user(ACCOUNTS)
    acc_view = api.orders_summary(sales_order=SO)
    step("销售角色看不到金额（finance=None / grand_total=None）",
         sales_view["finance"] is None and sales_view["order"]["grand_total"] is None,
         {"finance": sales_view["finance"], "grand_total": sales_view["order"]["grand_total"]})
    step("财务角色可见金额与应收",
         acc_view["finance"] is not None and acc_view["order"]["grand_total"] == 5000,
         acc_view["finance"])

    # ------------------------------------------------------------ 4. production.tasks.mine
    frappe.set_user(MEMBER)
    mine = api.production_tasks_mine(limit=50)
    out["ids"]["member_tasks"] = [t["name"] for t in mine["tasks"]]
    out["samples"]["member_view"] = [
        {"task": t["name"], "subject": t["subject"], "so": t.get("source_sales_order"),
         "due_state": t["due_state"], "status": t["production_status"],
         "exp_end_date": str(t.get("exp_end_date") or "")} for t in mine["tasks"]
    ]
    step("李工（企微 ligong）能看到分派给自己的任务",
         mine["summary"]["total"] >= 3
         and all(t["production_owner"] == MEMBER for t in mine["tasks"]),
         {"total": mine["summary"]["total"],
          "subjects": [t["subject"] for t in mine["tasks"]]})
    step("任务含临期/逾期只读判定与阈值",
         mine["due_soon_days"] >= 1
         and all(t["due_state"] in ("已完成", "逾期", "临期", "正常") for t in mine["tasks"]),
         {"due_soon_days": mine["due_soon_days"],
          "states": sorted({t["due_state"] for t in mine["tasks"]})})

    frappe.set_user(SALES)
    ok_sales, msg_sales = denied(lambda: api.production_tasks_mine())
    step("销售角色不能查看生产任务", ok_sales, msg_sales)

    # ------------------------------------------------------------ 5. production.tasks.update
    frappe.set_user(MEMBER)
    target = next((t for t in mine["tasks"] if t["production_status"] != "已完成"), None)
    other = frappe.db.get_value("Task", {"project": PROJECT, "production_owner": MANAGER,
                                        "status": "Open"}, "name")
    snap_before = stock_snapshot()
    upd = api.production_tasks_update(task=target["name"], production_status="进行中",
                                      note="H5 更新：已上工装")
    snap_after = stock_snapshot()
    out["ids"]["updated_task"] = target["name"]
    step("本人可更新状态/备注（H5/Bot 同一端点）",
         upd["production_status"] == "进行中"
         and frappe.db.get_value("Task", target["name"], "production_status") == "进行中",
         {"task": target["name"], "note": upd.get("production_note")})
    step("更新后原生 Task.status 同步映射 Working",
         frappe.db.get_value("Task", target["name"], "status") == "Working",
         frappe.db.get_value("Task", target["name"], "status"))
    step("任务更新不产生任何库存变化（库存与任务解耦）",
         snap_before == snap_after,
         {"warehouses": len(snap_before), "diff": {k: (snap_before[k], snap_after.get(k))
                                                   for k in snap_before if snap_before[k] != snap_after.get(k)}})

    ok_other, msg_other = denied(lambda: api.production_tasks_update(task=other,
                                                                    production_status="已完成"))
    step("不能代他人更新任务", ok_other, msg_other)
    ok_bad, msg_bad = denied(lambda: api.production_tasks_update(task=target["name"],
                                                                production_status="随便写"))
    step("非法状态被服务端拒绝", ok_bad, msg_bad)

    # ------------------------------------------------------------ 6. materials.shortage
    demo_so = frappe.db.get_value("Sales Order", {"po_no": "BUILD93-DEMO"}, "name")
    frappe.set_user(MANAGER)
    short = api.materials_shortage(limit=20)
    out["ids"]["demo_order"] = demo_so
    out["samples"]["shortage"] = [
        {"so": o["sales_order"], "customer": o["customer"],
         "items": [(c["item_code"], c["required_qty"], c["available_now"], c["shortage"])
                   for c in o["shortages"]]} for o in short["orders"]
    ]
    demo_short = next((o for o in short["orders"] if o["sales_order"] == demo_so), None)
    rack = next((c for c in (demo_short or {}).get("shortages", [])
                 if c["item_code"] == "RACK"), None)
    step("缺料契约按 BOM 差额算出真实缺料（尚未采购的订单）",
         demo_short is not None and rack is not None and rack["shortage"] >= 1.0
         and rack["shortage"] == rack["required_qty"] - rack["available_now"],
         {"so": demo_so, "rack": rack and {k: rack[k] for k in ("item_code", "required_qty",
                                                                "available_now", "shortage")},
          "count": short["count"]})

    frappe.set_user(MEMBER)
    member_short = api.materials_shortage(limit=20)
    step("普通生产人员只看到自己有任务的订单缺料",
         member_short["count"] >= 1
         and all(frappe.db.exists("Task", {"source_sales_order": o["sales_order"],
                                           "production_owner": MEMBER,
                                           "status": ("not in", ["Template", "Cancelled"])})
                 for o in member_short["orders"]),
         {"count": member_short["count"], "orders": [o["sales_order"]
                                                     for o in member_short["orders"]]})

    frappe.set_user(SALES)
    ok_short, msg_short = denied(lambda: api.materials_shortage())
    step("销售角色不能查看全局缺料清单", ok_short, msg_short)

    # ------------------------------------------------------------ 7. Bot 通道一致性
    env = bot_call("order_execution", {"wecom_userid": "ligong", "order": SO})
    data = env.get("data") or {}
    step("Bot 订单进度 == API 同一数值（任务/实物/发货）",
         env.get("ok") and data.get("sales_order") == SO
         and data["tasks"]["total"] == prog["total"]
         and data["physical"]["produced_qty"] == detail["physical"]["produced_qty"]
         and data["physical"]["once_delivery"] is True,
         {"ok": env.get("ok"), "erp_user": env.get("erp_user"),
          "tasks": data.get("tasks"), "physical": data.get("physical")})

    env2 = bot_call("my_production_tasks", {"wecom_userid": "ligong", "limit": 20})
    d2 = env2.get("data") or {}
    step("Bot 我的任务 == API 本人任务数",
         env2.get("ok") and d2.get("summary", {}).get("total") == mine["summary"]["total"],
         {"bot_total": d2.get("summary", {}).get("total"),
          "api_total": mine["summary"]["total"],
          "first": (d2.get("tasks") or [{}])[0].get("subject")})

    env3 = bot_call("materials_shortage", {"wecom_userid": "ligong", "limit": 10})
    d3 = env3.get("data") or {}
    step("Bot 缺料 == API 同一用户同一批订单",
         env3.get("ok") and d3.get("count") == member_short["count"]
         and d3.get("count") >= 1,
         {"bot": d3.get("count"), "api_member": member_short["count"]})

    env4 = bot_call("order_execution", {"wecom_userid": "nobody", "order": SO})
    step("Bot 未绑定企微成员被拒绝（NOT_BOUND）",
         env4.get("ok") is False and env4.get("code") in ("NOT_BOUND", "PERMISSION_DENIED"),
         {"code": env4.get("code"), "message": (env4.get("message") or "")[:80]})

    env5 = bot_call("my_production_tasks", {"wecom_userid": "wangming-wx"})
    step("Bot 销售角色查任务被拒绝（权限与 PC 一致）",
         env5.get("ok") is False and env5.get("code") == "PERMISSION_DENIED",
         {"code": env5.get("code"), "erp_user": env5.get("erp_user")})

    # ------------------------------------------------------------ 8. 四类订单不回退
    frappe.set_user("Administrator")
    types = {}
    for t in ("生产", "耗材", "零部件", "服务"):
        types[t] = frappe.db.count("Sales Order", {"business_type": t, "docstatus": 1})
    step("四类订单入口数据未回退", all(v >= 1 for v in types.values()), types)

except Exception as e:
    out["errors"].append({"error": repr(e), "trace": traceback.format_exc()[-1500:]})
    print("FATAL", repr(e))
finally:
    frappe.set_user("Administrator")

passed = sum(1 for s in out["steps"] if s["ok"])
out["summary"] = {"passed": passed, "total": len(out["steps"]),
                  "failed": [s["name"] for s in out["steps"] if not s["ok"]]}
print("RESULT %s/%s" % (passed, len(out["steps"])))
print(json.dumps({"summary": out["summary"], "ids": out["ids"]}, ensure_ascii=False, indent=1))
with open("/hostshare/build93-verify.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1, default=str)
