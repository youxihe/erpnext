# FLOW-97A 线上只读事实审计：SAL-ORD-2026-00001 / SAL-ORD-2026-00006

- 日期：2026-11-08
- 分支：`product/erpnext-wecom-ai-v1-20261029`
- 站点：线上 `https://d.urlxl.cn`（ERPNext 16.52.1 / Frappe 16.53.0，MySQL 8）
- 关联任务：`docs/product/tasks/FLOW-97.md` 第一阶段
- 审计脚本：`erpnext/poc/scripts/flow97_audit.py`（只读：只有 `get_all` / `db.get_value` / `SELECT`，
  无 insert/save/submit/cancel；原始输出留在 `poc/deploy/flow97_audit_online_clean.json`）
- 审计账号：脚本以 `Administrator` 只读视图核对事实；权限边界另由 `online_verify97` 按真实角色复验

## 1. 一句话结论

**00001 与 00006 没有任何共用采购单据**。两张订单各有自己的 MR / PO / PR / Work Order / Stock Entry / Delivery Note，
交集为空；共用 BOM `BOM-ASSY-X1-001` 只说明配方相同，**不能推出共用采购**。
00006 的 RACK 实物来自一张**不挂 PO、不挂 MR 的直采入库**（`MAT-PRE-2026-00016`），
而它自己的 `PUR-ORD-2026-00002` 至今 `received_qty=0`——同一笔 2 件需求已被入库一次、又还挂在待收货 PO 上。

## 2. 两单基础事实

| 项 | SAL-ORD-2026-00001 | SAL-ORD-2026-00006 |
| --- | --- | --- |
| docstatus / 状态 | 1 已提交 / Completed | 1 已提交 / Completed |
| 客户 | 苏州华新装备有限公司 | 苏州华新装备有限公司 |
| 下单 / 交期 | 2026-10-26 / 2026-11-25 | 2026-11-08 / 2026-11-22 |
| 生产项目 | 无（未建 Project） | `PROJ-0001` |
| 产品行 | ASSY-X1 × 2 | ASSY-X1 × 1 |
| 订单行 `bom_no` 原值 | 空（`bom_state=default_suggested`，默认 BOM-ASSY-X1-001） | `BOM-ASSY-X1-001`（`bom_state=explicit`，已提交锁定） |
| BOM 组件需求（按 BOM × 数量） | RACK 4 / SENSOR 2 / FASTENER 8 | RACK 2 / SENSOR 1 / FASTENER 4 |

## 3. 逐项真实链接表

引用字段说明：`SOI` = `Sales Order Item`，`PP` = `Production Plan`，`MR` = `Material Request`，
`PO` = `Purchase Order`，`PR` = `Purchase Receipt`，`WO` = `Work Order`，`SE` = `Stock Entry`，`DN` = `Delivery Note`。

### 3.1 SAL-ORD-2026-00001

| 源（SO + 行） | 目标 DocType / 单号 | 行/数量 | 状态 | 真实引用字段 | 关系类型 |
| --- | --- | --- | --- | --- | --- |
| 00001 / 行 1 `2a3ok8stl0` | Production Plan `MFG-PP-2026-00001` | 计划 ASSY-X1 × 2（produced 2） | 1 / Completed | `PP.sales_orders.sales_order = 00001`、`PP.po_items.sales_order = 00001`；`PP.prod_plan_references` **为空** | 直接（订单级） |
| 00001 | Material Request `MAT-MR-2026-00001` | RACK 3、SENSOR 2 | 1 / Received，per_ordered 100% | `MR Item.sales_order = 00001`、`MR Item.production_plan = MFG-PP-2026-00001` | 直接 + 计划间接 |
| 00001 | Purchase Order `PUR-ORD-2026-00001` | 行 1 RACK 3 / 行 2 SENSOR 2（¥1200） | 1 / To Bill，per_received 100% | `PO Item.sales_order = 00001`、`material_request_item` = MR 行 `88c6l89s4u` / `88cfg80ok7` | 直接 + MR 行 |
| 00001 | Purchase Receipt `MAT-PRE-2026-00002` | RACK 3、SENSOR 2 | 1 / To Bill | `PR Item.purchase_order = PUR-ORD-2026-00001`、`purchase_order_item` = PO 行 | 直接（PO 行） |
| 00001 | Purchase Receipt `MAT-PRE-2026-00001` | RACK 3、SENSOR 2 | **2 已取消** | 同上 | 直接但无效，不计数量 |
| 00001 / 行 1 | Work Order `MFG-WO-2026-00001` | ASSY-X1 × 2，produced 2 | 1 / Completed | `WO.sales_order = 00001`、`WO.production_plan = MFG-PP-2026-00001`、**`WO.sales_order_item` 为空** | 直接（订单级，行级缺失） |
| 00001 | Stock Entry `MAT-STE-2026-00003` | 领料 RACK 4、SENSOR 2、FASTENER 8 → 在制仓 | 1 / Material Transfer for Manufacture | `SE.work_order = MFG-WO-2026-00001` | 间接（经工单） |
| 00001 | Stock Entry `MAT-STE-2026-00004` | 消耗同上 + 入库 ASSY-X1 2 | 1 / Manufacture | 同上 | 间接（经工单） |
| 00001 | Stock Entry `MAT-STE-2026-00001/00002` | 同上 | **2 已取消** | 同上 | 间接但无效 |
| 00001 | Delivery Note `MAT-DN-2026-00004` | ASSY-X1 × 2 | 1 / Completed | `DN Item.against_sales_order = 00001`、`so_detail = 2a3ok8stl0` | 直接（订单行） |
| 00001 | Delivery Note `MAT-DN-2026-00003` | ASSY-X1 × 2 | **2 已取消** | 同上 | 直接但无效 |

### 3.2 SAL-ORD-2026-00006

| 源（SO + 行） | 目标 DocType / 单号 | 行/数量 | 状态 | 真实引用字段 | 关系类型 |
| --- | --- | --- | --- | --- | --- |
| 00006 / 行 1 `bqut2c57o7` | Production Plan | **无** | — | `Production Plan Item Reference.sales_order` 无 00006；也无可达计划 | 不存在 |
| 00006 | Material Request `MAT-MR-2026-00002` | RACK 2 | 1 / **Pending**，ordered 0 | `MR Item.sales_order = 00006`，`production_plan` 空 | 直接 |
| 00006 | Material Request `MAT-MR-2026-00003` | RACK 2 | **2 已取消** | 同上 | 直接但无效 |
| 00006 | Purchase Order `PUR-ORD-2026-00002` | RACK 2（¥400） | 1 / To Receive and Bill，**received 0** | `PO Item.sales_order = 00006`，**`material_request_item` 为空** | 直接，但未接 MR 行 |
| 00006 | Purchase Order `PUR-ORD-2026-00003` | RACK 2 | **2 已取消** | 同上 | 直接但无效 |
| 00006 | Purchase Receipt `MAT-PRE-2026-00016` | RACK 2 | 1 / To Bill | `PR Item.sales_order = 00006`；**`purchase_order` / `purchase_order_item` / `material_request_item` 全为空** | 直接对订单，**无采购来源** |
| 00006 | Purchase Receipt `MAT-PRE-2026-00017` | RACK 2 | **2 已取消** | 同上 | 无效 |
| 00006 / 行 1 | Work Order `MFG-WO-2026-00003` | ASSY-X1 × 1，produced 1 | 1 / Completed | `WO.sales_order = 00006`；`production_plan` 空、**`sales_order_item` 为空** | 直接（订单级） |
| 00006 | Stock Entry `MAT-STE-2026-00008` | 领料 RACK 2、SENSOR 1、FASTENER 4 | 1 / Material Transfer for Manufacture | `SE.work_order = MFG-WO-2026-00003` | 间接（经工单） |
| 00006 | Stock Entry `MAT-STE-2026-00009` | 消耗同上 + 入库 ASSY-X1 1 | 1 / Manufacture | 同上 | 间接（经工单） |
| 00006 | Delivery Note `MAT-DN-2026-00005` | ASSY-X1 × 1 | 1 / Completed | `DN Item.against_sales_order = 00006`、`so_detail = bqut2c57o7` | 直接（订单行） |

### 3.3 共用单据检测（集合交集）

| 单据类型 | 00001 独有 | 00006 独有 | **交集** |
| --- | --- | --- | --- |
| Material Request | MAT-MR-2026-00001 | 00002、00003(取消) | **空** |
| Purchase Order | PUR-ORD-2026-00001 | 00002、00003(取消) | **空** |
| Purchase Receipt | MAT-PRE-2026-00001(取消)、00002 | 00016、00017(取消) | **空** |
| Work Order | MFG-WO-2026-00001 | MFG-WO-2026-00003 | **空** |
| Stock Entry | STE-00001~00004 | STE-00008、00009 | **空** |
| Delivery Note | DN-00003(取消)、00004 | DN-00005 | **空** |

全站只有一张 Production Plan `MFG-PP-2026-00001`：`get_items_from=Sales Order`、`combine_items=0`、
`sales_orders=[00001]`、`prod_plan_references` 为空、`total_planned_qty=2`。
**线上不存在任何"多订单合并计划"样本**，因此样本内无法验证合并采购；该场景按任务第 5 条在本地 POC 站点另造（见 §6）。

## 4. 数量口径对账

### 4.1 00001：需求 4 件 RACK，只买了 3 件，却领了 4 件

| 环节 | RACK | SENSOR | FASTENER |
| --- | --- | --- | --- |
| BOM 需求（2 台） | 4 | 2 | 8 |
| 采购申请 MR-00001 | **3** | 2 | 0 |
| 采购订单 PO-00001 | 3 | 2 | 0 |
| 已入库 PR-00002 | 3 | 2 | 0 |
| 本单实际领料 STE-00003 | **4** | 2 | 8 |
| 本单实际消耗 STE-00004 | 4 | 2 | 8 |

RACK 少申请 1 件的原因有据可查：2026-10-26 `MAT-RECO-2026-00005` 盘点使 RACK 原材料仓从 0 → 1，
MR 因此只申请 3；领料时 3 件到货 + 1 件盘盈 = 4 件。
FASTENER 8 件完全未采购，直接从原有库存（46 件）领用。
**结论：本单的采购需求 ≠ BOM 需求，差额由公共库存补足——这是"共享库存"必须显式说明的实证。**

### 4.2 00006：同一笔 2 件 RACK，入库一次、又挂在待收货 PO 上

| 环节 | RACK | SENSOR | FASTENER |
| --- | --- | --- | --- |
| BOM 需求（1 台） | 2 | 1 | 4 |
| 采购申请 MR-00002（Pending，未转单） | 2 | 0 | 0 |
| 采购订单 PO-00002（未收货） | 2 | 0 | 0 |
| 直采入库 PR-00016（无 PO） | **2** | 0 | 0 |
| 本单实际领料 STE-00008 | 2 | 1 | 4 |
| 本单实际消耗 STE-00009 | 2 | 1 | 4 |

RACK 库存流水（`Stock Ledger Entry`，`is_cancelled=0`）：

```
2026-11-08  Purchase Receipt  MAT-PRE-2026-00016   +2  → 2（原材料仓）
2026-11-08  Stock Entry       MAT-STE-2026-00008   -2  → 0（原材料仓）／+2 → 4（在制仓）
2026-11-08  Stock Entry       MAT-STE-2026-00009   -2  → 2（在制仓，消耗）
```

即：**00006 的 RACK 实物是 PR-00016 进来的，不是 PO-00002 收的**；PO-00002 至今 0 收货，
若后续按 PO 正常收货，同一需求会再进 2 件（重复采购 2 件风险）。SENSOR / FASTENER 未申请采购，
直接取自公共库存（SENSOR 39 件、FASTENER 46 件）。

### 4.3 期末库存（Bin）

| 物料 | 仓库 | actual_qty | reserved_qty |
| --- | --- | --- | --- |
| RACK | 原材料仓 - QC | 0 | 0 |
| RACK | 生产在制仓 - QC | 2 | 0 |
| SENSOR | 原材料仓 - QC | 39 | 6 |
| SENSOR | 生产在制仓 - QC | 1 | 0 |
| FASTENER | 原材料仓 - QC | 46 | 0 |
| FASTENER | 生产在制仓 - QC | 4 | 0 |
| ASSY-X1 | 产成品仓 - QC | 0 | 0 |

RACK 在制仓余 2 件是 00006 领料 2 件与消耗 2 件之间的历史差异（此前批次遗留），
不属于任何一张订单的"专属库存"。

## 5. 现有订单执行概览的缺陷（区分缺 UI / 缺数据）

| # | 现象 | 缺 UI 还是缺基础来源数据 |
| --- | --- | --- |
| 1 | 页面完全不展示 Production Plan，用户看不到"本单在哪个计划里" | **缺 UI**（`order_summary` 根本没查 PP/`prod_plan_references`） |
| 2 | PO 只按 `PO Item.sales_order` 直查，经 Production Plan 汇总的采购会漏（本地合并场景已复现） | **缺 UI + 缺查询路径** |
| 3 | 采购/到货只给汇总数量，看不到"这 3 件来自哪张 PO 哪一行、是否已收" | **缺 UI**（数据齐全） |
| 4 | PR-00016 这种"无 PO 入库"与 PO-00002"未收货"并排出现，页面不提示两者是同一批 | **缺 UI + 缺口径**（数据本身矛盾，需标"来源不可证实/重复风险"） |
| 5 | 同一物料两张订单都显示整仓现存（如 SENSOR 39），没有"共享、不按单锁定"的说明 | **缺口径文案** |
| 6 | 缺料清单按交期做模拟分配，物料表里未标"估算/未预留" | **缺口径文案**（`shortage_basis` 只在脚注） |
| 7 | `Work Order.sales_order_item` 为空，无法把工单绑定到具体订单行 | **缺基础数据**（历史单据无行级引用；新建工单时 ERPNext 会带，但本批是手工建） |
| 8 | 合并成单个 PO Item 的多来源需求，原生 `material_request_item` 单值无法表达 | **原生限制**，按任务要求不做分摊引擎，只记录建议 |

## 6. 合并采购场景的本地验证（线上无样本，未在 d.urlxl.cn 制造过账）

线上只有 1 张单人计划，为验证原生「多订单合并计划 → 汇总 MR → 汇总 PO」链路，
在本地 Docker POC 站点 `erpnext-poc.localhost` 造样本（不动线上单据），
脚本 `erpnext/poc/scripts/flow97_local_sample.py` 可重复重建：

- 两张生产类 SO：`SAL-ORD-2026-00015`、`SAL-ORD-2026-00016`（ASSY-X1 各 1 台，已提交）；
- 一张 `Production Plan MFG-PP-2026-00002`：`get_items_from=Sales Order`、
  `combine_items=1`（Consolidate Sales Order Items）、两张单都在 `sales_orders` 表；
- 点「Get Items for Purchase」生成 `mr_items`（RACK 4，FASTENER/SENSOR 因现存量足够取 0）；
- 「Create Material Request」生成 **1 张** `MAT-MR-2026-00004`（RACK 4）；
- 采购把这张 MR 拉到 `PUR-ORD-2026-00006`（1 行 RACK 4）；收货 `MAT-PRE-2026-00026`（4 件）；
- 「Create Work Order」生成 **1 张** `MFG-WO-2026-00008`（ASSY-X1 2 台）；
- 领料 `MAT-STE-2026-00022`（RACK 4 / SENSOR 2 / FASTENER 8）。

实测原生字段落点（供 FLOW-97B 使用）：

| 环节 | 实测值 | 结论 |
| --- | --- | --- |
| 计划 → 来源订单 | `prod_plan_references` = 00015(1)、00016(1)，**两行都在** | 唯一可信的多订单来源表 |
| `Production Plan Item`（合并后） | 1 行 ASSY-X1 planned 2，`sales_order` **为空**，`sales_order_item` 只留第一张单的行 | **不能**用它分单 |
| 计划 → MR | `mr_items` 3 行（RACK 4），`sales_order` **为空**；MR 行 `production_plan=MFG-PP-2026-00002` | 合并后 MR 只有计划归属 |
| 计划 → MR 汇总表 | `PP.material_requests` 子表为空（计划不是从 MR 建的） | 反查只能靠 `MR Item.production_plan` |
| MR → PO | PO 行 `material_request_item` 指向 MR 行，`sales_order` **为空** | 一张 PO 可拉多张 MR 的多行 |
| PO → PR | `PR Item.purchase_order / purchase_order_item` | 部分收货按行累计 |
| 计划 → WO | **1 张** WO 承载 2 张订单，`sales_order` 为空、`production_plan` 有值、`sales_order_item` 只留第一张单 | 实物领用**不可按单拆分**，只能按计划比例估算 |
| WO → 领料 | `Stock Entry.work_order`，purpose = Material Transfer for Manufacture | 领料是整张工单的量 |

即：**合并采购真正能证明的是「哪些订单进了这张计划」，不是「哪件实物归哪张订单」**。
所以 FLOW-97B 的页面在合并场景一律显示「计划共享（按订单数量比例估算）」，
并给出工单合并提示，不伪造行级分配。

## 7. 未覆盖 / 风险

- `d.urlxl.cn` 上不存在合并采购样本，合并链路的数值正确性在本地 POC 验证，线上只读页面用
  `MFG-PP-2026-00001` 单人计划 + PO-00001/00002 验证渲染与跳转。
- 00006 的 PO-00002 与 PR-00016 重复：**本轮只读，未修改任何线上单据**；是否取消 PO-00002 或补挂来源，
  需业务确认后另行处理（已记入 FLOW-97B 页面提示「未收货 PO 与无来源入库并存」）。
- 历史工单 `sales_order_item` 为空，行级追溯只能到订单级，页面会标注「订单级」。
- 未做库存预留、批次/序列号追踪，因此**不能**宣称某张 PR 的 N 件实物归某张 SO；页面统一用
  「共享库存（不分单）」表述。
