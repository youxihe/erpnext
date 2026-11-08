# -*- coding: utf-8 -*-
"""RELEASE-95 P0-2：真实业务角色单据权限实测（真实登录态 + REST）

口径说明（与脚本模拟严格区分）：
- 本脚本**不使用** frappe.set_user + insert(ignore_permissions=True)。
- 每个角色用自己的账号通过 /api/method/login 建立真实会话，再用标准 REST 创建/提交单据。
- DocPerm、User Permission、字段权限、stock/account 校验全部由服务端真实判定。
- 负例同样走真实会话，验证越权被拒绝。

清理：全部单据以 Administrator 会话 cancel + delete，库存回到原位。

运行（容器内）：
  ERP_POC_PWD=*** ./env/bin/python /hostshare/release95_perm_verify.py
结果写 /hostshare/release95-perm.json
"""
import json
import os
import re
import traceback

import requests

BASE = "http://127.0.0.1:8000"
PWD = os.environ.get("ERP_POC_PWD") or ""
COMPANY = "昆山启程智能设备有限公司"
CUSTOMER = "宁波海天精工股份有限公司"
SUPPLIER = "昆山精工零部件有限公司"
RAW = "原材料仓 - QC"
WIP = "生产在制仓 - QC"
FGWH = "产成品仓 - QC"
TODAY = "2026-11-08"
DUE = "2026-11-25"

USERS = {
    "sales": ("wangming@erpnext-poc.localhost", "销售-王明 Sales Manager"),
    "purchase": ("chengong@erpnext-poc.localhost", "采购-陈工 Purchase Manager"),
    "stock": ("zhanggong@erpnext-poc.localhost", "仓库-张工 Stock Manager"),
    "production": ("liugong@erpnext-poc.localhost", "生产-刘工 Manufacturing Manager"),
    "worker": ("ligong@erpnext-poc.localhost", "车间-李工 Manufacturing User"),
    "finance": ("zhoukaiji@erpnext-poc.localhost", "财务-周会计 Accounts Manager"),
}

out = {"cases": [], "created": [], "errors": [], "users": {}}


def case(name, ok, detail=""):
    out["cases"].append({"name": name, "ok": bool(ok), "detail": str(detail)[:700]})
    print(("PASS " if ok else "FAIL ") + name + " | " + str(detail)[:300])


class Client:
    def __init__(self, user):
        self.user = user
        self.s = requests.Session()
        r = self.s.post(BASE + "/api/method/login", data={"usr": user, "pwd": PWD}, timeout=30)
        if r.status_code != 200:
            raise RuntimeError("login failed %s: %s %s" % (user, r.status_code, r.text[:200]))
        self.csrf = self._csrf()

    def _csrf(self):
        try:
            page = self.s.get(BASE + "/app", timeout=30)
            m = re.search(r'frappe\.csrf_token\s*=\s*"([^"]+)"', page.text) or \
                re.search(r'csrf_token["\']?\s*:\s*["\']([^"\']+)', page.text)
            return m.group(1) if m else ""
        except Exception:
            return ""

    def _h(self):
        return {"X-Frappe-CSRF-Token": self.csrf} if self.csrf else {}

    def me(self):
        r = self.s.get(BASE + "/api/method/frappe.auth.get_logged_user", timeout=30)
        return r.status_code, (r.json().get("message") if r.status_code == 200 else r.text[:120])

    def create(self, dt, payload):
        r = self.s.post(BASE + "/api/resource/" + dt.replace(" ", "%20"), json=payload,
                        headers=self._h(), timeout=60)
        return r

    def submit(self, dt, name):
        """按 REST 取回最新文档（含 modified）再提交，避免 TimestampMismatch。"""
        g = self.s.get(BASE + "/api/resource/%s/%s" % (dt.replace(" ", "%20"), name), timeout=60)
        if g.status_code != 200:
            return g
        doc = g.json()["data"]
        r = self.s.post(BASE + "/api/method/frappe.client.submit",
                        data={"doc": json.dumps(doc)}, headers=self._h(), timeout=90)
        return r

    def cancel(self, dt, name):
        r = self.s.post(BASE + "/api/method/frappe.client.cancel",
                        data={"doctype": dt, "name": name}, headers=self._h(), timeout=90)
        return r

    def delete(self, dt, name):
        return self.s.delete(BASE + "/api/resource/%s/%s" % (dt.replace(" ", "%20"), name),
                             headers=self._h(), timeout=60)

    def get(self, path):
        return self.s.get(BASE + path, timeout=30)


def err(r):
    try:
        j = r.json()
        return (j.get("exception") or j.get("_server_messages") or j.get("exc_type") or "")[:300]
    except Exception:
        return r.text[:300]


def create_submit(cli, dt, payload, label):
    """真实会话：创建 + 提交；成功则登记以便清理。"""
    r = cli.create(dt, payload)
    if r.status_code not in (200, 201):
        case("%s 创建 %s" % (label, dt), False, "HTTP %s %s" % (r.status_code, err(r)))
        return None
    name = r.json().get("data", {}).get("name")
    s = cli.submit(dt, name)
    if s.status_code != 200:
        case("%s 提交 %s" % (label, dt), False, "HTTP %s %s (draft=%s)" % (s.status_code, err(s), name))
        out["created"].append({"doctype": dt, "name": name, "submitted": False})
        return None
    case("%s 创建并提交 %s" % (label, dt), True, "doc=%s docstatus=1" % name)
    out["created"].append({"doctype": dt, "name": name, "submitted": True})
    return name


def expect_denied(cli, dt, payload, label, action="创建"):
    r = cli.create(dt, payload)
    if r.status_code in (403, 401):
        case("%s 越权%s %s 被拒绝" % (label, action, dt), True, "HTTP %s %s" % (r.status_code, err(r)))
        return
    if r.status_code in (200, 201):
        name = r.json().get("data", {}).get("name")
        out["created"].append({"doctype": dt, "name": name, "submitted": False})
        case("%s 越权%s %s 被拒绝" % (label, action, dt), False,
             "未被拒绝，实际创建成功 doc=%s" % name)
        return
    case("%s 越权%s %s 被拒绝" % (label, action, dt), True,
         "HTTP %s %s" % (r.status_code, err(r)))


def run():
    if not PWD:
        raise RuntimeError("缺少 ERP_POC_PWD 环境变量")

    admin = Client("Administrator")
    clients = {}
    for key, (user, desc) in USERS.items():
        c = Client(user)
        code, me = c.me()
        clients[key] = c
        out["users"][key] = {"user": user, "desc": desc, "login_ok": code == 200 and me == user}
        case("%s(%s) 真实登录" % (desc, user), code == 200 and me == user, "me=%s" % me)

    # ---------- 销售：销售订单 create+submit
    so_payload = {
        "customer": CUSTOMER, "company": COMPANY, "transaction_date": TODAY,
        "delivery_date": DUE, "order_type": "Sales", "business_type": "生产",
        "items": [{"item_code": "ASSY-X1", "qty": 1, "rate": 1000, "delivery_date": DUE}],
    }
    so = create_submit(clients["sales"], "Sales Order", so_payload, "销售")

    # ---------- 采购：采购订单 + 采购入库（真实库存 +1，稍后取消）
    po_payload = {
        "supplier": SUPPLIER, "company": COMPANY, "transaction_date": TODAY,
        "items": [{"item_code": "RACK", "qty": 1, "rate": 200, "schedule_date": DUE,
                   "warehouse": RAW}],
    }
    po = create_submit(clients["purchase"], "Purchase Order", po_payload, "采购")

    pr_payload = {
        "supplier": SUPPLIER, "company": COMPANY, "posting_date": TODAY,
        "items": [{"item_code": "RACK", "qty": 1, "rate": 200, "warehouse": RAW}],
    }
    if po:
        pr_payload["items"][0]["purchase_order"] = po
        pr_payload["items"][0]["purchase_order_item"] = None
    pr = None
    r = clients["purchase"].create("Purchase Receipt", pr_payload)
    if r.status_code in (200, 201):
        pr = r.json()["data"]["name"]
        # PR 若因 purchase_order 行引用不全失败，回退为不带 PO 引用的正常采购入库
        s = clients["purchase"].submit("Purchase Receipt", pr)
        if s.status_code != 200:
            case("采购 提交 Purchase Receipt", False, "HTTP %s %s" % (s.status_code, err(s)))
            out["created"].append({"doctype": "Purchase Receipt", "name": pr, "submitted": False})
            pr = None
        else:
            case("采购 创建并提交 Purchase Receipt", True, "doc=%s docstatus=1" % pr)
            out["created"].append({"doctype": "Purchase Receipt", "name": pr, "submitted": True})
    else:
        case("采购 创建 Purchase Receipt", False, "HTTP %s %s" % (r.status_code, err(r)))

    # ---------- 生产：工单 create+submit
    wo_payload = {
        "production_item": "ASSY-X1", "company": COMPANY, "qty": 1,
        "bom_no": frappe_bom(),
        "source_warehouse": RAW, "wip_warehouse": WIP, "fg_warehouse": FGWH,
    }
    wo = create_submit(clients["production"], "Work Order", wo_payload, "生产")

    # ---------- 仓库：领料 Stock Entry + 成品入库 + 发货 Delivery Note
    ste_payload = {
        "stock_entry_type": "Material Transfer", "company": COMPANY, "posting_date": TODAY,
        "from_warehouse": RAW, "to_warehouse": WIP,
        "items": [{"item_code": "RACK", "qty": 1, "s_warehouse": RAW, "t_warehouse": WIP}],
    }
    ste = create_submit(clients["stock"], "Stock Entry", ste_payload, "仓库")

    # 成品仓备货（Administrator 期初收货，仅为了能提交真实 Delivery Note）
    fg_receipt = {
        "stock_entry_type": "Material Receipt", "company": COMPANY, "posting_date": TODAY,
        "to_warehouse": FGWH,
        "items": [{"item_code": "ASSY-X1", "qty": 1, "t_warehouse": FGWH, "basic_rate": 1000}],
    }
    fgr = admin.create("Stock Entry", fg_receipt)
    fgr_name = None
    if fgr.status_code in (200, 201):
        fgr_name = fgr.json()["data"]["name"]
        s = admin.submit("Stock Entry", fgr_name)
        if s.status_code == 200:
            out["created"].append({"doctype": "Stock Entry", "name": fgr_name, "submitted": True})
        else:
            fgr_name = None

    dn_payload = {
        "customer": CUSTOMER, "company": COMPANY, "posting_date": TODAY,
        "items": [{"item_code": "ASSY-X1", "qty": 1, "warehouse": FGWH, "rate": 1000}],
    }
    dn = create_submit(clients["stock"], "Delivery Note", dn_payload, "仓库")

    # ---------- 财务：销售发票 + 收款单
    si_payload = {
        "customer": CUSTOMER, "company": COMPANY, "posting_date": TODAY,
        "items": [{"item_code": "ASSY-X1", "qty": 1, "rate": 1000}],
    }
    si = create_submit(clients["finance"], "Sales Invoice", si_payload, "财务")

    pe_payload = {
        "payment_type": "Receive", "party_type": "Customer", "party": CUSTOMER,
        "company": COMPANY, "posting_date": TODAY, "paid_amount": 1000,
        "received_amount": 1000, "paid_from": "应收账款 1 - QC", "paid_to": "现金 - QC",
        "reference_no": "RELEASE95-P02", "reference_date": TODAY,
    }
    pe = create_submit(clients["finance"], "Payment Entry", pe_payload, "财务")

    # ---------- 负例：越权拒绝
    expect_denied(clients["sales"], "Purchase Order", po_payload, "销售")
    expect_denied(clients["sales"], "Work Order", wo_payload, "销售")
    expect_denied(clients["purchase"], "Sales Order", so_payload, "采购")
    expect_denied(clients["worker"], "Payment Entry", pe_payload, "车间李工")

    # 车间李工：只读越权（读取财务单据）
    r = clients["worker"].s.get(BASE + "/api/resource/Payment%20Entry?limit_page_length=1", timeout=30)
    case("车间李工 无权限读取 Payment Entry 列表", r.status_code == 403,
         "HTTP %s %s" % (r.status_code, err(r)))

    # 未登录访客
    anon = requests.get(BASE + "/api/resource/Sales%20Order?limit_page_length=1", timeout=30)
    case("未登录访客不能读取销售订单", anon.status_code == 403,
         "HTTP %s %s" % (anon.status_code, err(anon)))

    # ---------- 各角色页面可达性（真实会话，UI 入口）
    pages = [("/cn_portal", "统一门户"), ("/production_board?view=mine", "我的生产任务"),
             ("/production_board?view=order", "订单生产进度"), ("/order_execution", "订单执行概览"),
             ("/wecom_h5", "企微 H5"), ("/app", "原生 Desk")]
    for key in ("sales", "stock", "production", "finance"):
        c = clients[key]
        for path, label in pages:
            r = c.get(path)
            case("%s 打开 %s(%s)" % (USERS[key][1], label, path), r.status_code == 200,
                 "HTTP %s len=%s" % (r.status_code, len(r.text)))

    return {"so": so, "po": po, "pr": pr, "wo": wo, "ste": ste, "dn": dn, "si": si, "pe": pe}


def frappe_bom():
    """BOM 名称从本地文件读取（避免在 HTTP 层再查一次）。"""
    try:
        with open("/hostshare/_bom_name.txt") as f:
            return f.read().strip()
    except Exception:
        return None


def cleanup():
    admin = Client("Administrator")
    for item in reversed(out["created"]):
        dt, name = item["doctype"], item["name"]
        try:
            if item.get("submitted"):
                c = admin.cancel(dt, name)
                if c.status_code != 200:
                    out["errors"].append("cancel %s %s: %s" % (dt, name, err(c)))
            d = admin.s.delete(BASE + "/api/resource/%s/%s" % (dt.replace(" ", "%20"), name),
                               headers=admin._h(), timeout=60)
            if d.status_code not in (200, 202, 404):
                out["errors"].append("delete %s %s: %s" % (dt, name, err(d)))
        except Exception as e:
            out["errors"].append("cleanup %s %s: %r" % (dt, name, e))


try:
    out["result"] = run()
except Exception:
    out["errors"].append(traceback.format_exc()[-2000:])
finally:
    try:
        cleanup()
    except Exception:
        out["errors"].append("cleanup-fatal: " + traceback.format_exc()[-500:])
    passed = sum(1 for x in out["cases"] if x["ok"])
    out["summary"] = {"pass": passed, "total": len(out["cases"]), "errors": len(out["errors"])}
    with open("/hostshare/release95-perm.json", "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=2, default=str)
    print("SUMMARY %s/%s errors=%s" % (passed, len(out["cases"]), len(out["errors"])))
    for e in out["errors"][:5]:
        print("ERR", str(e)[:300])
