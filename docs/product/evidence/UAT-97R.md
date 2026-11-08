# UAT-97R — 线上测试角色精简、中文岗位档案与可识别测试账号

状态：**ONLINE_PASS**（角色/账号配置迁移完成，真实账号验收通过；业务数据零改动）
执行时间：2026-11-09 00:40–01:20（Asia/Shanghai）
站点：https://d.urlxl.cn（既有测试站，**未清空订单/库存，未重置数据库**）
提交：见本文件末尾 §11（产品分支 `product/erpnext-wecom-ai-v1-20261029`）

---

## 0. 一句话结论

- 7 个业务账号全部挂上**中文岗位档案**，显示名统一为「岗位-A-姓名」；新增 2 个 A/B 对照账号（销售-B / 车间-B），共用同一档案。
- **没有删除也没有重命名任何原生 Role**：线上 48 个 Role 全为 ERPNext/Frappe 内置（`is_custom=0`），0 个自定义角色可删；本轮清理的是 5 条**多余的 Manager/Employee 角色授权**。
- 所有 `User.name`（邮箱）、User Permission、单据 owner、Project/Task 负责人、企微绑定、历史单据与库存**全部保持不变**；线上 `Stock Ledger Entry` 84 → 84、Rack 各仓数量不变。
- 真实账号验收：**线上 118/118 + 隔离用例 14/14**；本地回归 **118/118 + 14/14 + UX-96 42/42 + FLOW-97 40/40**。

---

## 1. 审计（改动前，只读）

审计脚本：`poc/deploy/uat97r_audit.py`、`uat97r_audit2.py`、`uat97r_audit3.py`（均只读，输出已脱敏）。
原始快照：`poc/deploy/uat97r_audit_clean.json`、`uat97r_audit3_clean.json`。

### 1.1 账号与授权（改动前）

| 账号 | 显示名 | Role Profile | 原生角色 | User Permission |
|---|---|---|---|---|
| zhaojingli@erpnext-poc.localhost | 赵经理 | 无 | Accounts User / Manufacturing User / Purchase User / Sales User / Stock User / **System Manager** | 无 |
| wangming@erpnext-poc.localhost | 王明 | 无 | Sales Manager / Sales User | 无 |
| liugong@erpnext-poc.localhost | 刘工 | 无 | Employee / Manufacturing Manager / Manufacturing User | Company=昆山启程；Employee=HR-EMP-00003 |
| chengong@erpnext-poc.localhost | 陈工 | 无 | Purchase Manager / Purchase User | 无 |
| zhanggong@erpnext-poc.localhost | 张工 | 无 | Employee / Stock Manager / Stock User | Company=昆山启程；Employee=HR-EMP-00002 |
| ligong@erpnext-poc.localhost | 李工 | 无 | Employee / Manufacturing User | Company=昆山启程；Employee=HR-EMP-00001 |
| zhoukaiji@erpnext-poc.localhost | 周会计 | 无 | Accounts Manager / Accounts User | 无 |
| Administrator | Administrator | 无 | 45 个（框架全量） | 无 |

其他账号：`Guest`、`bot-gateway@erpnext-poc.localhost`（企微机器人通道，未改动）。

### 1.2 Role / Role Profile / DocPerm 现状

- **Role 共 48 个，全部 `is_custom=0`（ERPNext/Frappe 内置）**，无 disabled，无重复 Has Role 行（`dupes=0`）。
  → 结论：**本期没有「可安全删除的非标准自定义 Role」**，任务 §2.4 的删除条件不成立，未删除任何角色。
- Role Profile 共 5 个，全部为 ERPNext 官方英文档案：`Accounts / Inventory / Manufacturing / Purchase / Sales`，**无任何用户挂载**（`users=[]`）。
- 自定义 DocPerm 仅 7 条，全部挂在 `Address` 上（All/Sales/Purchase/Accounts/Maintenance/System Manager），属 BUILD 期有意配置，**未改动**。
- `User Permission` 共 6 条，只作用于 3 个生产/仓库账号的 Company 与 Employee，**未改动**。
- **销售订单无任何 User Permission** → 销售 A/B 不存在行级数据域（见 §7 DATA_SCOPE_GAP）。

### 1.3 代码侧的角色耦合（决定档案怎么映射）

| 位置 | 判定的原生角色 | 含义 |
|---|---|---|
| `workspace.roles`（9 个中文工作台） | 客户与销售=Sales User；设计与生产=Manufacturing User；采购管理=Purchase User；仓库管理=Stock User；物流交付=Sales User/Stock User；财务管理=Accounts User；经营报表=五个 Manager；系统设置=System Manager | **工作台按「用户级」角色过滤**，只给 Manager 或只给 System Manager 会让对应模块整块消失 |
| `production.MANAGER_ROLES` | Manufacturing Manager / System Manager | 模板维护、任务分派 |
| `production.STAFF_ROLES` | Employee / Manufacturing User / Manufacturing Manager / System Manager | 我的任务 |
| `order_execution.SENIOR_ROLES` | System / Manufacturing / Stock / Purchase / Accounts / Sales Manager | 订单级成本与跨单可见 |
| `procurement_trace.PURCHASE_ROLES` | Purchase/Stock User+Manager、System Manager | 集中采购来源 |
| `bom_link.READ_ROLES` | 十个业务 User/Manager + System Manager | BOM 选项与反查 |

因此档案**不能**「只留 Manager」或「只留 System Manager」，否则菜单与只读入口会成片消失。

---

## 2. 七个中文 Role Profile（交付物）

| 中文岗位档案 | 绑定的原生角色 | 权限范围 | 保留/新增说明 |
|---|---|---|---|
| **经营管理** | System Manager + Sales/Manufacturing/Purchase/Stock/Accounts User | 全部业务单据 + 经营报表 + 系统设置 | 保留原 6 角色。**含 System Manager，属管理员口径**（见 §2.1） |
| **销售业务** | Sales User | 客户报备、四类销售订单草稿/提交/取消、本单 BOM 选用、交付进度、交货单 | 移除 Sales Manager |
| **设计生产** | Manufacturing User + Manufacturing Manager | 物料/BOM、九阶段模板维护、建项目与分派、生产计划/工单/物料移动 | 移除 Employee |
| **采购业务** | Purchase User + Purchase Manager | MR、询价/报价、PO、采购来源反查、订单级 BOM 需求与缺料 | 保留 Purchase Manager，原因见 §2.2 |
| **仓库管理** | Stock User | 采购入库、原料/WIP/成品仓出入库、领料、完工入库、交货单、库存查询 | 移除 Stock Manager、Employee |
| **车间执行** | Manufacturing User | 本人九阶段任务的状态/备注/目标日期与预警 | 移除 Employee |
| **财务业务** | Accounts User | 销售/采购发票、应收应付账龄、收付款、总账、财务报表 | 移除 Accounts Manager |

幂等实现：`cn_mfg_poc/role_setup.py` + 补丁 `patches/v0_0_6/setup_role_profiles.py`（已注册到 `patches.txt` 的 `[post_model_sync]`）。
Frappe 在 `User.validate → populate_role_profile_roles` 中会把 `User.roles` **收敛**为档案角色集合，所以「挂档案」本身就是授权清理，重跑不会新增或重复。

### 2.1 为什么「经营管理」保留 System Manager

- 该账号是当前站点唯一具备 System Manager 的业务账号，用户正在用它做人工测试；移除会把「用户与参数」「系统设置」整块撤掉，有把使用者锁在门外的风险（任务 §2.3 明确要求避免）。
- 它**不是**普通业务岗位：本文件与门户页面均标注「管理员口径」，A/B 隔离与越权负例都不使用该账号，业务经理权限由 `采购业务/设计生产` 等 Manager 角色单独证明。
- 只留 System Manager 会**丢菜单**：9 个中文工作台是按用户级角色过滤的（§1.3），所以另外 5 个 User 角色是「让工作台可见」的必要条件，不是额外扩权。

### 2.2 为什么「采购业务」保留 Purchase Manager

`order_execution` / `procurement_trace` 的订单级只读入口用 `SENIOR_ROLES` 判定，只给 Purchase User 时访问销售订单会 403（实测：`Purchase User` 无 Sales Order 读权限）。
采购必须能看「我要买的需求」，所以保留 Purchase Manager，并把它登记为**实现耦合待改造项**：后续应改为独立只读口径（例如 `Purchase User` 允许读订单级聚合但不显示金额），再把该角色降级。

---

## 3. 账号 → 显示名 → 岗位（可直接照此切换）

| 岗位 | 登录账号（不可改） | 显示名 | 主要菜单 | 明确不可用 |
|---|---|---|---|---|
| 经营管理 | zhaojingli@erpnext-poc.localhost | **经营管理-A-赵经理** | 客户与销售、设计与生产、采购管理、仓库管理、物流交付、财务管理、经营报表、基础资料、系统设置 | —（管理员口径，勿用于 A/B 隔离结论） |
| 销售业务 | wangming@erpnext-poc.localhost | **销售-A-王明** | 客户与销售、物流交付、基础资料、工作台 | 集中采购、模板管理、我的任务、业务岗位管理 |
| 销售业务（对照） | xiaoshou-b@erpnext-poc.localhost | **销售-B-对照** | 同销售-A（同一档案） | 同上 |
| 设计生产 | liugong@erpnext-poc.localhost | **设计生产-A-刘工** | 设计与生产、经营报表、基础资料、工作台 | 集中采购、业务岗位管理 |
| 采购业务 | chengong@erpnext-poc.localhost | **采购-A-陈工** | 采购管理、经营报表、基础资料、工作台 | 模板管理、我的任务、业务岗位管理 |
| 仓库管理 | zhanggong@erpnext-poc.localhost | **仓库-A-张工** | 仓库管理、物流交付、基础资料、工作台 | 模板管理、我的任务、业务岗位管理 |
| 财务业务 | zhoukaiji@erpnext-poc.localhost | **财务-A-周会计** | 财务管理、基础资料、工作台 | 集中采购、模板管理、我的任务、业务岗位管理 |
| 车间执行 | ligong@erpnext-poc.localhost | **车间-A-李工** | 设计与生产（我的任务/订单生产进度）、基础资料、工作台 | 集中采购、模板管理、业务岗位管理 |
| 车间执行（对照） | chejian-b@erpnext-poc.localhost | **车间-B-对照** | 同车间-A（同一档案） | 同上 |
| 系统管理员 | Administrator | Administrator | 全量后台 | — |

密码：**不在 Git、不在本文件、不在聊天明文输出**。已生成 9 个业务账号 + Administrator 的独立随机强密码（16–20 位，含大小写/数字/符号），保存在执行机本地
`D:\ERP\poc\deploy\uat97r_credentials.online.json`（在 Git 仓库之外）。
切换账号时请先退出登录，或使用独立浏览器 Profile / 无痕窗口，避免 Cookie 混杂。

---

## 4. 授权变更明细（before → after）

| 账号 | before | after | 变化 |
|---|---|---|---|
| zhaojingli | 6 角色 | 同 6 角色 | 仅显示名 + 档案 |
| wangming | Sales Manager, Sales User | Sales User | −Sales Manager |
| liugong | Employee, Manufacturing Manager, Manufacturing User | Manufacturing Manager, Manufacturing User | −Employee |
| chengong | Purchase Manager, Purchase User | 同 | 无 |
| zhanggong | Employee, Stock Manager, Stock User | Stock User | −Stock Manager, −Employee |
| ligong | Employee, Manufacturing User | Manufacturing User | −Employee |
| zhoukaiji | Accounts Manager, Accounts User | Accounts User | −Accounts Manager |

合计撤销 5 条额外授权。撤销前已按岗位逐一验证 create/read/write/submit 需求（§6 正例），未出现功能缺口。
`Employee` 撤销后：`我的任务`（STAFF_ROLES 含 Manufacturing User）、`_my_employee()`（按 user_id 直查，不经 DocPerm）、`Employee` 类 User Permission（保留未删）均正常。

---

## 5. 对照账号与「不伪造身份」

- `xiaoshou-b@erpnext-poc.localhost` → 销售业务（Sales User），显示名 `销售-B-对照`
- `chejian-b@erpnext-poc.localhost` → 车间执行（Manufacturing User），显示名 `车间-B-对照`
- 两个账号都**没有**任何管理/财务角色，也没有 User Permission；与 A 账号同档案、不同 `User.name`，因此是「两个独立账号」，不是同一账号改名。
- 新建时 `send_welcome_email=0`、`no_welcome_mail`，密码单独设置，不走邮件。

---

## 6. 真实账号验收（不使用 ignore_permissions 模拟）

脚本：`poc/deploy/uat97r_http_check.py`（每个账号独立 Session 真登录）、`uat97r_isolation.py`、`uat97r_workshop.py`、`uat97r_ui.py`。

### 6.1 页面/接口矩阵（线上 https://d.urlxl.cn，118/118）

| 账号 | 一级菜单 | /procurement_trace | /role_profiles | /production_template | 我的任务接口 | 集中采购反查 | 订单物料追溯 |
|---|---|---|---|---|---|---|---|
| 经营管理-A-赵经理 | 9 模块 + 工作台 | 200 | 200 | 200 | 200 | 200 | 200 |
| 销售-A-王明 | 客户与销售/物流交付/基础资料/工作台 | 403 | 403 | 403 | 403 | 403 | 200 |
| 销售-B-对照 | 同 A（菜单一致） | 403 | 403 | 403 | 403 | 403 | 200 |
| 设计生产-A-刘工 | 设计与生产/经营报表/基础资料/工作台 | 403 | 403 | 200 | 200 | 403 | 200 |
| 采购-A-陈工 | 采购管理/经营报表/基础资料/工作台 | 200 | 403 | 403 | 403 | 200 | 200 |
| 仓库-A-张工 | 仓库管理/物流交付/基础资料/工作台 | 200 | 403 | 403 | 403 | 200 | 200 |
| 财务-A-周会计 | 财务管理/基础资料/工作台 | 403 | 403 | 403 | 403 | 403 | 200 |
| 车间-A-李工 | 设计与生产/基础资料/工作台 | 403 | 403 | 403 | 200 | 403 | 按是否本人订单 |
| 车间-B-对照 | 同车间-A | 403 | 403 | 403 | 200 | 403 | 403（非本人订单） |
| Administrator | 全量 | 200 | 200 | 200 | 200 | 200 | 200 |

同时核验 9 个业务账号的 `/desk`、`/production_board?view=mine`、`/order_execution`、`/wecom_h5` 均可达（200/301/302，无 500）。
计数口径：9 个业务账号 × 13 项 + Administrator 1 项 = 118。
本地同一套脚本 118/118；两轮均 `fail=0`。

### 6.2 A/B 隔离（线上 14/14，本地 14/14）

销售 A/B（销售-B 新建草稿 `SAL-ORD-2026-00011`，标记 `po_no=UAT97R-B`，docstatus=0，不产生库存/总账）：

| 断言 | 结果 |
|---|---|
| 销售-B 可新建草稿销售订单（同角色可写） | PASS 200 |
| 销售-B 门户「我的订单」含自己的单 | PASS |
| 销售-A 门户「我的订单」不含 B 的单（owner 过滤） | PASS（A 3 单 / B 1 单） |
| 销售-A 调 `api.order_detail` 打开 B 的单 | PASS 403 `该订单不属于您` |
| 销售-B 打开自己的单 | PASS 200 |
| **销售-A 在 Desk 列表仍能读到 B 的单** | 事实为 True → 记录 **DATA_SCOPE_GAP** |

车间 A/B（把 `TASK-2026-00019`（机架焊接）临时改派给车间-B，用后已完整还原）：

| 断言 | 结果 |
|---|---|
| 车间-B 改他人任务（`TASK-2026-00027`） | PASS 403 |
| 车间-A 改车间-B 的任务 | PASS 403 |
| 车间-B 可更新本人任务 | PASS 200 |
| 车间-B `tasks_mine` 出现该任务 / 车间-A 不再含该任务 | PASS |
| 任务状态变更是否产生库存事务 | 否：SLE 84 → 84，Rack 仓数量不变 |

还原后：`production_owner` 回到 `ligong`、`production_status=待开始`、其余字段逐项一致（`RESTORE_FIELDS_IDENTICAL True`），`STOCK_UNCHANGED True`。

### 6.3 显示一致性

`/cn_portal` 顶部与首页问候、`/production_board` 当前账号、`/order_execution`、Desk 用户列表都取 `User.full_name`，实测均为「岗位-A-姓名」。
`/cn_portal` 左侧身份区新增「岗位：<中文档案>」，英文原生角色退到 `title` 悬停里做技术核对。
`/wecom_h5` 页面本身不展示姓名，身份仍由后端 `WeCom User Binding` 决定（4 条绑定全部未变，见 §9）。

---

## 7. 数据范围现状（诚实结论）

**DATA_SCOPE_GAP（未修复，按任务要求不擅自加全局数据域规则）**

1. 销售订单**没有** `User Permission`，DocPerm 也没有 `if_owner`：
   - 门户 `/cn_portal` + `api.my_orders` + `api.order_detail` 按 `owner` 过滤，A 看不到 B 的单据详情；
   - 但 **Desk 销售订单列表**对两者都返回全部 11 张订单（实测 A 能看到 B 的 `SAL-ORD-2026-00011`）。
   - 若要让 Desk 也隔离，需要新增 `if_owner` 的 Custom DocPerm 或 `User Permission`（按 Sales Person / Territory），会**阻断原生交付协作**，必须由用户确认后单独做。
2. 门户首页 KPI 原用 `frappe.client.get_count`（全局计数），会让销售-A 看到全部订单数。本轮只把**展示口径**对齐为「非管理角色数本人订单」（`my_orders` 同源），**未改动任何 DocPerm 或数据域**；Desk 内仍是全局。
3. Task 无 DocPerm（`Projects User/Manager` 才有），`/production_board` 与 H5 走自有 API 并强制 `production_owner=本人`；因此车间 A/B 的隔离是**服务端强校验**，不依赖 Desk。

---

## 8. 部署（线上）

- 备份：`/app/backup/uat97r/20261109-005611/`
  - `brj_erp.sql` 13M，760 张表，`-- Dump completed on 2026-11-09 0:56:23`（仅 GTID 提示，非错误）
  - `cn_mfg_poc/` 应用目录全量副本
- 发布脚本：`poc/deploy/uat97r_deploy.sh`（备份 → 解包 → 校验 → `migrate` → `clear-cache` → 重启 4 个 systemd 单元）
- `migrate exit=0`，补丁输出：
  ```
  UAT97R_PROFILES {'created': ['经营管理','销售业务','设计生产','采购业务','仓库管理','车间执行','财务业务'], 'updated': [], 'unchanged': []}
  UAT97R_IDENTITIES_CHANGED 7 / 7
  ```
- 服务：`web / worker / socketio / schedule / redis` 全部 `active`，`ping=200`
- 线上文件指纹（md5 前 12 位）：`role_setup.py db6f6443c378`、`www/role_profiles.py 86bd21165af1`、`www/role_profiles.html 38d96993a979`、`www/cn_portal.py c8d12d75c090`、`www/cn_portal.html ce66f5ac0874`、`patches/v0_0_6/setup_role_profiles.py 1deb06460d0f`、`patches.txt 852d0f853940`

---

## 9. 业务数据与身份零改动核验

| 项目 | 改动前 | 改动后 |
|---|---|---|
| `Stock Ledger Entry` | 84 | **84** |
| `Bin` 行数 / Rack 各仓 | 9 行；原料仓 0、在制仓 2 | 9 行；原料仓 0、在制仓 2 |
| Sales Order | 10 | 11（仅新增 `SAL-ORD-2026-00011` 草稿，标记 `UAT97R-B`，未提交） |
| MR / PO / PR / WO / SE / DN | 3 / 3 / 17 / 3 / 9 / 5 | **3 / 3 / 17 / 3 / 9 / 5** |
| Project / Task | 2 / 27 | **2 / 27**（`TASK-2026-00019` 已还原） |
| Sales Invoice / Payment Entry | 6 / 6 | **6 / 6** |
| 单据 owner 分布 | 按原账号 | 未变（只改 `User.first_name/full_name`） |
| 企微绑定 `WeCom User Binding` | 4 条（ligong / zhangsan→zhanggong / zhaojingli / wangming-wx） | **4 条不变**，`erp_user` 全部可解析，姓名随 full_name 自动更新 |
| 用户密码 | 全部 `ErpV1@2026`（已披露） | **9 个业务账号 + Administrator 各自独立随机强密码** |

`User.name`（邮箱）一律未改，因此 `Sales Order.owner`、`Task` 负责人、审计日志、通知、企微绑定均不受影响。

---

## 10. 未覆盖与风险

1. **DATA_SCOPE_GAP**（§7）：Desk 列表无行级隔离；需用户确认后才能加 `User Permission` / `if_owner`。
2. **采购业务保留 Purchase Manager**（§2.2）：属实现耦合，建议下一轮改为只读聚合口径后降级。
3. **设计生产无 Project/Task 的 Desk 权限**：`Task` 只有 `Projects User/Manager` 有 DocPerm，本轮未扩权（避免 Project 删除权限），分派统一走 `/production_board`。
4. **企微真人联调仍 REAL_WECOM_BLOCKED**：H5/机器人身份取自后端绑定，Mock 白名单模式未改动；本轮只验证了绑定未被破坏。
5. **密码交付**：仅落本机 `uat97r_credentials.online.json`；若该文件丢失，可用 `uat97r_apply.py` 重新轮换（会再次生成全部新密码）。未在 Git/聊天/页面中出现明文。
6. 新增草稿 `SAL-ORD-2026-00011` 仅用于 A/B 对比，未提交，可由用户自行删除或留作样本。

---

## 11. 回退方式

1. 角色/显示名回退：`/app/backup/uat97r/20261109-005611/cn_mfg_poc` 覆盖应用目录 + 恢复 `brj_erp.sql`（含改动前 `Has Role`、`Role Profile`、`full_name`）。
2. 仅回退某个账号：清空 `User.role_profiles` 并按 §1.1 表格恢复 `roles`，`full_name` 改回原值；`role_setup.py` 的 `PROFILES` 是唯一数据源，改它再重跑 `sync_identities()` 即可。
3. 回退后无需 migrate（本轮无 schema 变更，只有数据与页面）。

---

## 12. 提交

- 代码：`cn_mfg_poc/role_setup.py`、`patches/v0_0_6/setup_role_profiles.py`、`patches.txt`、`www/role_profiles.{py,html}`、`www/cn_portal.{py,html}`
- 测试脚本：`poc/scripts/release96_verify.py`（断言放宽为「包含姓名」，适配新显示名）
- 执行脚本（不入库，留本机）：`poc/deploy/uat97r_*.py|sh`
- Git commit 见 `git log`（产品分支 `product/erpnext-wecom-ai-v1-20261029`）
