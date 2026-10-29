# BUILD-60 — AI 机器人首批安全写操作（证据）

- 日期：2026-10-29
- 分支：`product/erpnext-wecom-ai-v1-20261029`
- 站点：`erpnext-poc.localhost`（127.0.0.1:18000），公司 昆山启程智能设备有限公司
- 结论：**LOCAL_PASS（本地联调 30/30）／REAL_WECOM_BLOCKED（真实企微待外部授权）**

---

## 1. 做了什么

在不改动旧 JSH / OpenClaw 运行时的前提下，为 ERPNext 新增了一条**受控写入通道**：模型只能「提草稿」，不能「落单据」；真正写入必须由本人用一次性口令确认，且确认动作对模型不可见（不注册为工具）。

### 1.1 ERPNext 侧（新增 / 修改）
| 文件 | 作用 |
|---|---|
| `cn_mfg_poc/bot_write.py` | 机器人写操作入口：`purchase_excel_template` / `purchase_excel_preview` / `report_customer_preview`；统一复用 `bot._serve` 验签换身份 |
| `cn_mfg_poc/api.py` | 新增 `excel_template`（生成标准采购入库 Excel 模板）、`excel_parse`（安全解析+逐行校验）、`cancel_purchase_draft`、`report_customer_preview/confirm`；`prepare_purchase_draft` 增加 `source` 与来源单号落库 |
| `cn_mfg_poc/cn_mfg_poc/doctype/bot_draft/` | 新建 **Bot Draft** DocType：承载「客户报备」类待确认草稿（supplier/warehouse/lines/status/target/来源标识），带 `cancel`/`confirm` 方法与审计 Comment |
| `purchase_intake_draft.json` | 增加 `source`（来源：H5/机器人）、`source_ref`（会话/消息 ID）字段，用于幂等与追溯 |

### 1.2 适配器侧（新增）
| 文件 | 作用 |
|---|---|
| `product/adapter/erpnext-bot-tools/index.js` | 新增 `erp_excel_template`、`erp_purchase_excel_preview`、`erp_report_customer_preview` 三个**只读预览工具**；增加「本人确认口令」拦截层（`handleConfirmation`） |
| `product/adapter/erpnext-bot-tools/harness/run_write.mjs` | 写入链路本地宿主，20 项断言 |

### 1.3 复用旧 POC 的思想（不是复用旧代码 / 旧业务 ID / 直接改 MySQL）
| 旧 AIERP POC 模式 | 本任务实现 |
|---|---|
| 草稿 → 确认 → 过账分离 | Purchase Intake Draft / Bot Draft 两段式，确认前零库存变化 |
| 幂等（同一文件重发同一草稿） | `source_ref` + 文件指纹命中即返回原草稿（`W4`、`V3`） |
| 数值只来自服务端 | 预览行数、库存前后值均由 ERPNext 查询返回，模型不得编造 |
| 私聊才处理确认、群聊忽略 | `W16` 群聊口令不被处理 |
| HMAC 签名通道 | 沿用 BUILD-50 的 `X-Cn-Bot-*` 签名头 |

---

## 2. 联调结果：写入链路 20/20

日志：`docs/product/evidence/build60-bot-write.log`
命令：`cd product/adapter/erpnext-bot-tools && ERP_BOT_MEDIA_DIR=... node harness/run_write.mjs`

| # | 断言 | 结果 | 关键数据 |
|---|---|---|---|
| W1 | 生成采购入库 Excel 模板 | PASS | 返回 `.xlsx` 模板文件 |
| W2 | 有效 Excel 生成待确认草稿 | PASS | `PID-00015` |
| W3 | 预览阶段库存不变 | PASS | FASTENER 11 → 11 |
| W4 | 同一文件重发返回同一草稿（幂等） | PASS | 同一 `PID-00015` |
| W5 | 确认后生成正式采购入库单 | PASS | **MAT-PRE-2026-00010**（docstatus 1，已提交） |
| W6 | 库存按单据增加一次（+5） | PASS | 11 → 16 |
| W7 | 重复确认不重复入库 | PASS | 16 → 16，提示「此前已确认过」 |
| W8a | 物料不存在被拒 | PASS | 预览 `ok_preview=false` |
| W8b | 数量为负被拒 | PASS | 同上 |
| W8c | 无表头被拒 | PASS | 同上 |
| W8d | 供应商无效被拒 | PASS | 同上 |
| W8e | 非本公司/组仓库被拒 | PASS | 同上 |
| W9 | 取消草稿不扣库也不入库 | PASS | `PID-00016` 已取消，54 → 54 |
| W10 | 无采购/仓储角色被拒 | PASS | `PERMISSION_DENIED` |
| W11 | 客户报备生成待确认草稿 | PASS | `BD-00017` |
| W12 | 确认后生成正式报备单(Lead) | PASS | **CRM-LEAD-2026-00004** |
| W13 | 报备重复确认不重复创建 | PASS | 提示「未重复创建」 |
| W14 | 同名客户再次报备提示已存在 | PASS | 返回已有 `CRM-LEAD-2026-00004` |
| W15 | 无销售角色报备被拒 | PASS | `PERMISSION_DENIED` |
| W16 | 群聊中的确认口令不被处理 | PASS | 未触发写入 |

## 3. 数据库一致性复核：10/10

脚本：`product/scripts/build60_verify.py`（容器内 `env/bin/python`）
日志：`docs/product/evidence/build60-verify.log`

| # | 断言 | 结果 | 关键数据 |
|---|---|---|---|
| V1 | 每个已确认草稿有且只有一张已提交采购入库单 | PASS | 草稿 3 张 → 入库单 3 张（末条 MAT-PRE-2026-00010） |
| V2 | 库存增量 == 入库单数量（无重复过账/凭空增加） | PASS | Bin=15.0，Σ入库单=15.0 |
| V3 | 重复确认不再生成新入库单 | PASS | before=10 after=10，返回 already=True |
| V4 | 取消的草稿没有关联入库单（库存不变） | PASS | 取消草稿 3 张 |
| V5 | 校验失败的文件没有留下任何草稿 | PASS | 残留草稿 0 张 |
| V6 | 报备写入正式 Lead 且归属报备人本人 | PASS | CRM-LEAD-2026-00004 owner=wangming@erpnext-poc.localhost |
| V7 | 正式单据上有审计 Comment（采购入库/报备） | PASS | PR=True / Lead=True |
| V8 | 撤权前可正常生成草稿 | PASS | `PID-00018` |
| V9 | 撤权后确认被拒 | PASS | `NOT_BOUND` |
| V10 | 撤权后也不能新建草稿 | PASS | `NOT_BOUND` |

## 4. 真实写入的单据（可到 PC / H5 核对）

| 类型 | 单据号 | 状态 | 库存/归属 |
|---|---|---|---|
| 采购入库单 | MAT-PRE-2026-00010 | 已提交（docstatus 1） | FASTENER +5（11 → 16） |
| 客户报备单 | CRM-LEAD-2026-00004 | 新建，owner=wangming | 苏州新元精密机械有限公司 |
| 采购入库草稿 | PID-00015 / PID-00016(已取消) / PID-00018 | Draft / Cancelled | 预览阶段零库存变化 |
| 报备草稿 | BD-00017 | Confirmed | 已转正式 Lead |

## 5. 安全设计要点

1. **身份不靠提示词**：`wecom_userid` 经 HMAC 验签后，由 `WeCom User Binding` 换成 ERP User，再 `frappe.set_user` 执行，权限走 ERPNext 原生角色。
2. **确认动作对模型不可用**：`确认采购 xxx` / `确认报备 xxx` / `取消采购 xxx` 是适配器的消息拦截层，不是工具；模型无法自行调用。
3. **口令绑定草稿号 + 本人**：必须是**该草稿的创建者**、在**私聊**中说出口令才生效。
4. **幂等**：草稿带 `source_ref`，重复确认返回「已确认过」并回带原单号。
5. **撤权即失效**：解绑/停用后，新建草稿与确认全部返回 `NOT_BOUND`（V8→V10）。
6. **审计**：每张正式单据写入 Comment，机器人通道另有 `cn_bot.log`。

## 6. 已知限制 / 未做

- 真实企微文件消息（Excel 附件下载）依赖 Bot API 授权；当前本地联调用 `ERP_BOT_MEDIA_DIR` 指向本地样本目录模拟「文件已落到媒体目录」。
- Excel 解析用 `openpyxl` 只读取单元格值，**不执行任何公式/宏**；文件大小、行数、列头有上限校验。
- 暂不支持多币种/批次序列号入库（已登记 BACKLOG）。

## 7. 状态

- 本地：**LOCAL_PASS**（30/30）
- 真实企微：**REAL_WECOM_BLOCKED** —— 仍需用户提供的 4 项外部配置（CorpID；AgentID+Secret；可信 HTTPS 回调域名；通讯录授权），外加 Bot 接收文件消息权限。
