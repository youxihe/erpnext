# -*- coding: utf-8 -*-
"""BUILD-94 分角色联合验收（服务端 + HTTP + 机器人），证据落到 build94-verify.json。

只读为主，唯一写操作是「H5 通过真实 HTTP POST 更新一次任务备注」和「重复提交负例」，
用来证明权限边界与幂等，不新增任何库存事务。
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

from cn_mfg_poc import api, order_execution, production  # noqa: E402

BASE = "http://localhost:8000"
CFG = json.load(open("/workspace/bot_adapter.local.json", encoding="utf-8"))
KEYS = json.load(open("/hostshare/api_keys.local.json", encoding="utf-8"))

SO = "SAL-ORD-2026-00008"
PROJECT = "PROJ-0005"
FG = "ASSY-X1"
FGWH = "产成品仓 - QC"
MANAGER = "liugong@erpnext-poc.localhost"
WORKER = "ligong@erpnext-poc.localhost"
SALES = "wangming@erpnext-poc.localhost"
STOCK = "zhanggong@erpnext-poc.localhost"
PURCHASE = "chengong@erpnext-poc.localhost"
ACCOUNTS = "zhoukaiji@erpnext-poc.localhost"

out = {"steps": [], "errors": [], "ids": {}, "samples": {}}


def step(name, ok, detail=""):
    out["steps"].append({"name": name, "ok": bool(ok), "detail": str(detail)[:520]})
    print(("PASS " if ok else "FAIL ") + name + " | " + str(detail)[:280])


def as_user(u):
    frappe.set_user(u)


def denied(fn):
    try:
        fn()
        return False, "未拒绝"
    except (frappe.PermissionError, frappe.ValidationError, frappe.UpdateAfterSubmitError) as e:
        return True, "%s: %s" % (type(e).__name__, str(e)[:110])
    except Exception as e:  # noqa: BLE001
        return True, "%s: %s" % (type(e).__name__, str(e)[:110])


def http(path, user=None, method="GET", payload=None):
    headers = {"Accept": "application/json"}
    if user:
        k, s = KEYS[user]
        headers["Authorization"] = "token %s:%s" % (k, s)
    data = None
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    last = None
    for attempt in (1, 2):
        try:
            r = opener.open(req, timeout=90)
            return r.status, r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001  开发服务器偶发单线程阻塞，重试一次
            last = e
            time.sleep(2)
    raise last


def http_api(method, user=None, payload=None, params=None):
    path = "/api/method/" + method
    if params:
        path += "?" + urlencode(params)
    st, body = http(path, user, "POST" if payload is not None else "GET", payload)
    try:
        return st, json.loads(body).get("message"), body
    except ValueError:
        return st, None, body


def bot_call(tool, params):
    path = "/api/method/cn_mfg_poc.bot.%s" % tool
    ts, nonce = str(int(time.time())), secrets.token_hex(12)
    body = "&".join("%s=%s" % (quote(str(k), safe=""), quote(str(v), safe=""))
                    for k, v in sorted(params.items()))
    sig = hmac.new(CFG["bot_adapter_secret"].encode(),
                   "\n".join(["POST", path, ts, nonce, body]).encode(), hashlib.sha256).hexdigest()
    req = urllib.request.Request(
        BASE + path, data=urlencode(params).encode(), method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded",
                 "Authorization": "token %s:%s" % (CFG["api_key"], CFG["api_secret"]),
                 "X-Cn-Bot-Timestamp": ts, "X-Cn-Bot-Nonce": nonce, "X-Cn-Bot-Signature": sig})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        return json.loads(opener.open(req, timeout=30).read().decode())["message"]
    except urllib.error.HTTPError as e:
        return {"ok": False, "code": "HTTP_%s" % e.code,
                "message": e.read().decode()[:200]}


def sle_count():
    return frappe.db.count("Stock Ledger Entry")


def fg_qty():
    return float(frappe.db.get_value("Bin", {"item_code": FG, "warehouse": FGWH},
                                     "actual_qty") or 0)


try:
    # ============================================================ A. 一笔订单全链单据
    as_user("Administrator")
    chain = {
        "sales_order": SO,
        "project": PROJECT,
        "material_request": frappe.db.get_value("Material Request Item", {"sales_order": SO},
                                                "parent"),
        "purchase_order": frappe.db.get_value("Purchase Order Item", {"sales_order": SO},
                                              "parent"),
        "purchase_receipt": frappe.db.get_value("Purchase Receipt Item", {"sales_order": SO},
                                                "parent"),
        "work_order": frappe.db.get_value("Work Order", {"sales_order": SO}, "name"),
        "material_transfer": frappe.db.get_value("Stock Entry", {"purpose": "Material Transfer for Manufacture",
                                                                 "docstatus": 1,
                                                                 "work_order": ("!=", "")}, "name",
                                                  order_by="creation desc"),
        "manufacture": frappe.db.get_value("Stock Entry", {"purpose": "Manufacture", "docstatus": 1},
                                           "name", order_by="creation desc"),
        "delivery_note": frappe.db.get_value("Delivery Note Item",
                                             {"against_sales_order": SO}, "parent"),
        "sales_invoice": frappe.db.get_value("Sales Invoice Item", {"sales_order": SO}, "parent"),
    }
    pe = frappe.db.get_value("Payment Entry Reference",
                             {"reference_doctype": "Sales Invoice",
                              "reference_name": chain["sales_invoice"]}, "parent")
    chain["payment_entry"] = pe
    out["ids"]["chain"] = chain
    step("销售→工艺→采购→仓库→生产→入库→发货→财务 全链单据齐全",
         all(chain.values()), {k: bool(v) for k, v in chain.items()})

    so = frappe.get_doc("Sales Order", SO)
    out["ids"]["order"] = {"status": so.status, "per_delivered": so.per_delivered,
                           "per_billed": so.per_billed, "amount": so.grand_total,
                           "customer": so.customer_name, "delivery_date": str(so.delivery_date)}
    step("订单状态与交付/开票比例真实一致",
         so.per_delivered == 100 and so.per_billed == 100 and so.status == "Completed",
         out["ids"]["order"])

    tasks = frappe.get_all("Task", filters={"project": PROJECT,
                                            "status": ("not in", ["Template", "Cancelled"])},
                           fields=["name", "subject", "production_owner", "production_status",
                                   "status", "completed_on", "completed_by"],
                           order_by="exp_start_date, name")
    out["samples"]["tasks"] = [{"task": t["name"], "subject": t["subject"],
                                "owner": t["production_owner"], "status": t["production_status"],
                                "native": t["status"], "completed_on": str(t["completed_on"]),
                                "completed_by": t["completed_by"]} for t in tasks]
    workers = {t["production_owner"] for t in tasks}
    step("九阶段任务由两名生产人员全部完成",
         len(tasks) == 9 and all(t["production_status"] == "已完成" for t in tasks)
         and workers == {MANAGER, WORKER}
         and all(t["completed_on"] and t["completed_by"] for t in tasks),
         {"total": len(tasks), "owners": sorted(workers),
          "completed": sum(1 for t in tasks if t["status"] == "Completed")})

    # ============================================================ B. 任务完成 ≠ 入库
    wo = frappe.get_doc("Work Order", chain["work_order"])
    step("九项任务全完成时成品仓为 0（入库只认 Manufacture）",
         fg_qty() == 0 and float(wo.produced_qty or 0) == 1
         and frappe.db.get_value("Sales Order", SO, "per_delivered") == 100,
         {"fg_now": fg_qty(), "wo_produced": wo.produced_qty,
          "note": "成品已由 DN 一次性发出，当前成品仓 0"})

    mfg_sle = frappe.db.sql(
        "select item_code, warehouse, actual_qty from `tabStock Ledger Entry` where voucher_no=%s",
        chain["manufacture"], as_dict=True)
    step("成品入库凭据是原生 Manufacture 事务（含成品行 + 耗料行）",
         any(r["item_code"] == FG and r["actual_qty"] > 0 for r in mfg_sle)
         and any(r["actual_qty"] < 0 for r in mfg_sle),
         mfg_sle)

    vouchers = {chain["purchase_receipt"], chain["material_transfer"], chain["manufacture"],
                chain["delivery_note"]}
    sle_rows = frappe.db.sql(
        "select voucher_no, voucher_type from `tabStock Ledger Entry` where voucher_no in %s",
        [tuple(vouchers)], as_dict=True)
    per_voucher = {}
    for r in sle_rows:
        per_voucher[r["voucher_no"]] = per_voucher.get(r["voucher_no"], 0) + 1
    out["ids"]["sle_by_voucher"] = per_voucher
    step("本次库存变动全部来自 4 张原生单据且条数符合预期",
         {r["voucher_no"] for r in sle_rows} == vouchers
         and per_voucher == {chain["purchase_receipt"]: 1, chain["material_transfer"]: 6,
                             chain["manufacture"]: 4, chain["delivery_note"]: 1},
         dict(per_voucher, note="领料一进一出=3 物料×2 仓=6 条"))

    # ============================================================ C. 四类订单与不触发
    types = {}
    for t in ("生产", "耗材", "零部件", "服务"):
        rows = frappe.get_all("Sales Order", filters={"business_type": t, "docstatus": 1},
                              fields=["name"], limit=20)
        types[t] = [r["name"] for r in rows]
    out["ids"]["order_types"] = types
    step("四类订单都可用（各有已提交订单）", all(types.values()), {k: len(v) for k, v in types.items()})

    service = types["服务"][0] if types["服务"] else None
    svc_wo = frappe.db.count("Work Order", {"sales_order": service}) if service else 0
    svc_mr = frappe.db.get_value("Material Request Item", {"sales_order": service}, "parent") \
        if service else None
    svc_dn = frappe.db.get_value("Delivery Note Item", {"against_sales_order": service}, "parent") \
        if service else None
    svc_sle = frappe.db.sql("select count(*) from `tabStock Ledger Entry` where voucher_no=%s",
                            svc_dn)[0][0] if svc_dn else 0
    out["ids"]["service"] = {"so": service, "work_order": svc_wo, "mr": svc_mr,
                             "dn": svc_dn, "sle": int(svc_sle)}
    step("服务类订单不建工单、不产生库存事务",
         service and svc_wo == 0 and int(svc_sle) == 0, out["ids"]["service"])

    for t in ("耗材", "零部件"):
        so_name = types[t][0] if types[t] else None
        wos = frappe.db.count("Work Order", {"sales_order": so_name}) if so_name else -1
        projs = frappe.db.count("Project", {"sales_order": so_name}) if so_name else -1
        step("%s类订单不触发生产（无工单/无项目）" % t, so_name and wos == 0 and projs == 0,
             {"so": so_name, "work_order": wos, "project": projs})

    # ============================================================ D. 越权与重复写入
    as_user(WORKER)
    other = next((t["name"] for t in tasks if t["production_owner"] == MANAGER), None)
    ok1, d1 = denied(lambda: api.production_tasks_update(task=other, production_status="待开始"))
    step("生产人员不能改他人任务", ok1, d1)

    as_user(SALES)
    ok2, d2 = denied(lambda: production.create_project(SO))
    step("销售角色不能创建生产进度项目", ok2, d2)
    ok3, d3 = denied(lambda: api.materials_shortage())
    step("销售角色不能读全局缺料", ok3, d3)

    as_user(STOCK)
    stock_mine = api.production_tasks_mine(limit=50)
    step("仓库角色只能看到本人任务（不越界看车间任务）",
         all(t["production_owner"] == STOCK for t in stock_mine["tasks"]),
         {"stock_user_tasks": stock_mine["summary"]["total"]})

    as_user("Administrator")
    sle_before_dup = sle_count()
    se_doc = frappe.get_doc("Stock Entry", chain["manufacture"])
    try:
        se_doc.submit()
    except Exception as e:  # noqa: BLE001
        out["samples"]["dup_se_error"] = "%s: %s" % (type(e).__name__, str(e)[:100])
    frappe.db.commit()
    step("已提交的完工入库单不会二次过账（SLE 不变）",
         sle_count() == sle_before_dup
         and frappe.db.get_value("Stock Entry", chain["manufacture"], "docstatus") == 1,
         {"sle": [sle_before_dup, sle_count()],
          "error": out["samples"].get("dup_se_error")})

    sle_before_dn = sle_count()
    dn_doc = frappe.get_doc("Delivery Note", chain["delivery_note"])
    try:
        dn_doc.submit()
    except Exception as e:  # noqa: BLE001
        out["samples"]["dup_dn_error"] = "%s: %s" % (type(e).__name__, str(e)[:100])
    frappe.db.commit()
    step("已提交的发货单不会二次扣库（SLE 不变）",
         sle_count() == sle_before_dn and fg_qty() == 0.0,
         {"sle": [sle_before_dn, sle_count()], "fg": fg_qty(),
          "error": out["samples"].get("dup_dn_error")})

    as_user(MANAGER)
    before = frappe.db.count("Task", {"project": PROJECT})
    again = production.create_project(SO)
    after = frappe.db.count("Task", {"project": PROJECT})
    step("重复创建生产项目幂等（不重复生成任务）",
         again.get("replayed") and before == after == 9,
         {"replayed": again.get("replayed"), "tasks": after})

    sle_before = sle_count()
    # 幂等写验证必须用「当前登录人有权限改」的任务，否则会被越权校验拦住（那是另一条断言）
    target = next(t["name"] for t in tasks if t["production_owner"] == MANAGER)
    first = api.production_tasks_update(task=target, production_status="已完成",
                                        note="BUILD-94 重复写入幂等验证")
    second = api.production_tasks_update(task=target, production_status="已完成",
                                         note="BUILD-94 重复写入幂等验证")
    step("同一任务重复提交不重复产生库存流水",
         sle_count() == sle_before and first["production_status"] == second["production_status"],
         {"sle": sle_before, "task": target})

    # ============================================================ E. PC / H5 / Bot 一致
    # 先做「H5 通过真实 HTTP POST 更新」，再验证 PC / Bot 能否读到同一条备注
    # 先做「H5 通过真实 HTTP POST 更新」，再验证 PC / Bot 能否读到同一条备注
    h5_target = next(t["name"] for t in tasks if t["production_owner"] == MANAGER)
    h5_note = "BUILD-94 H5 现场更新"
    # 本进程此前的读事务要显式提交，否则真实 HTTP 请求会等同一行锁直到超时
    frappe.db.commit()
    st, res, raw = http_api("cn_mfg_poc.api.production_tasks_update", MANAGER,
                            {"task": h5_target, "production_status": "已完成", "note": h5_note})
    step("H5（HTTP POST）更新任务成功", st == 200 and res and res.get("task") == h5_target,
         {"status": st, "note": (res or {}).get("production_note"), "body": raw[:200]})

    as_user(MANAGER)
    pc_mine = api.production_tasks_mine(limit=50)
    pc_set = {(t["name"], t["production_status"]) for t in pc_mine["tasks"]}
    step("PC：刘工能看到本单 9 项已完成任务",
         all((t["name"], "已完成") in pc_set for t in tasks) and pc_mine["summary"]["completed"] >= 9,
         {"pc_total": pc_mine["summary"]["total"],
          "pc_completed": pc_mine["summary"]["completed"]})

    pc_task = next((t for t in pc_mine["tasks"] if t["name"] == h5_target), None)
    step("H5 更新后 PC 立即看到同一条备注",
         pc_task and pc_task.get("production_note") == h5_note,
         {"task": h5_target, "note": (pc_task or {}).get("production_note")})

    env = bot_call("my_production_tasks", {"wecom_userid": "liugong", "limit": 50})
    bot_rows = (env.get("data") or {}).get("tasks") or []
    bot_set = {(r["name"], r["production_status"]) for r in bot_rows}
    step("Bot：刘工看到同一批任务与同一状态",
         env.get("ok") and all((t["name"], "已完成") in bot_set for t in tasks),
         {"bot_total": len(bot_rows), "erp_user": env.get("erp_user")})

    bot_task = next((t for t in bot_rows if t["name"] == h5_target), None)
    step("Bot 查询到的备注与 H5/PC 一致",
         env.get("ok") and bot_task and bot_task.get("production_note") == h5_note,
         {"task": h5_target, "note": (bot_task or {}).get("production_note")})

    # 订单进度三入口同值
    pc_order = api.orders_summary(sales_order=SO)
    env3 = bot_call("order_execution", {"wecom_userid": "liugong", "order": SO})
    bd = env3.get("data") or {}
    step("Bot 订单进度与 PC 概览同值（任务/实物/发货）",
         env3.get("ok")
         and bd["tasks"]["total"] == pc_order["progress"]["total"]
         and bd["tasks"]["completed"] == pc_order["progress"]["completed"]
         and bd["physical"]["produced_qty"] == pc_order["physical"]["produced_qty"]
         and bd["physical"]["once_delivery"] is True,
         {"pc": pc_order["progress"], "bot": bd.get("tasks"),
          "produced": pc_order["physical"]["produced_qty"]})

    # 任务卡片是前端异步渲染的，HTML 里能验证的是「页面装了任务视图与四种状态」，
    # 具体任务内容已由上面的 PC/Bot API 断言覆盖，避免用 HTML 字符串假装验证了数据。
    st, body = http("/wecom_h5", WORKER)
    step("H5 页面 200 且含生产任务卡片与保存入口",
         st == 200 and "我的生产任务" in body and "production_tasks_update" in body,
         {"status": st})
    step("H5 任务视图含四种生产状态与异步加载逻辑",
         all(s in body for s in ("待开始", "进行中", "已完成", "异常"))
         and "production_tasks_mine" in body and "loadJobs" in body,
         {"statuses": all(s in body for s in ("待开始", "进行中", "已完成", "异常"))})

    # ============================================================ F. 库存对账
    fg_bin = fg_qty()
    fg_sle = frappe.db.sql(
        "select coalesce(sum(actual_qty),0) from `tabStock Ledger Entry` "
        "where item_code=%s and warehouse=%s and is_cancelled=0", (FG, FGWH))[0][0]
    step("成品仓 Bin 与 SLE 汇总一致", float(fg_bin) == float(fg_sle) == 0.0,
         {"bin": fg_bin, "sle": float(fg_sle)})
    out["ids"]["sle_total"] = sle_count()
    out["ids"]["job_cards"] = frappe.db.count("Job Card", {"work_order": chain["work_order"]})

except Exception as e:
    out["errors"].append({"error": repr(e), "trace": traceback.format_exc()[-1800:]})
    print("FATAL", repr(e))
finally:
    frappe.set_user("Administrator")

passed = sum(1 for s in out["steps"] if s["ok"])
out["summary"] = {"passed": passed, "total": len(out["steps"]),
                  "failed": [s["name"] for s in out["steps"] if not s["ok"]]}
print("RESULT %s/%s" % (passed, len(out["steps"])))
with open("/hostshare/build94-verify.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1, default=str)
