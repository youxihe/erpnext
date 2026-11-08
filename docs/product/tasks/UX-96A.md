# UX-96A — 九阶段生产任务的创建、模板维护与负责人分派

## 问题（用户线上提出）
管理员进入 https://d.urlxl.cn/production_board?view=order 只能看到九阶段及当前订单进度，却看不到：九阶段在哪配置、怎样给新生产订单生成任务、如何改负责人/目标日期。

## 当前源码已证实
- `cn_mfg_poc/production.py` 中 `setup_template()` 初始化 `Project Template: 整机生产九阶段` 及九个原生模板 Task；九个默认阶段的初始描述/起点/时长写在 STAGES，但订单 Project/Task 的真正来源应当是数据库中的 Project Template。
- 生产订单与项目通过 `Project.sales_order` / `Sales Order.project` 关联，具体 Task 通过 `Task.project` 和 `Task.source_sales_order` 关联。
- 已有权限受控接口 `create_project(sales_order, start_date, owners)`、`assign_task(task,owner,exp_end_date)`、`tasks_update(...)`。
- 现有 `www/production_board.html` 的“订单生产进度”只有订单选择 + 刷新 + 只读表；“我的任务”仅本人状态/备注更新。因此这不是用户操作失误，而是管理端缺入口。

## 最小实施（不得重构原生 ERP）
1. 在顶部「设计与生产」→左侧「固定生产进度」下提供**管理员/生产经理**可见的“任务模板管理”，可打开原生 Project Template 和所引用模板 Task，支持编辑九阶段名称、顺序、默认排期参数（必要时仅补小型配置表单），并能知道模板变更**只作用未来新项目**，已生成历史任务保持不变。不要直接修改 STAGES 常量作为日常管理方式；升级/迁移不要覆盖人工编辑后的模板。
2. “订单生产进度”选择生产类**已确认**订单：尚无 Project 时显示“创建生产进度”；点击经已有后端 `create_project` 幂等生成 9 Task（重复点击不重复）；已有时显示“打开项目”和真实 Project ID。
3. 管理员/生产经理在当前表格能改负责人、目标日期及必要备注，复用现有 `assign_task`；列表显示业务人员中文姓名（查 User.full_name），不强制只能看邮箱 ID。普通员工只通过“我的任务”更新本人状态/备注，不能分派他人任务。
4. 允许管理人员修改**已有订单任务**的目标时间或备注。不要让模板变化反写已经启动的项目，避免历史数据无意变更；如果模板扩展/减少阶段，新增项目按新的模板生成，旧项目由管理员决定是否补充。
5. 权限必须后端校验：非生产订单不能创建；非管理人员不能创建/分派；跨账号不能改他人任务；原有 H5、Bot 的 Task 读写接口不退化。
6. 保留“Task 全部完成 != Work Order 完工入库”。操作 Project/Task 时 Stock Ledger / Bin 不变。

## DoD & 验收
- 用 Administrator 可以从 /cn_portal 找到模板管理/订单生产进度：打开「整机生产九阶段」，看到并可维护完整九项。
- 用一张新的已提交生产 Sales Order 点击创建进度，新增 Project 与 9 Task；重复点击仅返回同项目；能调整负责人/目标日期并看到预警；本人在 PC/H5 查询一致。
- 模板编辑之后新项目生效、历史项目不被静默覆盖；权限拒绝和库存不变测试 PASS。
- 本地测试通过后部署已有 https://d.urlxl.cn，保存线上测试订单号、Project/Task ID、点击路径、截图和回归证据。不要重置线上数据或误用历史测试号。
- 输出 `docs/product/evidence/UX-96A.md`、Git commit，更新 QUEUE 状态。

## 本期不做
完整 MES、工序工时、复杂生产排程、独立生产数据库、Job Card 强制报工。