# -*- coding: utf-8 -*-
"""BUILD-30 本地联调：企微 OAuth Mock 免登 + 绑定生命周期。仅 mock_mode=1 下可跑。"""
import io
import json
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:18000"
KEYS = json.load(io.open(r"D:/ERP/poc/share/api_keys.local.json", encoding="utf-8"))
ADMIN = KEYS["zhaojingli@erpnext-poc.localhost"]
results = []


def call(path, data=None, headers=None, expect=200, tag=""):
    url = f"{BASE}{path}"
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, method="POST" if data is not None else "GET")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        resp = opener.open(req, timeout=30)
        status, payload, cookie = resp.status, json.loads(resp.read().decode()), resp.headers.get("Set-Cookie") or ""
    except urllib.error.HTTPError as e:
        status = e.code
        try:
            payload = json.loads(e.read().decode())
        except Exception:
            payload = {}
        cookie = e.headers.get("Set-Cookie") or "" if e.headers else ""
    ok = (status == expect)
    results.append((tag, status, expect, ok))
    print(f"{'PASS' if ok else 'FAIL'} | {tag:<34} | {status} (期望 {expect})")
    return payload, cookie


# ---------------------------------------------------------------- T0 确保李工绑定启用（自举）
p, _ = call("/api/method/cn_mfg_poc.wecom.sync.sync_members",
            data={"members": [{"userid": "ligong", "name": "李工", "email": "ligong@erpnext-poc.localhost"}]},
            headers={"Authorization": f"token {ADMIN[0]}:{ADMIN[1]}"},
            expect=200, tag="T0 绑定自举(复职/启用)")
print("     └ 结果:", p["message"]["created_bindings"] or p["message"]["skipped"])

# ---------------------------------------------------------------- T1-T3 免登成功链路
p, _ = call("/api/method/cn_mfg_poc.wecom.oauth.mock_authorize?wecom_userid=ligong",
            expect=200, tag="T1 生成 mock 授权链接")
cb_url = p["message"]["mock_callback_url"]

p, cookie = call(cb_url, expect=200, tag="T2 模拟企微回调 → ERP 会话")
sid = p["message"]["sid"]
print(f"     └ 免登用户: {p['message']['user']} 角色: {[r for r in p['message']['roles'] if r in ('Manufacturing User','Sales User','Stock User')]}")

p, _ = call("/api/method/cn_mfg_poc.api.my_jobs", headers={"Cookie": f"sid={sid}"},
            expect=200, tag="T3 免登会话调用本人任务 API")
print("     └ 任务数:", len(p["message"]["jobs"]))

# ---------------------------------------------------------------- T4 未绑定成员拒绝
p, _ = call("/api/method/cn_mfg_poc.wecom.oauth.mock_authorize?wecom_userid=hacker01",
            expect=200, tag="T4a 生成未绑定成员链接")
call(p["message"]["mock_callback_url"], expect=403, tag="T4b 未绑定成员被拒")

# ---------------------------------------------------------------- T5 篡改 state 拒绝
bad = cb_url.split("state=")[0] + "state=" + cb_url.split("state=")[1][:-1] + ("0" if cb_url[-1] != "0" else "1")
call(bad, expect=403, tag="T5 篡改签名被拒")

# ---------------------------------------------------------------- T6 管理员配置/绑定接口权限
call("/api/method/cn_mfg_poc.wecom.sync.sync_members",
     data={"members": [{"userid": "x1", "name": "越权"}]},
     headers={"Authorization": f"token {KEYS['wangming@erpnext-poc.localhost'][0]}:{KEYS['wangming@erpnext-poc.localhost'][1]}"},
     expect=403, tag="T6 非管理员同步被拒")

call("/api/method/cn_mfg_poc.wecom.sync.pull_from_wecom",
     data={},
     headers={"Authorization": f"token {ADMIN[0]}:{ADMIN[1]}"},
     expect=417, tag="T7 真实同步无凭据 BLOCKED")

# ---------------------------------------------------------------- T8 停绑撤权（清会话）
p, _ = call("/api/method/cn_mfg_poc.wecom.sync.disable_binding",
            data={"wecom_userid": "ligong"},
            headers={"Authorization": f"token {ADMIN[0]}:{ADMIN[1]}"},
            expect=200, tag="T8a 管理员停用绑定")
p, _ = call("/api/method/cn_mfg_poc.wecom.oauth.mock_authorize?wecom_userid=ligong", expect=200, tag="T8b 生成链接")
call(p["message"]["mock_callback_url"], expect=403, tag="T8c 停绑后免登被拒")
call("/api/method/cn_mfg_poc.api.my_jobs", headers={"Cookie": f"sid={sid}"},
     expect=401, tag="T8d 停绑后旧会话失效(未登录)")

# ---------------------------------------------------------------- T9 恢复绑定（复职=重新启用）
p, _ = call("/api/method/cn_mfg_poc.wecom.sync.sync_members",
            data={"members": [{"userid": "ligong", "name": "李工", "email": "ligong@erpnext-poc.localhost"}]},
            headers={"Authorization": f"token {ADMIN[0]}:{ADMIN[1]}"},
            expect=200, tag="T9-0 重新同步(复职)")
print("     └ 结果:", p["message"]["created_bindings"])

p, _ = call("/api/method/cn_mfg_poc.wecom.oauth.mock_authorize?wecom_userid=ligong", expect=200, tag="T9a 恢复后生成链接")
p, _ = call(p["message"]["mock_callback_url"], expect=200, tag="T9b 恢复后免登成功")
print("     └ 免登用户:", p["message"]["user"])

print("=" * 70)
fails = [r for r in results if not r[3]]
print(f"合计 {len(results)} 项，失败 {len(fails)} 项")
if fails:
    for f in fails:
        print("  FAIL:", f)
    raise SystemExit(1)
print("BUILD-30 本地联调全部通过")
