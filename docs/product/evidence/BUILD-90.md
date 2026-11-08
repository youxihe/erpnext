# BUILD-90 轻制造基线与无工序制造验证（2026-11-08）

状态：**PASS(LOCAL)**（7/7 实测通过）。
真实企微真人 UAT 仍 `REAL_WECOM_BLOCKED`，与本次结论无关。
依据：远端提交 `041dc073` 的 `docs/product/decisions/LIGHT_MANUFACTURING_20261108.md`
与 `docs/product/QUEUE.md` 的 BUILD-90 定义。

## 0. 安全拉取与分支整合

- 分支 `product/erpnext-wecom-ai-v1-20261029`；`git fetch origin` 的 remote-tracking
  引用一度过期（停在 `c5b339be`），导致误判「远端无更新」。用显式 refspec
  `git fetch git@github.com:youxihe/erpnext.git +refs/heads/...:refs/remotes/origin/...`
  后发现远端真实 tip 为 `041dc073`（父提交 `a5b774a9`），**正是用户要求阅读的
  轻制造决策与 BUILD-90～94 定义**。
- 处理：先建备份分支 `backup/local-before-sync-20261108` 保存本地工作，
  再以 `041dc073` 为基线整合（保留其中有真实价值的探针数据，丢弃基于误判补写的
  决策/队列草稿）。**业务数据库未 reset、未清理、未重建**；既有单据一条未删。
- 当前 HEAD = `041dc073`，工作区仅含本项新增的脚本与证据。

## 1. 审计：现状保留（未重做旧 POC）

| 项 | 实测结果 |
| --- | --- |
| Git / 分支 | `product/erpnext-wecom-ai-v1-20261029`，HEAD `041dc073` |
| 容器 | `poc-frappe / poc-mariadb / poc-redis-cache / poc-redis-queue` 均 Up 24h；`aierp-*` 旧环境未触碰 |
| 隔离 POC Site | `erpnext-poc.localhost`，Frappe 16.53.0 / ERPNext 16.52.1 / Python 3.14.9；`http://127.0.0.1:18000/api/method/ping` = 200 |
| 线上部署 Site | `https://d.urlxl.cn/api/method/ping` = `{"message":"pong"}` |
| 中文导航 `/cn_portal` | 未登录 301 跳登录（正常），BUILD-80 已验收，未重构 |
| 企微 H5 `/wecom_h5` | 200 |
| AI Bot | `product/adapter/erpnext-bot-tools` 适配器与 HMAC 通道在；真实企微授权仍缺 → `REAL_WECOM_BLOCKED` |
| 四类订单 | 生产 2 / 耗材 1 / 零部件 1 / 服务 1，BUILD-80 成果完好 |
| 既有制造数据 | BOM 1（带 2 道工序）、Work Order 2（各 2 张 Job Card）、Job Card 4、Stock Entry 7 |

原始数据：`docs/product/evidence/build90-audit.json`（只读审计探针 `product/scripts/build90_audit.py`）。

## 2. 原生进度模型能力（BUILD-91 的依据）

- `Project Template` / `Project Template Task` / `Project` / `Task` **全部原生存在**，
  当前站点均为 **0 条记录**、**0 个模板** → BUILD-91 需要从零建模板，但**不需要新建 DocType**。
- `Project` 关键字段全部齐备：`project_template`、`sales_order`、`customer`、
  `expected_start_date/expected_end_date`、`status`、`is_active`、`percent_complete`。
  **`Project.sales_order` 存在**，可直接把生产进度 Project 关联到销售订单，满足「一单一项目」。
- `Task` 关键字段齐备：`project`、`subject`、`status`、`exp_start_date`、`exp_end_date`、
  `completed_on`、`completed_by`、`description`、`priority`、`task_weight`、`parent_task`。
- `Task.status` 原生选项为 `Open / Working / Pending Review / Overdue / Template / Completed / Cancelled`，
  与决策文案「待开始/进行中/完成/异常」不完全一致；BUILD-91 需做映射或最小自定义，不重造状态机。
- `Project Template Task` 只有 2 个字段（`subject` 等），没有 `start / duration / task_weight / description`
  → 九阶段模板的负责人与目标日期需在生成 Task 时按规则计算，不能依赖模板子表字段。

## 3. 关键技术验证：BOM 无 Operations、无 Job Card 能否合法完工入库

**结论：可以。** 使用独立 `LM90-*` 测试物料与真实提交的原生单据验证，
全程未生成、未操作任何 Job Card。脚本 `product/scripts/build90_native_verify.py`，
原始结果 `docs/product/evidence/build90-native-verify.json`，**7/7 PASS**。

| 步骤 | 真实单据 / 数值 |
| --- | --- |
| 测试物料 | `LM90-FG`（成品）、`LM90-RM`（原料），独立于既有演示物料 |
| 无工序单层 BOM | `BOM-LM90-FG-001`：`with_operations=0`、operations 0 行、`docstatus=1` |
| 原料真实入库 | `MAT-STE-2026-00008`（Material Receipt）：`LM90-RM@原材料仓 - QC` 0 → 10，库存价值 1000 |
| 无工序工单 | `MFG-WO-2026-00003`：`docstatus=1`、operations 0、**Job Card 0 张**、`skip_transfer=1` |
| 原生 Manufacture | `MAT-STE-2026-00009`：成品仓 `LM90-FG` **0 → 1**（价值 100），原料仓 `LM90-RM` **10 → 9**，SLE **71 → 73**，`produced_qty=1.0` |
| 关键机制 | v16 `make_stock_entry()` 返回 `stock_entry.as_dict()`（不是 Document），需 `frappe.get_doc(...)` 回转后 insert/submit；`get_items()` 在无工序 BOM 下正常展开原料 |

`skip_transfer=1` 时 `from_warehouse` 自动取 `Work Order.source_warehouse`，
因此「源仓直接消耗 → 成品入库」一步完成，不需要先做 `Material Transfer for Manufacture`；
该 purpose 与 `Material Issue` 原生均可用，决策中的双重扣库风险可通过固定这一默认路径规避。

## 4. Gate：任务状态与库存解耦

- `frappe.get_hooks("doc_events")` 中 `Task` / `Project` 均为 `None`，
  现有唯一自有 hook 是 `Sales Order.validate`（BUILD-80 订单类型校验）；
  `Stock Entry` 上只有 ERPNext 原生的 MR 数量回写。**不存在任务状态连到库存的链路**。
- 真实验证：创建 `PROJ-0001` / `TASK-2026-00001`（目标日期设为昨天），
  把 Task 状态从 `Open` 改为 `Completed` 并 `save()` 触发全套 doc events，
  前后 Bin 快照完全一致、SLE 保持 **73 → 73**。
  → **任务完成不会自动完工入库**，符合决策第 44 行与 Gate 要求。

> 上述 `LM90-*` 单据、PROJ/TASK 均为本项正式测试证据，保留不删除；
> 既有演示单据（SAL-ORD / MAT-PRE / MFG-WO-00001/00002 等）一条未改。

## 5. 与四类订单 / 统一导航的改造差异

| 已有能力 | 新方向下的处理 |
| --- | --- |
| `/cn_portal` 顶部一级 + 左侧二级 | 保留，不重构；BUILD-92 在其上补「订单执行概览」 |
| BUILD-10/20/40/70 的 `my_jobs` / `update_job_progress`（Job Card 报工） | 按决策降级为后台兼容能力，**员工界面不再强制**；BUILD-93 新增 Project Task 契约并收口 |
| 四类订单（生产/耗材/零部件/服务） | 保持 BUILD-80 服务端校验；只有生产类建进度 Project，耗材/零部件直接采购交付，服务不扣库存 |
| 现有带 2 道工序的 `BOM-ASSY-X1-001` | 不修改；新链路用无工序 BOM 证明「轻生产」可行，标准/非标 BOM 由 BUILD-92 按单选用 |
| 现有 `Production Plan` / MR / PO / PR / DN / Invoice 样本 | 保留为可追溯基线，BUILD-92 聚合成订单执行概览 |

## 6. BUILD-93 契约基线（供后续增量）

现有自有 API 10 个：`report_customer / search_customers / my_orders / order_detail /
my_jobs / update_job_progress / stock_balances / prepare_purchase_draft /
cancel_purchase_draft / confirm_purchase_draft`。
决策要求的 `orders.summary` / `production.tasks.mine` / `production.tasks.update` /
`materials.shortage` **四个契约均不存在**，BUILD-93 需在原 `cn_mfg_poc.api` 上增量补齐，
不重建 H5/Bot 通道。

## 7. 登记 BACKLOG（不打断主线）

- `LM90-01`：`Task.status` 原生选项与决策「待开始/进行中/完成/异常」不一致（S2，BUILD-91 做最小映射）。
- `LM90-02`：`Project Template Task` 子表字段过少，负责人/目标日期需生成时计算（S2，BUILD-91 处理）。
- `LM90-03`：现有 Job Card 系 API 需兼容迁移或收口，避免新旧两套「我的任务」（S2，BUILD-93 处理）。
- `LM90-04`：本次只验证 `skip_transfer=1` 的直达 Manufacture 路径；
  `Material Transfer for Manufacture` 两段式路径与双重扣库防护在 BUILD-92 结合真实工单再验证（S1）。

## 8. 结论

现状审计完成、原生进度模型可复用、**无工序/无 Job Card 制造完工入库已用真实单据与库存变化验证通过**、
任务状态与库存解耦 Gate 通过，改造差异与后续增量边界清晰。
BUILD-91 可直接在 `Project Template + Project/Task` 上开始，无需新建 DocType、无需重做旧 POC、无需重置数据。
