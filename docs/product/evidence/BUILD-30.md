# BUILD-30 — 企业微信组织与用户身份

日期：2026-10-29 ｜ 分支：`product/erpnext-wecom-ai-v1-20261029`
结论：**LOCAL_PASS ／ REAL_WECOM_BLOCKED**。绑定→免登→会话→撤权全链路本地实测 16/16 通过；
真实企微连通需要管理员提供 4 项外部资源（见第 5 节），在提供前不标真实 PASS。

## 1. 实现（cn_mfg_poc/wecom/ + 2 个 DocType，全部 Git 携带）

| 组件 | 说明 |
|---|---|
| `WeCom Settings`（单例） | CorpID / AgentID / 通讯录 Secret（Password 加密字段）/ 可信回调域名 / 会话有效期 / Mock 模式开关 / Mock 签名密钥 |
| `WeCom User Binding` | 企微成员 UserID ↔ ERP User 唯一绑定（DB unique 约束 + 应用层冲突校验）；停用即清会话 |
| `wecom/oauth.py` | `login_url`（真实 OAuth 授权链）、`oauth_callback`（code→qyapi→userid→会话）、`mock_authorize/mock_callback`（本地联调专用，HMAC 签名 state、5 分钟有效期） |
| `wecom/sync.py` | `sync_members`（幂等绑定/复职）、`disable_binding`（停绑+清会话）、`pull_from_wecom`（真实通讯录拉取，缺凭据明确 BLOCKED）、`get_erp_user_by_wecom_userid`（BUILD-50 Bot 身份源） |

安全设计：userid 一律由服务端解析（真实模式仅来自企微 qyapi；客户端不可伪造）；未绑定/停绑/账号停用拒绝；Secret 只存密码字段；部门结构**不**自动生成任何 ERP 角色。

## 2. 本地联调结果（product/scripts/build30_test.py，16/16 PASS）

| 用例 | 结果 |
|---|---|
| T1-T3 企微成员 ligong 免登 → ERP 会话（角色 Manufacturing User）→ 调本人任务 API（2 条） | PASS |
| T4 未绑定成员 hacker01 免登 | 403 拒绝 |
| T5 篡改 state 签名 | 403 拒绝 |
| T6 非管理员（王明）调绑定管理接口 | 403 拒绝 |
| T7 真实通讯录同步无凭据 | 417 BLOCKED（明确报缺 CorpID/Secret，不造假） |
| T8 停绑撤权：免登 403、**旧会话立即失效（401 未登录）** | PASS |
| T9 复职（重新同步启用）后免登恢复 | PASS |

完整日志：`docs/product/evidence/build30-test.log`。

## 3. 现有绑定（本地演示数据）

ligong→李工、wangming-wx→王明、zhangsan→张工（CorpID=LOCAL-MOCK-CORP，Mock 模式开）。

## 4. Mock 模式边界（必须知晓）

mock_authorize 允许以任意已绑定 userid 生成免登链接 —— **仅限本地联调**。配置真实企微后关闭 Mock（`mock_mode=0`），该入口即永久 403；真实链路走 `login_url → oauth_callback`。

## 5. 需要用户介入的外部资源（真实企微 UAT 前必须）

| # | 配置项 | 放置位置 |
|---|---|---|
| 1 | 企业 ID（CorpID） | WeCom Settings·企业ID |
| 2 | 自建应用 AgentID + Secret（需通讯录与网页授权权限） | AgentID 填表单；**Secret 由管理员直接填入「通讯录 Secret」密码字段，请勿发到聊天** |
| 3 | 可信 HTTPS 回调域名（备案 + 企微后台「网页授权及 JS-SDK 可信域名」） | WeCom Settings·可信回调域名 |
| 4 | 企微后台完成自建应用配置并授权通讯录 | — |

提供后：关闭 Mock → `sync.py.pull_from_wecom` 拉真实通讯录建绑定 → 企微客户端打开 H5 实测免登 → 才能把 BUILD-30 改标 REAL_WECOM_PASS。

## 6. 复测方式

```bash
"C:\...python.exe" product/scripts/build30_test.py   # 幂等，16 项断言
# 管理界面：Administrator 登录 → 系统设置 → WeCom Settings / WeCom User Binding
```
