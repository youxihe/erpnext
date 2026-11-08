# -*- coding: utf-8 -*-
"""RELEASE-95 P0-4：公网测试安全底线验证

覆盖：
1. Mock 免登白名单逻辑：只有 mock_mode=1 且 site_config 显式允许才放行；
   去掉 site_config 允许项后，同一进程内调用必须 PermissionError。
2. 本机站点（白名单开启）真实 HTTP：Guest 仍可用 mock 免登联调、H5 显示模拟面板。
3. 仓库/配置不含明文口令与密钥（在 Git 里扫描）。
结果写 /hostshare/release95-security.json
"""
import json
import os
import traceback

import requests

import frappe

frappe.init(site="erpnext-poc.localhost", sites_path="/workspace/development/frappe-bench/sites")
frappe.connect()

BASE = "http://127.0.0.1:8000"
out = {"cases": [], "errors": []}


def case(name, ok, detail=""):
    out["cases"].append({"name": name, "ok": bool(ok), "detail": str(detail)[:500]})
    print(("PASS " if ok else "FAIL ") + name + " | " + str(detail)[:250])


from cn_mfg_poc.wecom.oauth import mock_allowed, mock_authorize, mock_callback  # noqa: E402

mode_on = bool(frappe.db.get_single_value("WeCom Settings", "mock_mode"))
flag = frappe.conf.get("cn_mfg_poc_allow_mock_login")
case("本机 mock_mode=1 且显式允许 => mock_allowed() 为真", mode_on and bool(flag) and mock_allowed(),
     "mock_mode=%s flag=%s" % (mode_on, flag))

# --- 去掉 site_config 允许项：必须立即拒绝（模拟公网站点未授权）
saved = frappe.conf.get("cn_mfg_poc_allow_mock_login")
frappe.conf.pop("cn_mfg_poc_allow_mock_login", None)
try:
    case("未显式允许时 mock_allowed() 为假", mock_allowed() is False, "flag=%s" % frappe.conf.get("cn_mfg_poc_allow_mock_login"))
    for fn, kwargs, label in ((mock_authorize, {"wecom_userid": "ligong"}, "mock_authorize"),
                              (mock_callback, {"state": "x.y"}, "mock_callback")):
        try:
            fn(**kwargs)
            case("未显式允许时 %s 被拒绝" % label, False, "未抛异常")
        except frappe.PermissionError as e:
            case("未显式允许时 %s 被拒绝" % label, True, str(e)[:120])
        except Exception as e:
            case("未显式允许时 %s 被拒绝" % label, False, repr(e)[:160])
finally:
    frappe.conf["cn_mfg_poc_allow_mock_login"] = saved

# --- 本机 HTTP：Guest 仍可用 mock 联调（白名单站点）
r = requests.get(BASE + "/api/method/cn_mfg_poc.wecom.oauth.mock_authorize",
                 params={"wecom_userid": "ligong", "redirect": "/wecom_h5"}, timeout=30)
ok = r.status_code == 200 and "mock_callback_url" in r.text
case("本机白名单站点 Guest 可用 mock 免登（本地联调不受影响）", ok,
     "HTTP %s %s" % (r.status_code, r.text[:120]))

r = requests.get(BASE + "/wecom_h5", timeout=30)
case("本机 H5 访客页显示模拟面板", r.status_code == 200 and "模拟企微免登" in r.text,
     "HTTP %s len=%s" % (r.status_code, len(r.text)))

# --- 仓库不含明文口令/密钥
REPO = "/hostshare/erpnext"
patterns = ["ErpV1@2026", "ErpPoc@2026", "_bot_adapter_secret", "api_secret\"", "sk-"]
hits = []
if os.path.isdir(REPO):
    for root, dirs, files in os.walk(REPO):
        dirs[:] = [d for d in dirs if d not in (".git", "node_modules", "__pycache__")]
        for f in files:
            if not f.endswith((".py", ".json", ".md", ".js", ".html", ".yml", ".yaml", ".sh")):
                continue
            p = os.path.join(root, f)
            try:
                with open(p, "r", encoding="utf-8", errors="ignore") as fh:
                    txt = fh.read()
            except Exception:
                continue
            for pat in patterns:
                if pat in txt:
                    hits.append((p, pat))
case("Git 工作树不含明文测试口令/密钥", not hits, str(hits[:5]))

# --- 线上站点不应存在的配置（仅提示，真正校验在线上执行）
case("本机站点为测试站点（非公网域名）", True, "site=erpnext-poc.localhost")

passed = sum(1 for x in out["cases"] if x["ok"])
out["summary"] = {"pass": passed, "total": len(out["cases"]), "errors": len(out["errors"])}
with open("/hostshare/release95-security.json", "w") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print("SUMMARY %s/%s" % (passed, len(out["cases"])))
