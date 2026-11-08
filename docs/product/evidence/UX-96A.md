# UX-96A 生产入口补齐（模板配置 / 建项目 / 分派负责人）

- 日期：2026-11-08
- 分支：`product/erpnext-wecom-ai-v1-20261029`
- 站点：本地 `erpnext-poc.localhost`（Docker `poc-frappe`）→ 线上 `https://d.urlxl.cn`
- 关联任务：`docs/product/tasks/UX-96A.md`
- 关联文件：`cn_mfg_poc/production.py`、`cn_mfg_poc/www/production_board.{py,html}`、
  `cn_mfg_poc/www/production_template.{py,html}`、`cn_mfg_poc/www/cn_portal.py`、
  `cn_mfg_poc/api.py`、`scripts/release96_verify.py`

## 1. 结论

生产入口从「只有只读进度页」补齐为**管理员可在中文门户完成的闭环**：
配置九阶段模板 → 为生产订单生成项目（幂等）→ 改负责人/目标日期/备注 → 打开原生项目。
三项动作全部服务端按真实角色校验，前端只是入口；任务操作全程不产生任何库存过账。

线上真实角色实测（`zhaojingli` 生产负责人 / `wangming` 销售经理 / `ligong` 生产人员 /
`zhanggong` 仓库），后端断言 **38/38**、浏览器交互 **29/29**、本地回归 **42/42**，均 0 error。

关键实测事实：

| 事实 | 线上证据 |
| --- | --- |
| 模板可维护，且只影响**之后**新建的项目 | 工期 3→4，新建 `PROJ-0002` 第一阶段 end=2026-11-12（start+4）；历史 `PROJ-0001` 9 个任务日期逐字段不变；工期恢复 3 后 `PROJ-0002` 日期不变 |
| 一订单一项目且幂等 | `SAL-ORD-2026-00005` → `PROJ-0002`（`TASK-2026-00019~00027`）；重复调用 `replayed=True`，任务数 9→9 |
| 分派显示中文姓名 | 机架焊接 → 李工（`TASK-2026-00019`），机加工件 → 张工（`TASK-2026-00020`，目标 2026-11-20） |
| 任务操作不过账 | 全过程 `sle=52 / bin_qty=135 / bin_rows=7` 前后完全一致 |
| 非管理不能建/分派/改模板 | 5 条负例全部抛 `PermissionError` / `ValidationError`（见 §3） |

## 2. 交付内容

### 2.1 后端接口（`cn_mfg_poc.production`，均带 `_audit` 审计）

| 接口 | 方法 | 权限 | 说明 |
| --- | --- | --- | --- |
| `template_detail()` | GET | 生产负责人/系统管理员 | 返回 9 阶段 task/subject/start/duration/description + `native_url` + `effect_note` |
| `template_update_task(task, subject, start, duration, description)` | POST | 同上 | 仅允许改 `is_template=1` 的模板 Task，并同步 `Project Template Task.subject` |
| `template_move_task(task, direction)` | POST | 同上 | 交换 `idx` 调序 |
| `order_board(sales_order)` | GET | 有订单读权限或管理角色 | 订单 + 项目 + 任务（`owner_name` 中文、`template_index`）+ `can_manage`/`can_create`/`create_block_reason`/`stock_note` |
| `create_project(sales_order, start_date, owners)` | POST | 生产负责人/系统管理员 | 幂等；非生产订单、未提交订单一律拒 |
| `assign_task(task, owner, exp_end_date, note)` | POST | 生产负责人/系统管理员 | 返回 `owner_name`；写 `production_owner`/`production_note`/`exp_end_date` |
| `assignable_users()` | GET | 生产相关角色 | 只列启用且带生产/员工角色的用户，返回中文姓名 |

`setup_template()` 语义改为「模板已存在即视为人工配置权威」：不再用代码里的
`STAGES` 覆盖管理员改过的阶段，仅在模板 0 行时自愈（`repaired_empty_template`）。

### 2.2 中文门户入口

- `/production_board?view=order`：订单信息卡（订单/客户/交期/状态/项目链接）、
  未建项目时的「创建生产进度」+ 拒绝原因、Manager 行内「负责人下拉（中文名）+ 目标日期 +
  备注 + 保存」、`打开项目`、`补齐缺失阶段`、右上「任务模板管理 →」。
- `/production_template`：9 阶段名称/开始天/工期/描述可改、↑↓ 调序、跳原生 Project Template；
  非 Manager 直接 `frappe.throw(..., PermissionError)`（线上实测 HTTP 403）。
- `/cn_portal`：仅 `Manufacturing Manager` / `System Manager` 追加「任务模板管理」入口。

## 3. 线上真实角色验收（https://d.urlxl.cn）

脚本：`poc/deploy/online_verify96.py`（服务器 `frappe.init` 直连，真实 session 用户）；
结果 `poc/deploy/online-ux96-verify.json`，**38/38 PASS，errors=0**。

### 3.1 权限拒绝用例（全部实测拒绝）

| 用例 | 角色 | 结果 |
| --- | --- | --- |
| A4 读模板详情 | 王明（Sales Manager，非生产管理） | `PermissionError: 仅生产负责人/系统管理员可执行该操作` |
| A6 改模板工期 | 李工（Manufacturing User） | 同上 |
| A14 非生产订单建项目 | 赵经理（管理）+ 耗材单 `SAL-ORD-2026-00002` | `ValidationError: 只有生产类订单才生成生产进度项目` |
| A15 建生产进度 | 王明（Sales Manager） | `PermissionError: 仅生产负责人/系统管理员可创建生产进度项目` |
| A16 分派他人任务 | 李工 | `PermissionError: 仅生产负责人/系统管理员可分派任务` |
| A17 跨账号改他人任务 | 张工改李工的 `TASK-2026-00019` | `PermissionError: 该任务负责人不是您（ligong@…），不能代他人更新` |
| A18 打开订单看板 | 李工（未授予销售订单读权限） | `PermissionError: 无权查看该销售订单` |
| A18b 读自己的任务 | 李工 | 通过：`tasks_mine=1`，全部任务 `production_owner=ligong` |

### 3.2 线上单据号

| 对象 | 编号 |
| --- | --- |
| 销售订单 | `SAL-ORD-2026-00005`（生产类、已提交、验收前无项目） |
| 生产项目 | `PROJ-0002`（`/desk/project/PROJ-0002`） |
| 任务 | `TASK-2026-00019`~`TASK-2026-00027`（九阶段） |
| 历史项目（对照） | `PROJ-0001`（来自 `SAL-ORD-2026-00006`） |
| 模板任务 | `TASK-2026-00001`~`00009`（`is_template=1`） |

### 3.3 浏览器点击路径（截图证据，本机留档不含凭据）

1. 赵经理登录 → `/production_board?view=order` → 选 `SAL-ORD-2026-00005`：
   项目号 `PROJ-0002` 可见、九阶段 9 行、9 个负责人下拉、下拉含「李工/张工」。
   → `poc/deploy/online_shots/ux96a_01_order_board.png`
2. 第 2 阶段改派张工 + 目标日期 2026-11-20 + 备注 → 保存：
   提示「已保存 机加工件加工 → 张工（库存未变动）」。
   → `ux96a_02_assign_saved.png`
3. `/production_template`：9 行；改第一阶段工期 3→4 → 保存提示「已保存阶段「机架焊接」（仅影响之后新建的进度）」；
   刷新后仍为 4，再改回 3。 → `ux96a_03_template.png`
4. 李工登录 → `/cn_portal`：无「任务模板管理」入口（`ux96a_06_worker_portal.png`）；
   直接访问 `/production_template` → **HTTP 403**（`ux96a_07_worker_denied.png`）；
   `/production_board?view=mine` 可见自己的「机架焊接」，无改派下拉（`ux96a_08_worker_tasks.png`）。

## 4. 本地回归

`scripts/release96_verify.py`（容器内 `./env/bin/python`）**42/42 PASS**，覆盖
模板读写、建项幂等、新旧项目排期分流、中文姓名、6 条权限负例、库存前后一致（SLE 67→67）。

## 5. 本轮发现并修复的缺陷

1. **线上部署脚本第 7 步 `clear-cache` 崩溃**：在 `/app/erpnext-v1` 执行 `frappe clear-cache`
   会按 cwd 找 `./apps.txt`，报 `OSError: b'./apps.txt' Not Found`，导致服务未重启。
   已改为在 `sites` 目录执行（与 `migrate` 一致的约定），并单独补跑：4 个 systemd 单元
   `web/worker/socketio/schedule` 全部 `active`，`/api/method/ping` = **200**。
2. **模板页非管理员 403 提示语**原先依赖 500 页，现由 `frappe.throw(PermissionError)`
   返回 403 并给出「仅生产负责人」中文原因。

## 6. 未覆盖 / 风险

- 项目起始日默认取当天：`SAL-ORD-2026-00005` 交期 2026-11-12，但九阶段排到 2026-12-03，
  看板已把「临期/逾期」显性化，**是否按交期倒排**属产品口径，登记到 BACKLOG 待定。
- 生产人员（Manufacturing User）在线上无销售订单读权限，因此看不到订单看板，只能看
  「我的任务」；若希望其在看板里只读自己订单，需单独授权（未擅自放开）。
- 真实企微入口仍为 `REAL_WECOM_BLOCKED`（与本任务无关）。

## 7. 证据清单

- 脚本：`poc/deploy/online_verify96.py`、`poc/deploy/online_finalize96.py`、
  `poc/deploy/online_ui96.py`、`poc/deploy/release96_deploy.sh`、`poc/deploy/patch96_fix2.sh`
- JSON/日志：`poc/deploy/online-ux96-verify.json`、`poc/deploy/online-final2.txt`
- 截图：`poc/deploy/online_shots/ux96a_01_order_board.png`、`ux96a_02_assign_saved.png`、
  `ux96a_03_template.png`、`ux96a_06_worker_portal.png`、`ux96a_07_worker_denied.png`、
  `ux96a_08_worker_tasks.png`
- 线上发布：备份 `/app/backup/ux96/20261108-220817`（DB 13M + 应用目录）、
  二次补丁备份 `/app/backup/ux96/fix2-20261108-222158`
