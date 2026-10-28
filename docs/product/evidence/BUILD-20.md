# BUILD-20 — 三入口共用业务 API

日期：2026-10-29 ｜ 分支：`product/erpnext-wecom-ai-v1-20261029`
结论：**PASS（LOCAL）**。统一 API 全部落到 ERPNext 原生单据；21 项合同回放（含真实写入、幂等、9 类拒绝）全部通过。

## 1. 实现位置

- 模块：`poc/apps/cn_mfg_poc/cn_mfg_poc/api.py`（Git 携带），路径前缀 `/api/method/cn_mfg_poc.api.*`
- 草稿载体：新 DocType **Purchase Intake Draft**（`cn_mfg_poc/doctype/purchase_intake_draft/`，权限=Stock/User/Manager/System Manager）
- 身份：Frappe Token 认证（`Authorization: token <api_key>:<api_secret>`）或会话 Cookie；后续企微 OAuth（BUILD-30）映射到同一 ERP User。**全程不使用 Administrator 共享 Token**。

## 2. 首批接口合同

| 接口 | 方法 | 角色（服务端校验） | 数据落点 | 幂等/防重 |
|---|---|---|---|---|
| `report_customer(customer_name, contact_name?, mobile_no?)` | POST | Sales User/Manager、System Manager + Lead create | 原生 **Lead**（报备人=当前用户） | 同名正式客户/未关闭报备 → 返回 existing 不重复建 |
| `search_customers(q)` | GET | 同上（读权限内） | Customer + Lead 只读 | — |
| `my_orders()` / `order_detail(name)` | GET | Sales User/Manager + SO read | Sales Order 只读 | 非管理角色仅限本人单据（owner） |
| `my_jobs()` | GET | Manufacturing User/Manager、System Manager | Job Card 只读 | 指派多选+实际工时按 `Employee.user_id=当前用户` 服务端过滤 |
| `update_job_progress(job_card, qty)` | POST | 同上 + 必须绑定在职员工 | 原生 start_timer/complete_job_card，全量完成自动提交 | 分配给他人 → 403；已完成/超量 → 417；只接受本人 |
| `stock_balances(warehouse?, item?)` | GET | Stock/Manufacturing User/Manager、System Manager | Bin 只读 | 销售等角色 403 |
| `prepare_purchase_draft(supplier, lines, warehouse?)` | POST | Stock User/Manager、System Manager | **Purchase Intake Draft**(Draft) | 逐行校验物料/供应商/仓库/数量单价，不动库存 |
| `confirm_purchase_draft(draft)` | POST | 同上 | 原生 **Purchase Receipt** 提交过账 | 已确认草稿重复确认 → 返回原单，不再过账 |

审计：写入动作在目标单据留 `[API] 用户 · 动作 · 细节` Comment + `cn_api` 文件日志（不含密钥/敏感内容）。

## 3. 真实回放结果（product/scripts/build20_replay.py，21/21 PASS）

- **李工**（token）：`my_jobs` 只见本人 2 任务 → `update_job_progress(PO-JOB00003, 0.5)` **真实报工完成** → 状态 Completed（auto 提交）；重复报工 417；替张工报工（PO-JOB00002）403「未分配给您」；超量报工 417；报备客户/查订单 403。
- **王明**（token）：查客户命中宁波海天精工；**报备 CRM-LEAD-2026-00002 苏州瑞丰自动化设备有限公司**（真实写入）；重复报备返回同一单（幂等）；`my_orders` 4 张；查库存/报工 403。
- **张工**（token）：查原材料仓 OK；**草稿 PID-00001（FASTENER×10 @5）→ 确认 → 采购入库单 MAT-PRE-2026-00003 真实过账**；重复确认返回原单不重复入库；库存 0→10 仅一次；无效物料/无效供应商 417。
- **李工建采购草稿** 403；**匿名调用** 403。
- 完整逐条输出：`docs/product/evidence/build20-replay.log`。

## 4. PC/H5/Bot 同源验证

- API 报备的客户与 PC 同库：`Customer` 列表实时可见（宁波海天精工由 BUILD-10 PC 报备转化、苏州瑞丰由 API 报备，均在 `frappe.get_all('Customer')`）。
- 李工 API 报工后，PC「我的车间任务」报表同一时刻显示 Completed —— 三入口读同一权威数据。

## 5. 决策与登记

- **DocType 用 ASCII 名**：v16 的 query-builder 校验 `TABLE_NAME_PATTERN` 不接受中文 DocType（`get_list` 直接抛 Invalid DocType），故草稿 DocType 命名 `Purchase Intake Draft`，字段标签保留中文（OBS-20-01，S2：如需中文列表标题可加翻译或改 label）。
- Draft 记录在改名重建时清空重放（PID-00001/00002 为改名前产物，其 PR 单据仍在且有效）。
- Excel 文件解析本身按 QUEUE 归 BUILD-60；本阶段合同只收「解析后的行数据」。

## 6. 复测方式

```bash
"C:\...python.exe" product/scripts/build20_replay.py   # 幂等可重复，21 项断言
# 密钥：D:/ERP/poc/share/api_keys.local.json（本地文件，不入 Git）
```
