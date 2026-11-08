# BUILD-91 证据：固定生产进度项目与九任务模板

日期：2026-11-08
分支：`product/erpnext-wecom-ai-v1-20261029`
权威依据：`docs/product/decisions/LIGHT_MANUFACTURING_20261108.md` + `docs/product/QUEUE.md` 的 BUILD-91 条目
环境：本地 POC Docker（`poc-frappe` / `poc-mariadb` / `poc-redis-*`），Site `erpnext-poc.localhost`，Frappe 16.53.0 / ERPNext 16.52.1

## 1. 范围与做法

只做增量：保留 BUILD-00～90 全部成果、不重建 Site、不重置任何业务数据。生产人员只更新 `Project / Task` 的过程状态、目标日期、备注、附件；**不强制 Job Card、不由 Task 触发任何库存事务**。

| 项 | 实现 | 位置 |
|---|---|---|
| 九阶段可配置模板 | `Project Template` = `整机生产九阶段`，9 行，模板 Task 的 `start/duration` 分别为 0/3、3/4、7/3、10/2、12/3、15/3、18/2、20/3、23/2 | `cn_mfg_poc/production.py` `STAGES`、`setup_template()` |
| 最小自定义字段 | `Task.production_owner / production_status / production_note / production_attachment / source_sales_order`，不新建 DocType | `CUSTOM_FIELDS` |
| 状态映射 | 待开始→`Open`、进行中→`Working`、已完成→`Completed`、异常→`Pending Review`；完成同时写 `completed_on/completed_by` | `STATUS_TO_NATIVE`、`tasks_update()` |
| 一单一项目 | 生产类、已确认的 Sales Order ↔ 唯一 `Project`（`Project.sales_order`），原生 `after_insert` 回写 `Sales Order.project`；重复调用返回原项目，不重复建 Task；缺阶段时按 subject 补齐 | `create_project()`、`_ensure_project_tasks()` |
| 预警 | 逾期=目标日已过且未完成；临期=未来 N 日内到期且未完成，N 默认 3，可由 `site_config.production_due_soon_days` 覆盖；只读计算不写库 | `due_state()`、`due_soon_days()` |
| 权限 | 生产经理/系统管理员可创建项目、分派；本人只能更新本人任务；销售角色仅可读订单进度、不可建项目/看任务/改任务 | `_require()`、`create_project/assign_task/tasks_update/tasks_mine/order_progress` |
| PC 入口 | `/production_board?view=mine`（我的任务）、`?view=order`（订单生产进度），在 `/cn_portal`「设计与生产」注入；销售角色看不到该工作台时回退挂到「客户与销售」 | `www/production_board.py|html`、`www/cn_portal.py:_inject_production_links()` |

## 2. 实测发现与修复（关键技术点）

1. **`Task.is_template` 必须显式置 1**：ERPNext v16 `Task.validate_status()` 会把 `status="Template" and not is_template` 的状态强制改回 `Open`；`Project Template.validate_template_tasks()` 又只认 `is_template=1`。早期失败 setup 生成了 18 条 `is_template=0 / status=Open` 且无 `project` 的孤儿 Task。修好字段后，`setup_template()` 自愈：复用并修正 `TASK-2026-00002`～`00010` 为模板，清理 `TASK-2026-00011`～`00019` 这 9 条纯副本（均为本次失败脚本自建、无单据引用）。第二次执行 `setup_template()` 输出 `created/repaired/removed` 全为空，证明幂等。
2. **不能用原生 `Project.after_insert() → copy_from_template()`**：v16 `create_task_from_template()` 内部用 `.insert()` 而非 `ignore_permissions=True`，而原生 `Task` DocPerm 只给 `Projects User / HR Manager` 建单权限，生产经理会抛 `PermissionError`（实测 traceback 见排查记录，`after_insert` 中断后 Project 行残留且 0 个 Task、Sales Order.project 未回写）。改为：insert 前不设 `project_template`（`after_insert` 仍原生回写 `Sales Order.project`），insert 后 `db_set` 模板名，再由本模块读 `Project Template` 行、复用原生 `project.calculate_start_date/calculate_end_date()` 生成 9 个原生 Task（`ignore_permissions=True`）。未改动 ERPNext 核心与 DocPerm。
3. **项目结束日留缓冲**：九阶段最长到 `start+25` 天，节假日顺延；`Task.validate_parent_project_dates()` 会对 `exp_end_date > Project.expected_end_date` 的新建任务抛 `InvalidDates`，故 `expected_end_date = start + 35` 天。
4. **门户模块缓存**：修改 `www/cn_portal.py` 后需 `touch` 触发 `frappe serve` 的 reloader；重载前销售角色读到旧菜单（HTTP 23/24），重载后 24/24。

## 3. 真实单据与数据（非模拟）

| 对象 | 真实 ID / 值 |
|---|---|
| 生产类销售订单 | `SAL-ORD-2026-00005`（生产类、docstatus=1、To Deliver and Bill） |
| 九阶段模板 | `整机生产九阶段`（9 行），模板 Task `TASK-2026-00002`～`TASK-2026-00010` |
| 生产进度 Project | `PROJ-0002`，`Sales Order.project` 回写为 `PROJ-0002` |
| 九个生产 Task | `TASK-2026-00019` ～ `TASK-2026-00027` |
| 目标日期示例 | 机架焊接 2026-11-08→2026-11-11；机加工件加工 2026-11-11→2026-11-15；内钣金焊接 2026-11-15→2026-11-18 |
| 分派 | `TASK-2026-00019` → 李工 `ligong@erpnext-poc.localhost`；`TASK-2026-00020` → 刘工 `liugong@erpnext-poc.localhost` |
| 本人更新 | `TASK-2026-00019` 进行中（备注「机架已上工装」）→ 已完成（备注「焊接完成」），`completed_on=2026-11-08`，原生 `status=Completed` |
| 预警样例 | `TASK-2026-00020` 逾期、`TASK-2026-00021` 临期、`TASK-2026-00022` 正常，`due_soon_days=3` |
| 订单进度聚合 | `total=9, completed=1, overdue=1, due_soon=1` |
| 库存 Gate | 全程 `Stock Ledger Entry` 计数 **73 → 73**，`tabBin` 全量快照一致；`doc_events` 中 `Task` / `Project` 均为 `None` |
| 非生产订单 | `SAL-ORD-2026-00002`（耗材）、`SAL-ORD-2026-00004`（服务）均被「只有生产类订单才生成生产进度项目」拒绝 |

## 4. 测试结果

- 服务端真实测试 `product/scripts/build91_verify.py`：**27/27 PASS，0 异常**（`build91-verify.json`）。
  覆盖：模板 9 项、5 个字段、建项目、9 个 Task、来源订单回填、日期计算、`Sales Order.project` 回写、重复创建幂等（9→9）、分派、销售角色双负例、代他人更新拒绝、本人任务只见本人、本人更新状态/备注/完成时间、原生状态映射、逾期/临期/正常/已完成四态、汇总计数、订单进度聚合、库存与 SLE 不变、无库存 hook、非生产订单拒绝。
- 真实 HTTP 回放 `product/scripts/build91_http_verify.py`：**24/24 PASS**（`build91-http.json`）。
  覆盖：4 个身份的 `/cn_portal` 菜单按角色注入且四类订单入口不回退、`/production_board` 200、李工只见 1 项本人任务、销售角色可见 2 张生产订单且可读 9 阶段进度、销售角色更新/创建均 HTTP 403、未登录 403、HTTP 重复创建返回 `PROJ-0002` 且任务数保持 9、SLE 73→73。
- 幂等配置 `product/scripts/build91_setup.py`：`build91-setup.json`，第二次执行无新增/修复/删除。

## 5. 点击路径（PC）

1. 访问 `http://127.0.0.1:18000/cn_portal` → 顶部「设计与生产」→ 左侧「固定生产进度」。
2. 「我的任务」→ 打开 `/production_board?view=mine`：KPI（总数/逾期/临期/已完成）+ 任务表，每行可改状态、填备注后点「保存」。
3. 「订单生产进度」→ 打开 `/production_board?view=order`：下拉选生产类订单，查看九阶段负责人、目标日期、预警、状态、完成时间与备注（只读）。
4. 销售角色登录后顶部「客户与销售」→「固定生产进度 → 订单生产进度」；不应出现「我的任务」。
5. 原生 Desk 可用 `Project / PROJ-0002`、`Task / TASK-2026-00019` 直接核对同一数据。

## 6. 权限负例（实测）

| 身份 | 动作 | 结果 |
|---|---|---|
| 王明（Sales Manager / Sales User） | 创建生产进度项目 | `PermissionError: 仅生产负责人/系统管理员可创建生产进度项目`，HTTP 403 |
| 王明 | `tasks_mine` | `PermissionError: 当前角色无权查看生产任务`，HTTP 403 |
| 王明 | `tasks_update` | HTTP 403 |
| 李工 | 更新刘工负责的 `TASK-2026-00020` | `PermissionError: 该任务负责人不是您（liugong@…），不能代他人更新` |
| 未登录 | `tasks_mine` | HTTP 403 |
| 刘工（Manufacturing Manager） | 创建 / 分派 / 重复创建 | 允许，重复创建返回 `replayed=True` 且任务数不变 |

## 7. 未改动 / 不回退

- BUILD-80 四类订单分类入口、标准筛选与服务端校验保持可用（HTTP 验证按角色核对）。
- BUILD-90 的无 Job Card 制造链路与既有库存数据不动；本轮 SLE 恒定 73。
- Job Card 原生能力与旧 `my_jobs` / `update_job_progress` API 保留，员工界面不强制打开（收口留待 BUILD-93）。
- `/cn_portal` 顶部一级 + 左侧二级布局未重构，仅新增一个分组。
- 未修改 ERPNext / Frappe 核心文件，未新增 DocType，未调整任何 DocPerm。

## 8. 复现命令

```bash
# 容器内执行（脚本与密钥经 /hostshare 挂载，密钥文件不进 Git）
docker exec poc-frappe sh -c 'cd /workspace/development/frappe-bench/sites && \
  exec /workspace/development/frappe-bench/env/bin/python /hostshare/build91_setup.py'
docker exec poc-frappe sh -c 'cd /workspace/development/frappe-bench/sites && \
  exec /workspace/development/frappe-bench/env/bin/python /hostshare/build91_verify.py'
docker exec poc-frappe sh -c 'cd /workspace/development/frappe-bench/sites && \
  exec /workspace/development/frappe-bench/env/bin/python /hostshare/build91_http_verify.py'
# 修改 www/*.py 后触发 dev server 重载
docker exec poc-frappe sh -c 'touch /workspace/development/frappe-bench/apps/cn_mfg_poc/cn_mfg_poc/www/*.py'
```

## 9. 状态与剩余项

结论：**PASS(LOCAL)**。真实企业微信真人 UAT 仍缺授权（`REAL_WECOM_BLOCKED`），不在 BUILD-91 范围内虚报通过。
非关键观察已登记 `docs/product/BACKLOG.md` 的 `LM91-01`～`LM91-04`；订单实物流转与三入口接力分别在 BUILD-92 / BUILD-93 继续。
