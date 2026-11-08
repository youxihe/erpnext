# FLOW-97B 订单级物料履约与集中采购来源（双向追溯）

- 日期：2026-11-08
- 分支：`product/erpnext-wecom-ai-v1-20261029`
- 站点：本地 `erpnext-poc.localhost`（Docker `poc-frappe`）→ 线上 `https://d.urlxl.cn`
- 关联任务：`docs/product/tasks/FLOW-97.md` 第二阶段；前置审计 `docs/product/evidence/FLOW-97A.md`
- 关联文件：
  - `cn_mfg_poc/procurement_trace.py`（新增，全部只读）
  - `cn_mfg_poc/api.py`（新增 `materials.trace` / `purchase.options` / `purchase.trace` 三个契约）
  - `cn_mfg_poc/www/order_execution.html`（新增「物料需求及采购履约」）
  - `cn_mfg_poc/www/procurement_trace.py` / `.html`（新增页面）
  - `cn_mfg_poc/www/cn_portal.py`（采购/仓库角色新增「集中采购来源」入口）

## 1. 结论

用户的核心疑问「00001 和 00006 用同一个 BOM，采购/入库/领料到底怎么绑定」有了明确答案，并且现在可以直接在页面上逐行看到：

- **两单没有共用采购**：MR / PO / PR / WO / SE / DN 六类单据交集为空（见 FLOW-97A §3.3）。
  共用 BOM 只说明配方相同。
- **00001**：`MAT-MR-2026-00001`（RACK 3 / SENSOR 2）→ `PUR-ORD-2026-00001` → `MAT-PRE-2026-00002`（已收完）
  → `MFG-WO-2026-00001` → `MAT-STE-2026-00003/00004` 领 4 件 RACK（3 件采购 + 1 件盘盈）。
- **00006**：`MAT-MR-2026-00002`（RACK 2，Pending）与 `PUR-ORD-2026-00002`（RACK 2，**未收货**）都挂着，
  但实物来自 **不挂 PO 的 `MAT-PRE-2026-00016`**。页面直接给出告警：
  「同一物料既有未收货采购订单（2.0）又有无采购订单的入库（2.0）：若按 PO 继续收货会重复到货」。
- **共享库存不再被当成独占**：所有数量都标注来源仓 Bin 是共享的，`本单已领/已耗` 来自本单工单的 Stock Entry，
  不按订单分摊库存。
- **合并采购**：线下 POC 造了真实合并样本（`MFG-PP-2026-00002` 合并 `00015/00016`），
  实测原生链路是 **1 张合并计划 → 1 张 MR → 1 张 PO → 1 张 WO**，
  订单归属只保留在 `Production Plan Item Reference`，因此页面显示「计划共享（按订单数量比例估算）」，
  不伪造行级分配。

线上真实角色：后端 **30/30**、浏览器 **20/20**；本地合并用例 **40/40** + UX-96 回归 **42/42**；
库存与单据数全程零变动（`sle=84`、`bin_qty=135.0`、`bins=9`、`PO=3`、`PR=17`、`MR=3`、`WO=3`、`SE=9`）。

## 2. 新增的两个视图

### 2.1 订单执行概览 →「物料需求及采购履约」（`/order_execution`）

每个 BOM 组件一行，逐格可点原生单据：

| 列 | 含义 | 数据来源 |
| --- | --- | --- |
| 需求 | 本单 BOM 需求（按订单数量折算） | `BOM.items` |
| 已申请 | 已提交 MR 的申请量；合并计划按本单占比折算 | `Material Request Item.qty` |
| 已下单 | 已提交 PO 的订购量；合并计划按占比折算 | `Purchase Order Item.qty` |
| 已到货 | 已提交 PR 的入库量（含无 PO 直采，标注来源） | `Purchase Receipt Item.qty` |
| 待收货 | PO 订购 − 已收（按占比折算） | 同上 |
| 本单已领 / 已耗 | 本单工单的 `Material Transfer for Manufacture` / `Manufacture` 明细 | `Stock Entry.work_order` |
| 共享现存 | 该组件在 BOM 发料仓的 Bin 实际库存 | `Bin.actual_qty`（**共享，不按单锁定**） |
| 来源与单据 | MR / PO / PR 单据号 + 行号 + 数量 + 状态 + 来源标签 | 逐条原生引用 |

来源标签只有四种，且只有前两种是「证明」，后两种是「说明」：

| 标签 | 判定条件 | 性质 |
| --- | --- | --- |
| 直接引用 | 子表行 `sales_order = 本单` | 原生证明（订单级） |
| 经采购申请行 | `PO Item.material_request_item` 命中本单可见的 MR 行 | 原生证明 |
| 计划共享（按订单数量比例估算） | MR 行 `production_plan` = 本单命中的合并计划；比例取 `Production Plan Item Reference` 的订单数量 | **估算**，用于合并计划 |
| 无采购订单入库 / 来源不可证实 | PR 行 `purchase_order` 为空，或 PO 行没有任何 MR/计划/订单引用 | 明确标注不可证明 |

告警规则（页头黄色块）：

1. 同一物料「未收货 PO > 0」且「无 PO 入库 > 0」→ 重复到货风险；
2. 采购申请行全部无法指向本单 → 来源不可证实；
3. 有入库但没有任何采购订单 → 无法追溯采购来源；
4. 工单既没挂本单、计划又缺订单引用表 → 领料无法按单拆分；
5. 合并工单 → 领料/耗用按计划比例估算，并列出共用的其它订单号。

### 2.2 集中采购来源（`/procurement_trace`，采购/仓库角色）

从一张采购订单反查：

- PO 行 → `material_request` / `material_request_item` → MR 行；
- MR 行 `production_plan` → 生产计划 → `Production Plan Item Reference` → 各销售订单及需求数量；
- `PO Item.sales_order` 直接挂单的（手工采购常见）单独标「订单直接引用」；
- 两侧都没有的标「来源不可证实」并给出告警；
- 每行列出该 PO 行的全部入库单（含已取消），并给出「订购 / 已收 / 待收」。

页面底部固定说明：一张 PO 可以拉多张 MR 的多行；同一 SKU 被压成一行时，
原生 `material_request_item` 只能记一个来源，其余来源不可证实。

## 3. 原生字段的实测结论（决定实现边界）

合并样本 `MFG-PP-2026-00002`（`SAL-ORD-2026-00015/00016`，`combine_items=1`）实测：

| 位置 | 实测值 | 后果 |
| --- | --- | --- |
| `Production Plan Item Reference` | 00015(1)、00016(1) 两行 | **唯一**可证明「哪些订单进了这张计划」 |
| `Production Plan Item` | 1 行 ASSY-X1 planned 2，`sales_order` 空、`sales_order_item` 只留第一张单 | 不能用于分单 |
| `MR Item` | RACK 4，`production_plan` 有值、`sales_order` 空 | 合并后 MR 只有计划归属 |
| `PP.material_requests` 子表 | 空 | 计划→MR 反查只能靠 `MR Item.production_plan` |
| `PO Item` | RACK 4，`material_request_item` 有值、`sales_order` 空 | 必须经 MR 才能回到计划与订单 |
| `Work Order` | 1 张承载 2 张订单，`sales_order` 空、`sales_order_item` 只留第一张单 | 领料**不可按单拆分**，只能按比例估算 |

因此实现上刻意不做三件事：不按 SKU/时间猜来源、不把默认/带入值当确认、不给合并工单编造行级分摊。

## 4. 权限

| 能力 | 允许角色 | 校验点 |
| --- | --- | --- |
| 订单物料履约 | `Sales/Purchase/Stock/Manufacturing/Accounts User+Manager`、`System Manager`；且需对销售订单有 read 权限，或为高级角色，或为该单生产任务负责人 | `order_material_trace` 内 `has_permission` + `_is_order_worker` |
| 集中采购来源 / 采购订单下拉 | `Purchase User/Manager`、`Stock User/Manager`、`System Manager` | `po_options` / `purchase_trace` 角色门 + `has_permission("Purchase Order")` |
| 金额（PO 行金额、订单总额） | 仅 `Accounts User/Manager`、`System Manager` | 非财务角色返回 `null`，页面显示「按角色隐藏」 |
| `/procurement_trace` 页面 | 同上采购角色，其余 403 | `get_context` 抛 `PermissionError` |

实测负例：生产人员查集中采购来源 / 查采购订单来源 / 查他人订单物料追溯、销售经理查集中采购来源，均被拒绝；
销售经理可看订单物料追溯（订单级只读），管理员可看采购来源。

## 5. 线上验收（d.urlxl.cn，只读）

后端 30 项全部通过，样本为真实历史单据：

| 用例 | 实际值 |
| --- | --- |
| 00001 RACK 需求/申请/下单/到货/领料 | 4 / 3 / 3 / 3 / 4 |
| 00001 计划 | `MFG-PP-2026-00001`，`refs_missing=True`（无订单引用表） |
| 00001 入库 | `MAT-PRE-2026-00002`（已提交 3）+ `MAT-PRE-2026-00001`（已取消，不计） |
| 00001 FASTENER | 无采购记录，领 8（取自公共库存） |
| 00006 计划 | 无 |
| 00006 RACK 需求/申请/下单/待收 | 2 / 2 / 2 / 2 |
| 00006 入库 | `MAT-PRE-2026-00016` 标「无采购订单入库（来源不可证实）」 |
| 00006 告警 | 「未收货 PO 2 件 + 无 PO 入库 2 件 → 若按 PO 收货会重复到货」 |
| PO-00001 反查 | MR-00001 行 1/2、订单 00001、入库 00002 + 已取消 00001 |
| PO-00002 反查 | 订单 00006、无 MR 行、未收货 2 件 |

浏览器 20 项全部通过（截图见下）：`Ignore` 无；生产人员访问 `/procurement_trace` 返回 **403**，
门户菜单不出现「集中采购来源」，但 `/order_execution` 正常打开。

截图（`poc/deploy/online_shots/`）：

| 文件 | 内容 |
| --- | --- |
| `flow97_01_so00001_trace.png` | 00001 物料履约表（直接引用、已取消入库、公共库存标签） |
| `flow97_02_so00001_full.png` | 00001 整页 |
| `flow97_03_so00006_trace.png` | 00006 履约表（无 PO 入库 + 未收货 PO） |
| `flow97_04_so00006_full.png` | 00006 整页 + 重复到货告警 |
| `flow97_05_po00001_trace.png` | PO-00001 反查（MR 行、订单、入库） |
| `flow97_06_po00001_full.png` | PO-00001 整页 |
| `flow97_07_po00002_trace.png` | PO-00002（无采购申请、待收 2） |
| `flow97_08_portal_menu.png` | 门户菜单新增「集中采购来源」 |
| `flow97_09_worker_403.png` | 生产人员 403 |

## 6. 本地合并采购验收（40/40）

样本：`SAL-ORD-2026-00015/00016` → `MFG-PP-2026-00002`（合并）→ `MAT-MR-2026-00004`（RACK 4）
→ `PUR-ORD-2026-00006`（RACK 4）→ `MAT-PRE-2026-00026`（收 4）→ `MFG-WO-2026-00008`（2 台）
→ `MAT-STE-2026-00022`（RACK 4 / SENSOR 2 / FASTENER 8）。

| 断言 | 结果 |
| --- | --- |
| 两张订单命中同一计划且互相可见 | 通过（各 50%） |
| 各单 RACK 申请/下单/到货 = 2（计划 4 × 50%） | 通过 |
| 申请行保留计划原始数量 4、标「计划共享」 | 通过 |
| 采购行标「经采购申请行」、分摊 2 | 通过 |
| 合并工单：原始领 4、本单约 2、给出共用告警 | 通过 |
| PO-00006 反查分摊到两张订单各 2 | 通过 |
| 手工 PO（无 MR/无订单）标「来源不可证实」并告警 | 通过 |
| 权限负例 3 条 + 正例 1 条 | 通过 |
| 追溯调用零库存变动 `(206, 144.0, 11)` 前后一致 | 通过 |

同时回跑 UX-96 验收脚本 **42/42**，BOM 选用/反查/受控变更/manual 三态未受影响。

## 7. 边界与未做的事（按要求）

- **不做** MRP/APS、库存预留、批次/序列号逐件追踪、采购费用分摊、MES 报工。
- 同一 SKU 被采购压成**单个 PO Item** 时，原生 `material_request_item` 为单值，
  页面只能证明其中一个来源，其余标「来源不可证实」；如需按 SO 定量分摊，
  需先确认是否接受「需求分配表」这类新表（本轮未开发，已在页面说明）。
- 历史工单 `sales_order_item` 为空，行级追溯只能到订单级；新建工单会带，
  但历史数据不补，页面按订单级展示。
- 00006 的 PO-00002 与 PR-00016 重复问题**只提示不修数据**：本轮全程只读，
  线上单据未改动（`sle=84`、`docstatus` 全部保持原状）。是否取消 PO-00002 需业务确认。
- 合并计划的数量按订单数量比例估算，若实际领料与计划比例偏差较大，
  页面会同时显示原始领料量与「本单约」估算量，不隐藏原始值。

## 8. 发布与回滚

- 备份：`/app/backup/flow97/20261108-233450`（应用目录 `cn_mfg_poc` + `brj_erp.sql` 13M，
  `-- Dump completed on 2026-11-08 23:35:16`）。
- 本轮无 DocType / 补丁变更，只替换 6 个文件，无需 `migrate`；
  `clear-cache` 后重启 `erpnext-v1-web/worker/socketio/schedule`，四个单元 `active`，`ping=200`。
- 线上文件校验：
  `procurement_trace.py f71d566fddd8`、`api.py 1c4993242678`、
  `www/procurement_trace.py 0133902f9a9a`、`www/procurement_trace.html 6ca2d6cf41b5`、
  `www/order_execution.html bd35b08c6b9b`、`www/cn_portal.py b6c283b2019f`。
- 回滚：把 `$BK/cn_mfg_poc` 覆盖回 `/app/erpnext-v1/apps/cn_mfg_poc`，清缓存并重启四个服务。
