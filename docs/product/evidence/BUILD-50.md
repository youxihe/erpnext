# BUILD-50 — 企业微信 AI ERP 机器人只读链路

日期：2026-10-29 ｜ 分支：`product/erpnext-wecom-ai-v1-20261029`
结论：**LOCAL_PASS / REAL_WECOM_BLOCKED**。
机器人适配器与 ERPNext 受控接口已联通，16 项联调断言 + 8 项「机器人数值 == ERPNext 数据库」一致性断言全部通过；
真实企微机器人通道（企微 API 机器人/旧 OpenClaw 通道）尚未接入，故不给 REAL_WECOM_PASS。

## 1. 旧 OpenClaw 运行时调研结论（只读，未做任何修改）

调查对象：`F:\aierp-openclaw\state\extensions\aierp-erp-tools`（JSH ERP 侧，进程在跑，未触碰）+ `D:\ERP\ai-erp` 文档。

| 旧实现中值得继承的点 | 本任务的处理 |
|---|---|
| 只信任 `ctx.messageChannel === "wecom"` 的 `ctx.requesterSenderId`，群聊直接拒绝 | 原样继承（`trustedWecomUserId` / `isWecomGroupChat`） |
| 请求 HMAC-SHA256 签名（时间戳 + nonce + 密钥），密钥来自环境变量 | 继承，密钥改由 WeCom Settings Password 字段保存、适配器用 `ERP_BOT_ADAPTER_SECRET` 注入 |
| 「草稿 → 本人确认 → 过账」的 SOP，确认不交给模型 | BUILD-50 只读；确认链留到 BUILD-60 实现 |
| 数值一律来自 ERP 返回体，格式化在适配器，禁止模型估算 | 继承，并在返回文案统一标注「数据来自 ERP，非模型估算」 |
| 身份由绑定表解析，不接受提示词自报 | 继承，改用 ERPNext 侧「WeCom User Binding」（BUILD-30 成果） |

明确**没有**复用的部分：JSH 业务 ID、`/jshERP-boot` 网关、旧 MySQL 库存写入、旧 ai-erp 的任何代码文件。
新插件 id 为 `erpnext-bot-tools`，与旧 `aierp-erp-tools` 完全并列，安装到 OpenClaw 也不影响旧运行时。

## 2. 实现位置

- ERPNext 侧：`poc/apps/cn_mfg_poc/cn_mfg_poc/bot.py` → `/api/method/cn_mfg_poc.bot.*`（新增）
- 适配器侧：`product/adapter/erpnext-bot-tools/`（`index.js` 插件 + `openclaw.plugin.json` + `harness/run.mjs` 本地宿主）
- 初始化脚本：`product/scripts/build50_setup.py`、`build50_verify.py`
- 设置项：WeCom Settings 新增「AI 机器人通道」分区（启用开关 + 适配器共享密钥 Password 字段）

## 3. 三道闸（为什么模型拿不到「别人的数据」）

1. **通道闸**：适配器对 `POST\n<path>\n<ts>\n<nonce>\n<规范化参数>` 做 HMAC-SHA256 签名，±300 秒有效；
   密钥存 WeCom Settings 密码字段，适配器侧从环境变量读；签名/时间戳不对 → `BAD_SIGNATURE`（实测 T14）。
2. **账号闸**：适配器只持有 `bot-gateway@erpnext-poc.localhost` 的 API Token，该账号角色仅 `All / Guest`，无任何业务权限（实测输出 `roles ['All','Guest']`）。
3. **身份闸**：请求体只有企微 UserID，服务端用 `WeCom User Binding` 解析出 ERP User 后 `frappe.set_user`，
   再**直接调用 PC/H5 共用的 `cn_mfg_poc.api.*` 业务函数**——权限、归属、角色判断与 PC、H5 完全一致（实测 T1~T10）。

## 4. 工具与接口合同

| 工具（适配器） | ERPNext 端点 | 返回（真实数据） | 权限 |
|---|---|---|---|
| `erp_whoami` | `bot.whoami` | ERP 账号/姓名/角色/员工 | 已绑定即可 |
| `erp_stock_query` | `bot.stock_query` | 物料、仓库、数量、单位（支持中文关键字/编码/指定仓库） | 仓储/制造/系统管理 |
| `erp_my_orders` | `bot.my_orders` | 订单号、客户、金额、交付%/收款%/进度文案 | 销售角色 |
| `erp_order_progress` | `bot.order_progress` | 状态、金额、交付%/收款%、出库单、发票 | 订单归属/销售经理 |
| `erp_my_jobs` | `bot.my_jobs` | Job Card、工序、已完成/总量、待完成、状态 | 制造角色 + 在职员工 |
| `erp_mgmt_summary` | `bot.mgmt_summary` | 销售订单数/额、待交付、工单状态、库存量与价值 | 销售/仓储/制造经理、系统管理 |

统一信封：`{"ok":true,"nature":"REAL_ERP","erp_user":...,"as_of":...,"data":{...}}`；
拒绝：`{"ok":false,"code":"PERMISSION_DENIED|NOT_BOUND|BAD_SIGNATURE|BOT_DISABLED|VALIDATION","message":"..."}`。
每次调用写审计：`sites/erpnext-poc.localhost/logs/cn_bot.log`（证据 `build50-bot-audit.log`）。

## 5. 实测结果（脚本与日志）

- 联调：`product/adapter/erpnext-bot-tools/harness/run.mjs` → `docs/product/evidence/build50-bot.log`，**16/16 PASS**（exit 0）
  - 李工（制造）：我的任务 2 张（PO-JOB00003 0.5/1、PO-JOB00001 2/2）、库存「传感器（SENSOR）@生产在制仓 1 件」；销售订单、经营摘要均被拒 `PERMISSION_DENIED`
  - 王明（销售）：我的订单 5 张、`SAL-ORD-2026-00005` 状态 To Deliver and Bill / 交付 0%；车间任务被拒
  - 张工（仓储）：库存命中 SENSOR、经营摘要（近 30 天：5 单 ¥21,750、待交付 2 单 ¥2,600、库存 100 件 ¥3,330）
  - 赵经理：whoami 解析为 `zhaojingli@erpnext-poc.localhost`
  - 负例：未绑定 `weixiubao`→NOT_BOUND；群聊→不下发 ERP；非企微通道→拒绝；篡改签名→BAD_SIGNATURE
- 一致性（同一 Site 对照）：`product/scripts/build50_verify.py` → `docs/product/evidence/build50-verify.log`，**8/8 PASS**

| 项 | DB（ERPNext） | 机器人返回 |
|---|---|---|
| 库存 SENSOR | 生产在制仓 1.0 | 生产在制仓 1.0 |
| 订单 SAL-ORD-2026-00005 | To Deliver and Bill / 0% / ¥1800 | 一致 |
| 任务 PO-JOB00003 | Completed / 1.0 / 0.5 | 一致 |
| 经营摘要（全部已提交销售订单） | 5 张 / ¥21,750 | 5 张 / ¥21,750 |
| 撤权（停用绑定）→ 复权 | NOT_BOUND → 恢复 | 一致 |
| 通道开关 bot_enabled=0 | 全拒 BOT_DISABLED | 一致 |
| 只读链路不写业务数据 | Comment 157 → 157 | 一致 |

样例问答（适配器真实输出）：

```
问：传感器还有多少库存
ERPNext 实时库存：
- 传感器（SENSOR）@ 生产在制仓 - QC：1 件
共 1 行，数据来自 ERP，非模型估算。

问：SAL-ORD-2026-00005 到哪一步了
SAL-ORD-2026-00005（苏州华新装备有限公司）
状态：To Deliver and Bill · 金额 ¥1,800
交付 0% / 收款 0% — 尚未交付，待安排出库
出库单：暂无 / 发票：暂无

问：我今天有什么任务（李工）
李工的车间任务（2 张）：
- PO-JOB00003 装配 · ASSY-X1 已完成 0.5/1（待完成 0.5）· Completed
- PO-JOB00001 装配 · ASSY-X1 已完成 2/2（待完成 0）· Completed
```

## 6. 为什么不是 REAL_WECOM_PASS

真实链路还缺（沿用 BUILD-30 的结论，全部是外部授权/配置，非代码）：

1. 企业微信后台「机器人」或自建应用消息 API 的**接收消息配置**（URL + Token + EncodingAESKey）；
2. 机器人所在的**可信 HTTPS 域名/IP 白名单**（当前 Site 只有 `http://127.0.0.1:18000` 本地端口）；
3. 若走旧 OpenClaw 通道：需要 `AIERP_WECOM_BOT_ID`/`OPENCLAW_GATEWAY_TOKEN` 等旧环境凭据，且把新插件挂到 `extensions/`；
4. 真实企微成员 UserID 与当前 mock 绑定（ligong / wangming-wx / zhangsan / zhaojingli）的对齐。

当前已完成的是「ERP 侧受控能力 + 适配器代码 + 本地宿主全链路」；一旦通道配置就绪，只需在 OpenClaw 注册本插件并注入环境变量即可，不需要改 ERP 侧代码。

## 7. 复测方式

```bash
# 1) ERP 侧初始化（幂等；会轮换适配器密钥与网关 Token）
docker exec -w /workspace/development/frappe-bench poc-frappe env/bin/python /workspace/build50_setup.py

# 2) 适配器本地联调（宿主机 Node，读 D:/ERP/poc/share/bot_adapter.local.json）
cd product/adapter/erpnext-bot-tools && node harness/run.mjs

# 3) 与数据库一致性复核（容器内）
docker exec -w /workspace/development/frappe-bench poc-frappe env/bin/python /workspace/build50_verify.py
```

## 8. 遗留（已登记 BACKLOG）

- OBS-50-01：本环境 `frappe.logger` 默认级别为 ERROR，INFO 不落盘；bot 侧已改为直接写站点日志文件，BUILD-20 的 `cn_api` 日志同样问题待统一。
- OBS-50-02：适配器密钥目前由本机文件注入；真实部署应放进容器/密钥管理，并叠加来源 IP 白名单。
- OBS-50-03：`order_progress` 的「进度文案」由服务端状态推导，未纳入物流在途/部分出库的细粒度口径。
