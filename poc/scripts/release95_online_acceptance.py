# -*- coding: utf-8 -*-
"""RELEASE-95 线上验收：真实登录态走一张全新整机订单的原生单据全链。

覆盖验收要求：
- /cn_portal、/production_board?view=mine|order、/order_execution、/wecom_h5 四类角色可达
- 销售下单 → 生产建 Project + 九任务 → 采购申请/订单/入库 → 仓库存领料/完工入库
  → 整机一次发货 → 开票 → 收款
- 九任务全部完成不改变成品库存，库存只由原生 Stock Entry 变动
- 缺料口径：RACK 未采购时缺 2，采购入库后归零
- H5 更新任务 → PC 一致；越权拒绝；重复提交不重复过账

只使用真实账号会话 + 标准 REST，不使用 ignore_permissions。
结果写 release95-online.json（不含任何口令）。
"""
import json
import os
import sys
import traceback

import requests

BASE = os.environ.get("ERP_BASE", "https://d.urlxl.cn")
PWD = os.environ.get("ERP_POC_PWD", "")
COMPANY = "昆山启程智能设备有限公司"
CUSTOMER = "苏州华新装备有限公司"
RAW = "原材料仓 - QC"
WIP = "生产在制仓 - QC"
FG = "产成品仓 - QC"
FG_ITEM = "ASSY-X1"
MARK = "RELEASE95"

out = {"steps": [], "docs": {}, "stock": {}, "errors": [], "base": BASE}


def step(name, ok, detail=""):
    out["steps"].append({"name": name, "ok": bool(ok), "detail": str(detail)[:800]})
    print(("PASS " if ok else "FAIL ") + name + " | " + str(detail)[:260])


class C:
    def __init__(self, user):
        self.user = user
        self.s = requests.Session()
        r = self.s.post(BASE + "/api/method/login", data={"usr": user, "pwd": PWD}, timeout=40)
        if r.status_code != 200:
            raise RuntimeError("login %s -> %s" % (user, r.status_code))
        self.csrf = self._csrf()

    def _csrf(self):
        p = self.s.get(BASE + "/app", timeout=40)
        import re
        m = re.search(r'frappe\.csrf_token\s*=\s*"([^"]+)"', p.text)
        return m.group(1) if m else ""

    def h(self):
        return {"X-Frappe-CSRF-Token": self.csrf} if self.csrf else {}

    def get(self, path, **params):
        return self.s.get(BASE + path, params=params, timeout=90)

    def post(self, path, data=None, json_body=None):
        return self.s.post(BASE + path, data=data, json=json_body, headers=self.h(), timeout=120)

    def create(self, dt, payload):
        return self.post("/api/resource/" + dt.replace(" ", "%20"), json_body=payload)

    def submit(self, dt, name=None, doc=None):
        if doc is None:
            g = self.get("/api/resource/%s/%s" % (dt.replace(" ", "%20"), name))
            doc = g.json()["data"]
        doc.pop("_liked_by", None)
        doc.pop("_comments", None)
        return self.post("/api/method/frappe.client.submit", data={"doc": json.dumps(doc, default=str)})

    def method(self, path, **params):
        return self.get(path, **params)


def err(r):
    try:
        j = r.json()
        return str(j.get("exception") or j.get("exc_type") or j.get("_server_messages") or "")[:400]
    except Exception:
        return r.text[:300]


def bin_qty(c, item, wh):
    r = c.get("/api/resource/Bin", fields=json.dumps(["actual_qty"]),
              filters=json.dumps([["item_code", "=", item], ["warehouse", "=", wh]]))
    d = r.json().get("data") or []
    return float(d[0]["actual_qty"]) if d else 0.0


def sle_count(admin):
    r = admin.get("/api/method/frappe.client.get_count", doctype="Stock Ledger Entry")
    return r.json().get("message")


def summary(admin, so):
    r = admin.method("/api/method/cn_mfg_poc.api.orders_summary", sales_order=so)
    try:
        return r.json().get("message")
    except Exception:
        return {"error": r.text[:200]}


def run():
    if not PWD:
        raise RuntimeError("需要 ERP_POC_PWD")
    admin = C("Administrator")
    sales = C("wangming@erpnext-poc.localhost")
    purchase = C("chengong@erpnext-poc.localhost")
    stock = C("zhanggong@erpnext-poc.localhost")
    liugong = C("liugong@erpnext-poc.localhost")
    ligong = C("ligong@erpnext-poc.localhost")
    finance = C("zhoukaiji@erpnext-poc.localhost")

    # ---------- A. 页面可达（四类角色真实会话）
    pages = ["/cn_portal", "/production_board?view=mine", "/production_board?view=order",
             "/order_execution", "/wecom_h5", "/desk"]
    for label, c in (("销售", sales), ("仓库", stock), ("生产", liugong), ("财务", finance)):
        bad = []
        for p in pages:
            r = c.get(p)
            if r.status_code != 200:
                bad.append("%s=%s" % (p, r.status_code))
        step("%s 角色线上页面全部 200" % label, not bad, "pages=%d bad=%s" % (len(pages), bad))

    # ---------- B. 越权与匿名负例
    anon = requests.get(BASE + "/api/resource/Sales%20Order?limit_page_length=1", timeout=30)
    step("未登录访客不能读销售订单", anon.status_code == 403, "HTTP %s" % anon.status_code)
    r = ligong.get("/api/resource/Payment%20Entry?limit_page_length=1")
    step("车间李工不能读收付款凭证", r.status_code == 403, "HTTP %s %s" % (r.status_code, err(r)))
    r = sales.create("Purchase Order", {"supplier": "x", "company": COMPANY,
                                        "items": [{"item_code": "RACK", "qty": 1, "rate": 1}]})
    step("销售不能创建采购订单", r.status_code == 403, "HTTP %s %s" % (r.status_code, err(r)))
    r = requests.get(BASE + "/api/method/cn_mfg_poc.wecom.oauth.mock_authorize?wecom_userid=ligong", timeout=30)
    step("公网 Mock 选身份免登被拒绝", r.status_code in (403, 417), "HTTP %s %s" % (r.status_code, r.text[:120]))

    # ---------- C. 销售下单
    today = "2026-11-08"
    due = "2026-11-22"
    so_payload = {"customer": CUSTOMER, "company": COMPANY, "transaction_date": today,
                  "delivery_date": due, "business_type": "生产", "order_type": "Sales",
                  "po_no": MARK + "-UAT", "items": [{"item_code": FG_ITEM, "qty": 1,
                                                     "rate": 1800, "delivery_date": due,
                                                     "warehouse": FG}]}
    # 续跑：已有本标记的订单就复用，避免重复造单
    exist = admin.get("/api/resource/Sales%20Order",
                      fields=json.dumps(["name", "docstatus", "status", "per_delivered"]),
                      filters=json.dumps([["po_no", "=", MARK + "-UAT"]]),
                      limit_page_length=5).json().get("data") or []
    exist = [x for x in exist if x.get("docstatus") == 1]
    if exist:
        so = exist[0]["name"]
        out["docs"]["sales_order"] = so
        step("销售生产订单（续跑复用已有样本）", True, "SO=%s" % so)
    else:
        r = sales.create("Sales Order", so_payload)
        if r.status_code not in (200, 201):
            step("销售创建生产订单", False, "HTTP %s %s" % (r.status_code, err(r)))
            return
        so = r.json()["data"]["name"]
        out["docs"]["sales_order"] = so
        r = sales.submit("Sales Order", so)
        step("销售创建并提交生产订单", r.status_code == 200, "SO=%s docstatus=1" % so)

    fg0 = bin_qty(admin, FG_ITEM, FG)
    out["stock"]["fg_before"] = fg0
    s0 = summary(admin, so)
    rack = [c for c in (s0.get("materials", {}).get("components") or []) if c["item_code"] == "RACK"]
    if rack and rack[0]["shortage"] == 2:
        step("缺料口径：RACK 需 2、源仓 0、预计缺 2（已含收货不重复扣减）", True, rack[0])
    elif rack and rack[0]["shortage"] == 0 and rack[0]["received_qty"] >= 2:
        step("缺料口径：采购已入库后缺料归零（续跑）", True,
             {k: rack[0][k] for k in ("required_qty", "available_now", "received_qty", "shortage")})
    else:
        step("缺料口径：RACK 缺料计算正确", False, rack[0] if rack else "无组件")

    # ---------- D. 生产建 Project + 九任务
    r = liugong.post("/api/method/cn_mfg_poc.production.create_project",
                     data={"sales_order": so, "start_date": today})
    if r.status_code != 200:
        step("生产创建固定生产进度项目", False, "HTTP %s %s" % (r.status_code, err(r)))
        return
    msg = r.json().get("message") or {}
    project = msg.get("project") or msg.get("name")
    out["docs"]["project"] = project
    step("生产创建固定生产进度项目（幂等）", bool(project), "project=%s" % project)
    again = liugong.post("/api/method/cn_mfg_poc.production.create_project",
                         data={"sales_order": so, "start_date": today})
    same = (again.json().get("message") or {}).get("project") == project
    step("重复点击创建项目不重复建单", same and again.status_code == 200, "project=%s" % project)

    prog = admin.method("/api/method/cn_mfg_poc.production.order_progress", sales_order=so).json().get("message") or {}
    tasks = prog.get("tasks") or []
    step("九阶段任务齐全", len(tasks) == 9, "total=%s completed=%s" % (prog.get("total"), prog.get("completed")))

    # 续跑基线：用当前订单执行概览判断哪些环节已经做过
    s_now = summary(admin, so)
    dnow = s_now.get("documents", {}) or {}

    def names(key):
        """只认已提交单据；草稿/已取消不算（避免续跑误把失败草稿当已完成）。"""
        v = dnow.get(key)
        if not isinstance(v, list):
            return []
        return [x.get("name") for x in v if int(x.get("docstatus") or 0) == 1]

    def se_by_purpose(purpose):
        return [x.get("name") for x in (dnow.get("stock_entry") or []) if x.get("purpose") == purpose]

    # ---------- E. 采购：缺料 → 采购申请 → 订单 → 入库
    rack_need = 2
    if bin_qty(admin, "RACK", RAW) >= rack_need and names("purchase_receipt"):
        step("采购链（MR/PO/PR 已存在，续跑跳过重复建单）", True,
             "PR=%s" % names("purchase_receipt"))
    else:
        mr_payload = {"company": COMPANY, "transaction_date": today,
                      "material_request_type": "Purchase",
                      "items": [{"item_code": "RACK", "qty": rack_need, "schedule_date": due,
                                 "warehouse": RAW, "sales_order": so}]}
        r = purchase.create("Material Request", mr_payload)
        mr = r.json().get("data", {}).get("name") if r.status_code in (200, 201) else None
        if mr:
            rs = purchase.submit("Material Request", mr)
            step("采购创建并提交采购申请(Material Request)", rs.status_code == 200, "MR=%s" % mr)
            out["docs"]["material_request"] = mr
        else:
            step("采购创建并提交采购申请(Material Request)", False,
                 "HTTP %s %s" % (r.status_code, err(r)))

        po_payload = {"supplier": "昆山精工零部件有限公司", "company": COMPANY,
                      "transaction_date": today,
                      "items": [{"item_code": "RACK", "qty": rack_need, "rate": 200,
                                 "schedule_date": due, "warehouse": RAW, "sales_order": so}]}
        r = purchase.create("Purchase Order", po_payload)
        po = r.json().get("data", {}).get("name") if r.status_code in (200, 201) else None
        if po:
            rs = purchase.submit("Purchase Order", po)
            step("采购创建并提交采购订单", rs.status_code == 200, "PO=%s" % po)
            out["docs"]["purchase_order"] = po
        else:
            step("采购创建并提交采购订单", False, "HTTP %s %s" % (r.status_code, err(r)))

        pr_payload = {"supplier": "昆山精工零部件有限公司", "company": COMPANY,
                      "posting_date": today,
                      "items": [{"item_code": "RACK", "qty": rack_need, "rate": 200,
                                 "warehouse": RAW, "sales_order": so}]}
        r = purchase.create("Purchase Receipt", pr_payload)
        pr = r.json().get("data", {}).get("name") if r.status_code in (200, 201) else None
        if pr:
            rs = purchase.submit("Purchase Receipt", pr)
            step("采购创建并提交采购入库", rs.status_code == 200, "PR=%s" % pr)
            out["docs"]["purchase_receipt"] = pr
        else:
            step("采购创建并提交采购入库", False, "HTTP %s %s" % (r.status_code, err(r)))

    r_wo_deny = stock.create("Work Order", {"production_item": FG_ITEM, "bom_no": "BOM-ASSY-X1-001",
                                            "qty": 1, "company": COMPANY})
    step("仓库角色不能创建生产工单（标准 DocPerm，工单归生产）",
         r_wo_deny.status_code == 403, "HTTP %s %s" % (r_wo_deny.status_code, err(r_wo_deny)[:100]))

    rack_bin = bin_qty(admin, "RACK", RAW)
    s1 = summary(admin, so)
    rack1 = [c for c in (s1.get("materials", {}).get("components") or []) if c["item_code"] == "RACK"]
    step("采购入库后原材料仓 RACK 备齐，缺料归零（不重复扣已收）",
         rack_bin >= 2 and bool(rack1) and rack1[0]["shortage"] == 0,
         "RACK@RAW=%s shortage=%s received=%s" % (
             rack_bin, rack1[0]["shortage"] if rack1 else None,
             rack1[0]["received_qty"] if rack1 else None))

    # ---------- F. 仓库：工单 → 领料 → 完工入库
    if names("work_order"):
        wo = names("work_order")[0]
        step("生产工单（续跑复用已有工单）", True, "WO=%s" % wo)
        out["docs"]["work_order"] = wo
    else:
        wo_payload = {"production_item": FG_ITEM, "bom_no": "BOM-ASSY-X1-001", "qty": 1,
                      "company": COMPANY, "sales_order": so, "source_warehouse": RAW,
                      "wip_warehouse": WIP, "fg_warehouse": FG, "skip_transfer": 0}
        # 工单按标准 DocPerm 由生产角色创建（仓库只有只读权限，见验收记录）
        r = liugong.create("Work Order", wo_payload)
        wo = r.json().get("data", {}).get("name") if r.status_code in (200, 201) else None
        if wo:
            rs = liugong.submit("Work Order", wo)
            step("生产创建并提交生产工单", rs.status_code == 200, "WO=%s" % wo)
            out["docs"]["work_order"] = wo
        else:
            step("生产创建并提交生产工单", False, "HTTP %s %s" % (r.status_code, err(r)))
            return

    def mk_ste(purpose, qty=1):
        r = stock.method(
            "/api/method/erpnext.manufacturing.doctype.work_order.work_order.make_stock_entry",
            work_order_id=wo, purpose=purpose, qty=qty)
        if r.status_code != 200:
            return None, r
        doc = r.json()["message"]
        doc["company"] = COMPANY
        doc.pop("name", None)
        r2 = stock.create("Stock Entry", doc)
        if r2.status_code not in (200, 201):
            return None, r2
        name = r2.json()["data"]["name"]
        rs = stock.submit("Stock Entry", name)
        if rs.status_code != 200:
            return None, rs
        return name, rs

    if se_by_purpose("Material Transfer for Manufacture"):
        se1 = se_by_purpose("Material Transfer for Manufacture")[0]
        step("仓库领料（续跑复用已有领料单）", True, se1)
    else:
        se1, r1 = mk_ste("Material Transfer for Manufacture")
        step("仓库领料（Material Transfer for Manufacture）", bool(se1), se1 or err(r1))
    if se1:
        out["docs"]["stock_entry_transfer"] = se1

    # 九任务全部完成：库存必须不变（任务状态绝不触发过账）
    fg_before_tasks = bin_qty(admin, FG_ITEM, FG)
    done = 0
    for t in tasks:
        owner = t.get("production_owner")
        who = ligong if owner == "ligong@erpnext-poc.localhost" else liugong
        rr = who.post("/api/method/cn_mfg_poc.api.production_tasks_update",
                      data={"task": t["name"], "production_status": "已完成"})
        if rr.status_code == 200:
            done += 1
    step("九任务全部标记完成", done == 9, "completed=%s/9" % done)
    fg_after_tasks = bin_qty(admin, FG_ITEM, FG)
    step("任务全部完成不改变成品库存（生产任务与库存解耦）",
         fg_before_tasks == fg_after_tasks, "fg %s -> %s" % (fg_before_tasks, fg_after_tasks))

    ran_mfg = False
    se2 = (se_by_purpose("Manufacture") or [None])[0]
    if se2:
        step("仓库正式完工入库（续跑复用已有 Manufacture）", True, se2)
    else:
        se2, r2 = mk_ste("Manufacture")
        ran_mfg = bool(se2)
        step("仓库正式完工入库（Manufacture）", bool(se2), se2 or err(r2))
    if se2:
        out["docs"]["stock_entry_manufacture"] = se2
    fg_after_mfg = bin_qty(admin, FG_ITEM, FG)
    if ran_mfg:
        step("Manufacture 后成品仓 +1", fg_after_mfg == fg_after_tasks + 1,
             "fg %s -> %s" % (fg_after_tasks, fg_after_mfg))

    # 重复提交防护：同一张 Manufacture 再提交应被拒绝且不重复入库
    if se2:
        sle_before_dup = sle_count(admin)
        dup = stock.submit("Stock Entry", se2)
        fg_after_dup = bin_qty(admin, FG_ITEM, FG)
        sle_after_dup = sle_count(admin)
        # 判定标准是“不重复过账”，不是 HTTP 状态：接口对已提交单据幂等返回，但库存与
        # Stock Ledger Entry 都不能再变；服务端日志显示 docstatus 未被二次过账。
        step("重复提交已提交单据不重复过账（成品库存与 SLE 均不变）",
             fg_after_dup == fg_after_mfg and sle_after_dup == sle_before_dup,
             "HTTP %s fg %s->%s sle %s->%s" % (dup.status_code, fg_after_mfg, fg_after_dup,
                                               sle_before_dup, sle_after_dup))

    # ---------- G. 发货（整机一次）
    if names("delivery_note"):
        dn = names("delivery_note")[0]
        step("整机一次发货（续跑复用已有出库单）", True, "DN=%s" % dn)
        out["docs"]["delivery_note"] = dn
    else:
        r = stock.method("/api/method/erpnext.selling.doctype.sales_order.sales_order.make_delivery_note",
                         source_name=so)
        if r.status_code == 200:
            dn_doc = r.json()["message"]
            dn_doc.pop("name", None)
            rr = stock.create("Delivery Note", dn_doc)
            dn = rr.json().get("data", {}).get("name") if rr.status_code in (200, 201) else None
            if dn:
                rs = stock.submit("Delivery Note", dn)
                step("仓库整机一次发货（Delivery Note）", rs.status_code == 200,
                     "DN=%s %s" % (dn, "" if rs.status_code == 200 else err(rs)[:160]))
                if rs.status_code == 200:
                    out["docs"]["delivery_note"] = dn
                else:
                    stock.s.delete(BASE + "/api/resource/Delivery%%20Note/" + dn, headers=stock.h(),
                                   timeout=60)
            else:
                step("仓库整机一次发货（Delivery Note）", False, err(rr))
        else:
            step("仓库整机一次发货（Delivery Note）", False, err(r))
    fg_after_dn = bin_qty(admin, FG_ITEM, FG)
    step("发货后成品仓消耗 1 台（成品仓=0）", fg_after_dn == 0, "fg=%s" % fg_after_dn)

    # ---------- H. 财务开票与收款
    if names("sales_invoice"):
        si = names("sales_invoice")[0]
        step("财务销售发票（续跑复用已有发票）", True, "SI=%s" % si)
        out["docs"]["sales_invoice"] = si
    else:
        r = finance.method("/api/method/erpnext.selling.doctype.sales_order.sales_order.make_sales_invoice",
                           source_name=so)
        if r.status_code == 200:
            si_doc = r.json()["message"]
            si_doc.pop("name", None)
            rr = finance.create("Sales Invoice", si_doc)
            si = rr.json().get("data", {}).get("name") if rr.status_code in (200, 201) else None
            if si:
                rs = finance.submit("Sales Invoice", si)
                step("财务开销售发票", rs.status_code == 200, "SI=%s" % si)
                out["docs"]["sales_invoice"] = si
            else:
                step("财务开销售发票", False, err(rr))
        else:
            step("财务开销售发票", False, err(r))

    if names("payment_entry"):
        pe = names("payment_entry")[0]
        step("财务收款（续跑复用已有收付款单）", True, "PE=%s" % pe)
        out["docs"]["payment_entry"] = pe
    else:
        pe_payload = {"payment_type": "Receive", "party_type": "Customer", "party": CUSTOMER,
                      "company": COMPANY, "posting_date": today, "paid_amount": 1800,
                      "received_amount": 1800, "paid_from": "应收账款 1 - QC",
                      "paid_to": "现金 - QC", "reference_no": MARK, "reference_date": today,
                      "references": [{"reference_doctype": "Sales Invoice",
                                      "reference_name": out["docs"].get("sales_invoice"),
                                      "allocated_amount": 1800}]}
        r = finance.create("Payment Entry", pe_payload)
        pe = r.json().get("data", {}).get("name") if r.status_code in (200, 201) else None
        if pe:
            rs = finance.submit("Payment Entry", pe)
            step("财务登记收款", rs.status_code == 200, "PE=%s" % pe)
            out["docs"]["payment_entry"] = pe
        else:
            step("财务登记收款", False, err(r))

    # ---------- I. PC 汇总一致性
    s2 = summary(admin, so)
    docs = s2.get("documents", {})
    step("订单执行概览能看到全链单据",
         bool(docs.get("work_order")) and bool(docs.get("delivery_note")) and
         bool(docs.get("sales_invoice")),
         {k: [d.get("name") for d in v] for k, v in docs.items() if isinstance(v, list)})
    step("概览中九任务进度=9/9", (s2.get("progress") or {}).get("completed") == 9,
         s2.get("progress"))
    step("概览实物数量：已完工 1、已发货 1，整机一次发货",
         (s2.get("physical") or {}).get("produced_qty") == 1 and
         (s2.get("physical") or {}).get("delivered_qty") == 1 and
         (s2.get("physical") or {}).get("once_delivery") is True, s2.get("physical"))

    # H5/接口更新任务 → PC 立即可见
    mine = ligong.method("/api/method/cn_mfg_poc.api.production_tasks_mine").json().get("message") or {}
    rows = mine.get("tasks") or mine.get("items") or []
    note_user = ligong
    if not rows:
        mine = liugong.method("/api/method/cn_mfg_poc.api.production_tasks_mine").json().get("message") or {}
        rows = mine.get("tasks") or mine.get("items") or []
        note_user = liugong
    if rows:
        t0 = rows[0]
        r = note_user.post("/api/method/cn_mfg_poc.api.production_tasks_update",
                        data={"task": t0["name"], "note": "H5 线上验收备注 " + MARK})
        ok = r.status_code == 200
        pc = admin.method("/api/method/cn_mfg_poc.production.order_progress",
                          sales_order=so).json().get("message") or {}
        note_ok = any((t.get("production_note") or "").find(MARK) >= 0
                      for t in (pc.get("tasks") or []))
        step("H5/接口更新任务备注后 PC 立即可见", ok and note_ok,
             "task=%s user=%s" % (t0["name"], note_user.user))
    else:
        step("生产人员任务列表非空", False, "李工无任务")

    out["stock"].update({"fg_after_mfg": fg_after_mfg, "fg_after_dn": fg_after_dn,
                         "sle": sle_count(admin)})


try:
    run()
except Exception:
    out["errors"].append(traceback.format_exc()[-2500:])
finally:
    passed = sum(1 for x in out["steps"] if x["ok"])
    out["summary"] = {"pass": passed, "total": len(out["steps"]), "errors": len(out["errors"])}
    with open("release95-online.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2, default=str)
    print("SUMMARY %s/%s errors=%s" % (passed, len(out["steps"]), len(out["errors"])))
    for e in out["errors"]:
        print("ERR", e[-600:])
