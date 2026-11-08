# BUILD-92 证据：订单执行概览与整机实物流转

日期：2026-11-08
分支：`product/erpnext-wecom-ai-v1-20261029`
权威依据：`docs/product/QUEUE.md` BUILD-92、`docs/product/decisions/LIGHT_MANUFACTURING_20261108.md`
环境：本地 POC Docker，Site `erpnext-poc.localhost`，Frappe 16.53.0 / ERPNext 16.52.1

## 1. 为什么要新建一张订单

审计 `build92-audit.json` 显示：既有生产类订单 `SAL-ORD-2026-00005` 是采购件 `SENSOR × 6`，**没有 BOM、没有任何关联单据**；`SAL-ORD-2026-00001` 虽是 `ASSY-X1` 整机且已有完整历史链路，但已 100% 交付/开票。为不改历史数据、又能真实演示「从缺料到一次发货」的完整链路，新建生产类订单 `SAL-ORD-2026-00006`（`po_no=BUILD92-LM-001`，`ASSY-X1 × 1`，交期 2026-11-22，金额 ¥5,000）。

`ASSY-X1` 标准 BOM `BOM-ASSY-X1-001` 带 2 道工序；按轻制造方向与 BOM-01「标准 BOM 优先、非标订单选用独立版本」，为这张订单建独立无工序版本 `BOM-ASSY-X1-002`（RACK 2 / SENSOR 1 / FASTENER 4），并写入 `Sales Order Item.bom_no`，**不改标准 BOM 的默认关系**。

## 2. 分角色真实原生单据链（全部 `docstatus=1`）

| # | 岗位 / 账号 | 原生单据 | 单号 | 关键结果 |
|---|---|---|---|---|
| 1 | 生产经理 刘工 | BOM（订单独立版本） | `BOM-ASSY-X1-002` | `with_operations=0`，`is_default=0` |
| 2 | 销售 王明 | Sales Order | `SAL-ORD-2026-00006` | 生产类、整机 1 台、行级选用 BOM |
| 3 | 生产经理 刘工 | Project / Task（BUILD-91 接力） | `PROJ-0003` / `TASK-2026-00028`～`00036` | 九阶段模板生成 9 个 Task |
| 4 | — | 缺料计算 | RACK 缺 2（需求 2 / 原料仓 0），SENSOR、FASTENER 不缺 | 按 BOM × 订单量 |
| 5 | 采购 陈工 | Material Request | `MAT-MR-2026-00002` | Purchase 类型，RACK × 2 |
| 6 | 采购 陈工 | Purchase Order | `PUR-ORD-2026-00002` | 供应商：昆山精工零部件有限公司，¥400 |
| 7 | 仓库 张工 | Purchase Receipt | `MAT-PRE-2026-00016` | RACK@原材料仓 **0 → 2** |
| 8 | 生产经理 刘工 | Work Order | `MFG-WO-2026-00004` | `skip_transfer=0`，**0 张 Job Card** |
| 9 | 仓库 张工 | Stock Entry（领料） | `MAT-STE-2026-00010` | Material Transfer for Manufacture：原料仓 → 生产在制仓 |
| 10 | 仓库 张工 | Stock Entry（完工） | `MAT-STE-2026-00011` | Manufacture：ASSY-X1@产成品仓 **0 → 1**，`produced_qty=1` |
| 11 | 销售 王明 | Delivery Note | `MAT-DN-2026-00005` | **整机一次发货（1 张 DN）**，`per_delivered=100%` |
| 12 | 财务 周会计 | Sales Invoice | `ACC-SINV-2026-00006` | `per_billed=100%`，¥5,000 |
| 13 | 财务 周会计 | Payment Entry | `ACC-PAY-2026-00006` | ¥5,000，`outstanding_amount=0` |

> 原生单据用 `insert(ignore_permissions=True)` 提交，但每步先 `frappe.set_user(岗位账号)`，`owner` 与操作人真实落到对应用户。POC 角色画像未逐一配置每个原生 DocType 的 submit DocPerm；正式上线需按 DocPerm 收紧，已登记 `LM92-03`。

## 3. 真实库存流水（不可变 SLE 凭证，`build92-stock-trace.json`）

BUILD-91 结束时 `Stock Ledger Entry = 73`；本轮 4 张库存单据共新增 **12 条 SLE → 85**，之后不再变化。

| 单据 | SLE | 明细（`actual_qty` / `qty_after_transaction`） |
|---|---|---|
| `MAT-PRE-2026-00016` | 1 | RACK@原材料仓 **+2 → 2** |
| `MAT-STE-2026-00010` 领料 | 6 | RACK@原材料仓 −2 → 0；RACK@在制仓 +2 → 4；SENSOR −1 → 39 / +1 → 2；FASTENER −4 → 46 / +4 → 8 |
| `MAT-STE-2026-00011` 完工 | 4 | RACK@在制仓 −2 → 2；SENSOR −1 → 1；FASTENER −4 → 4；**ASSY-X1@产成品仓 +1 → 1** |
| `MAT-DN-2026-00005` 发货 | 1 | ASSY-X1@产成品仓 **−1 → 0** |

**Gate（任务 ≠ 库存）**：最后一条 SLE 修改时间 `2026-11-08 11:56:19`，而 `TASK-2026-00028` 标记完成时间 `11:57:48`；任务完成后 Bin 全量快照一致、SLE 恒为 85。`doc_events` 中 `Task` / `Project` 均为 `None`。

## 4. 订单执行概览（PC）

新增只读页 `/order_execution`，挂到 `/cn_portal` 的「订单执行」分组（按角色回退到第一个可见的业务模块）。数据全部来自 `cn_mfg_poc/order_execution.py: order_summary()`：

- **订单与产品**：客户、下单/承诺交期、数量、单价、订单选用 BOM、交付/开票比例，单据号可点进原生 Desk。
- **物料覆盖**：按订单 BOM 展开，逐项显示 需求量 / 原料仓现存 / 已申请 / 已采购 / 已入库 / 已领料 / 已消耗 / 预计缺料。缺料公式 `max(0, required − available_now − received_qty − issued_net)`，闭环后全部组件缺料为 0。
- **原生单据链**：Material Request、Purchase Order、Purchase Receipt、Work Order、Stock Entry、Delivery Note、Sales Invoice、Payment Entry 的真实单号、状态与 `/desk/...` 链接（HTTP 实测 200）。
- **固定生产进度与实物**：`PROJ-0003` 的完成/总数/逾期/临期、完工入库数量、是否一次发货、Job Card 数（0，不强制）。
- **财务按权限**：仅 `Accounts User / Accounts Manager / System Manager` 可见订单金额、单价、发票金额、已回款、未收余额；其他角色连单据行 `grand_total` 也会被剔除，只能看单号/状态/日期。

另提供 `materials_shortage()` 轻量契约（BUILD-93 的 Bot/H5 复用），按真实订单与 BOM 计算未完成生产订单的缺料。

## 5. 测试结果

- `product/scripts/build92_execute.py`：**15/15 PASS，0 异常**（`build92-execute.json`），且连续重跑仍 15/15、不重复造数（单据按订单引用定位复用）。
- `product/scripts/build92_verify.py`：**26/26 PASS**（`build92-verify.json`）——真实单据链、两段式库存事务、缺料→采购→领料→消耗全链路可追溯、四类角色的金额隔离、财务角色可见金额、Guest 拒绝、四类订单与服务单不回退、Task/Project 无库存 hook。
- `product/scripts/build92_http_verify.py`：**44/44 PASS**（`build92-http.json`）——5 个身份的 `/cn_portal` 菜单注入与旧入口不回退、`/order_execution` 200、概览 API 按角色金额隔离、未登录 403、9 个原生单据链接、4 条 `/desk/...` 路由 HTTP 200、缺料契约可用。
- 回归：修改 `READ_ROLES` 后重跑 BUILD-91 服务端 **27/27**、HTTP **24/24**（`build91_verify.py` 已改为可重复执行）。
- 其他证据：`build92-audit.json`（执行前现状）、`build92-precheck.json`（BOM/字段/供应商/helper 前置核对）、`build92-stock-trace.json`（SLE 流水）。

## 6. 点击路径

1. `http://127.0.0.1:18000/cn_portal` → 顶部「客户与销售」/「设计与生产」→ 左侧「订单执行 → 订单执行概览」。
2. 下拉选择 `SAL-ORD-2026-00006` → 查看 KPI、订单与产品、物料覆盖、原生单据链、固定生产进度、开票回款。
3. 点任意单据号跳原生表单核对；点「查看九阶段任务」跳 `/production_board?view=order`。
4. 财务角色（周会计 / Administrator）可见金额，销售/仓库/采购/生产角色金额显示为「—」或提示不可见。

## 7. 四类订单不回退

| 类型 | 张数 | 校验 |
|---|---|---|
| 生产 | 3（含新增 `SAL-ORD-2026-00006`） | 新单完整跑通原生制造/发货链路 |
| 耗材 | 1 | `SAL-ORD-2026-00002` 直接出库，0 张 Work Order |
| 零部件 | 1 | `SAL-ORD-2026-00003` 直接出库，0 张 Work Order |
| 服务 | 1 | `SAL-ORD-2026-00004` 0 张 Delivery Note、0 条出库 SLE、0 张 Work Order |

## 8. 复现命令

```bash
docker exec poc-frappe sh -c 'cd /workspace/development/frappe-bench/sites && \
  exec /workspace/development/frappe-bench/env/bin/python /hostshare/build92_execute.py'
docker exec poc-frappe sh -c 'cd /workspace/development/frappe-bench/sites && \
  exec /workspace/development/frappe-bench/env/bin/python /hostshare/build92_stock_trace.py'
docker exec poc-frappe sh -c 'cd /workspace/development/frappe-bench/sites && \
  exec /workspace/development/frappe-bench/env/bin/python /hostshare/build92_verify.py'
docker exec poc-frappe sh -c 'cd /workspace/development/frappe-bench/sites && \
  exec /workspace/development/frappe-bench/env/bin/python /hostshare/build92_http_verify.py'
```

## 9. 状态与剩余项

结论：**PASS(LOCAL)**。真实企业微信真人 UAT 仍缺授权（`REAL_WECOM_BLOCKED`）。
非关键观察登记 `docs/product/BACKLOG.md` 的 `LM92-01`～`LM92-04`；三入口接力与分角色联合验收分别在 BUILD-93 / BUILD-94 继续。
