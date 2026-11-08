# RELEASE-95 发布证据：BUILD-90～94 Review Fix + d.urlxl.cn 线上测试发布

- 发布日期：2026-11-08（CST）
- 执行人：Workbuddy
- 产品分支：`product/erpnext-wecom-ai-v1-20261029`
- 部署源 commit：`12861af4`（含 P0 修复 `610db60e`）
- 线上站点：https://d.urlxl.cn （测试环境，**不是**生产客户系统）
- 结论：**ONLINE_PASS（HTTP / REST / 真实普通用户登录态）**，真实企业微信真人 UAT 仍 `REAL_WECOM_BLOCKED`

> 本文不含任何登录口令、数据库密码、Token 或 Secret。测试账号均在隔离测试站点，非客户真实账号。

## 1. 版本对照

| 项 | 发布前 | 发布后 |
| --- | --- | --- |
| 线上 `cn_mfg_poc` | BUILD-80（无 `production.py` / `order_execution.py` / `production_board`） | BUILD-90～94 + RELEASE-95 修复 |
| Frappe / ERPNext | 16.53.0 / 16.52.1 | 未变更（16.53.0 / 16.52.1） |
| 数据库 | 云 MySQL 8.0.30-txsql / `brj_erp` | 未重建、未换库，原地迁移 |
| 部署源 SHA | — | `12861af4`（产品分支） |
| 本地对照 | 同一 commit 的 Docker POC 站点 | 一致（`docs/product/evidence/BUILD-94.md`） |

## 2. 备份与回滚

- 备份目录：`/app/backup/release95/20261108-183543`
- 数据库：`brj_erp.sql`（13 MB，`mysqldump --single-transaction`），`gzip -t` 通过，`-- Dump completed` 完整结束
- 表数量校验：库内 760 张表 = dump 内 760 个 `CREATE TABLE`
- 同时备份：站点文件 `site-files.tar.gz`、旧 app `app-cn_mfg_poc.tar.gz`、被补丁的 Frappe 文件 `frappe-patched-files.tar.gz`，全部记录 SHA256（`SHA256SUMS`）
- 发布前业务基线：`pre-rowcount.txt`（销售订单 5、项目 0、任务 0、工单 2、库存移动 7、SLE 70、Bin 9、物料 7、用户 10、自定义字段 13、DocType 834）
- 发布后逐项比对：**全部 SAME**，无数据丢失
- 回滚方法：
  1. `mysql brj_erp < /app/backup/release95/20261108-183543/brj_erp.sql`（需具备建表权限的账号）
  2. `rm -rf /app/erpnext-v1/apps/cn_mfg_poc && tar -xzf .../app-cn_mfg_poc.tar.gz -C /app/erpnext-v1/apps`
  3. `redis-cli -p 6380 -n 1 FLUSHDB` 后重启 `erpnext-v1-web/worker/schedule`
- 数据库账号 `sid_admin` 无 `DROP` 权限，因此未做「导入到临时库验证恢复」的演练；改为表数一致 + dump 完整标记 + 逐表基数比对的等价校验，风险在 BACKLOG `DB-02` 中登记。

## 3. 迁移与兼容补丁（含本次新发现）

执行顺序：**应用代码 → 表名大小写补丁 → MySQL 8 兼容补丁 → `bench migrate` → 清缓存 → 重启**。

| 步骤 | 结果 |
| --- | --- |
| `patch_lower_case_tables2.sh` | 幂等重放，`_normalize_table_names` 存在 |
| `patch_mysql8_compat.sh` | 原 6 项 `SKIP_ALREADY_PATCHED`，新增 2 项首次应用 |
| `bench migrate` | 0 traceback，`Syncing fixtures` / `after_migrate` 正常结束 |
| 新补丁 `v0_0_3.setup_production_template` | 创建 Task 自定义字段 5 个、模板 Task 9 个、Project Template「整机生产九阶段」 |

### 3.1 本次发现并修复的两个真问题

1. **`information_schema.is_generated` 不兼容 MySQL 8（新）**
   - 现象：迁移中创建 Task 自定义字段报 `(1054, "Unknown column 'is_generated' in 'field list'")`，导致生产模板初始化失败。
   - 根因：Frappe 的 `mariadb` 驱动在 `get_columns()` 里选 `information_schema.columns.is_generated`（MariaDB 专有列），MySQL 8 只有 `EXTRA`/`GENERATION_EXPRESSION`。
   - 处理：改为两库通用的 `(EXTRA LIKE '%%GENERATED%%')`（注意 `%` 需转义，否则报 `not enough arguments for format string`）；写入 `patch_mysql8_compat.sh` 第 4 项，可重复执行。
2. **补丁阶段选错**
   - 现象：把模板初始化放在默认（`pre_model_sync`）阶段时，`tabDocField` 尚未同步，创建自定义字段必然失败。
   - 处理：`patches.txt` 改为显式分段，模板初始化放入 `[post_model_sync]`；重放后成功，且可重复执行（本地二次执行输出全为 `[]`）。

## 4. P0-1 缺料口径修复（前后对照，真实单据）

旧公式 `required - available_now - received_qty - issued_net` 把已进入 Bin 的采购入库又减一次，**低报缺料**。
新公式 `max(0, 需求×(1-已完工比例) - 源仓 Bin 可用 - 已领未耗)`，并按交期顺序在多单间分配同仓库存。

本地真实单据对照（`poc/scripts/release95_shortage_verify.py`，**23/23**）：

| 场景 | 需求 | 源仓可用 | 已收 | 旧公式 | 新公式 |
| --- | --- | --- | --- | --- | --- |
| SAL-ORD-2026-00007 采购入库 1 件 | 2 | 1 | 1 | 0（低报） | **1（正确）** |
| 再入库 1 件 | 2 | 2 | 2 | 0 | 0（真正备齐） |
| 全部领料到在制仓 | 2 | 0 | 2 | 0 | 0（已领未耗抵扣） |
| 已完工订单 SAL-ORD-2026-00008 | 2 | 0 | 2 | 0 | 0（剩余需求归零） |
| 同仓多单 | — | — | — | 每单重复占用库存 | 按交期顺序分配，分配量不超过实际库存 |

线上同口径验证：新订单 `SAL-ORD-2026-00006` 下单后 RACK `需 2 / 源仓 0 / 缺 2`；采购入库 2 件后 `可用 2 / 已收 2 / 缺 0`。

## 5. P0-2 真实角色单据权限（真实登录态）

口径区分：
- **脚本模拟**：BUILD-92/93/94 的 `set_user + insert(ignore_permissions=True)`，只证明流程可提交。
- **REST 真实会话**（本次）：每个角色用自己账号 `login` 后走标准 REST，服务端按 DocPerm/User Permission 判定。
- **UI 实测**（本次）：同一会话直接打开页面，状态码与关键内容见第 6 节。

本地 `poc/scripts/release95_perm_verify.py` **44/44**：

| 角色 | 真实提交成功的单据 |
| --- | --- |
| 销售 王明 | Sales Order |
| 采购 陈工 | Purchase Order、Purchase Receipt |
| 生产 刘工 | Work Order |
| 仓库 张工 | Stock Entry（领料）、Delivery Note |
| 财务 周会计 | Sales Invoice、Payment Entry |

越权与匿名负例（全部被拒）：销售建采购订单 403、销售建工单 403、采购建销售订单 403、车间李工建收付款单 403、车间李工读收付款单 403、未登录读销售订单 403、**仓库建工单 403（标准 DocPerm，工单归生产，属正确行为）**、公网 Mock 选身份 403。

结论：**标准 DocPerm 已满足业务，不需要放宽任何授权，也没有给任何账号加 System Manager 或共享 Administrator Token。**

## 6. P0-4 公网测试安全

- 修复：Mock 选身份免登增加白名单校验 `mock_mode=1` **且** `site_config: cn_mfg_poc_allow_mock_login=1`；`mock_authorize` / `mock_callback` / H5 选身份面板统一走该校验。
- 本地（白名单站点）8/8：去掉允许项后同进程调用立即 `PermissionError`，恢复后 Guest 仍可 mock 联调。
- **线上**：`/api/method/cn_mfg_poc.wecom.oauth.mock_authorize?wecom_userid=ligong` 返回 **403 "Mock 免登在本站点已禁用"**，公网访客无法再冒充业务人员。
- 仓库与工作树扫描：无明文口令、无 `api_secret`、无适配器密钥。
- 未做（登记 BACKLOG `SEC-01`）：所有测试账号仍共用同一测试口令；正式对外前需改为独立口令，并收紧公网 Administrator 访问。

## 7. 线上验收结果（真实普通用户登录态，32/32）

脚本：`poc/scripts/release95_online_acceptance.py`（可续跑，不含口令，密码由环境变量注入）
原始结果：`poc/scripts/release95-online.json`

### 7.1 页面与授权

| 检查 | 结果 |
| --- | --- |
| 销售/仓库/生产/财务 四角色打开 `/cn_portal`、`/production_board?view=mine`、`?view=order`、`/order_execution`、`/wecom_h5`、`/desk` | 24/24 全 200 |
| `/cn_portal` 含「固定生产进度」「订单执行概览」入口 | 是 |
| `/order_execution` 含物料/缺料/九阶段区块 | 是 |
| `/wecom_h5` 含「我的任务」「缺料」 | 是 |
| 列表计数 `reportview.get_count`（此前 500 的场景） | 生产 3 / 耗材 1 / 零部件 1 / 服务 1，全部 200 |

### 7.2 线上样本整机订单全链（新建，原生单据）

| 环节 | 角色 | 单据 |
| --- | --- | --- |
| 销售下单（生产类，1 台，1800） | 销售 王明 | `SAL-ORD-2026-00006` |
| 固定生产进度项目 + 九阶段任务 | 生产 刘工 | `PROJ-0001`，`TASK-2026-00010`～`00018` |
| 采购申请 | 采购 陈工 | `MAT-MR-2026-00002` |
| 采购订单 | 采购 陈工 | `PUR-ORD-2026-00002` |
| 采购入库（RACK×2） | 采购 陈工 | `MAT-PRE-2026-00016` |
| 生产工单 | 生产 刘工 | `MFG-WO-2026-00003` |
| 领料（至在制仓） | 仓库 张工 | `MAT-STE-2026-00008` |
| 完工入库（Manufacture） | 仓库 张工 | `MAT-STE-2026-00009` |
| 整机一次发货 | 仓库 张工 | `MAT-DN-2026-00005` |
| 开票 | 财务 周会计 | `ACC-SINV-2026-00006` |
| 收款 | 财务 周会计 | `ACC-PAY-2026-00006` |

（验收过程中因脚本重试多出的一组采购单据 `MAT-MR-2026-00003` / `PUR-ORD-2026-00003` / `MAT-PRE-2026-00017` 已撤销，库存已回退；概览里仍以 `docstatus=2` 保留追溯，不参与数量汇总。）

### 7.3 关键断言

| 断言 | 实测 |
| --- | --- |
| 九任务全部完成时成品仓不变 | 成品仓 `0 → 0`，SLE 不变 |
| 只有原生 Manufacture 才入库 | `0 → 1`（`MAT-STE-2026-00009`） |
| 发货后成品仓归零 | `1 → 0`（`MAT-DN-2026-00005`） |
| 重复提交已提交单据不重复过账 | HTTP 200（幂等返回），成品仓 `0→0`，SLE `83→83` |
| 缺料口径 | 下单时 RACK 缺 2；入库后可用 2 / 已收 2 / 缺 0；完工后剩余需求 0 |
| 订单执行概览 | 状态 Completed、per_delivered 100%、per_billed 100%；财务：发票 1800、未收 0、已收 1800 |
| 实物 | `produced_qty=1`、`delivered_qty=1`、`once_delivery=true`、`job_cards=0` |
| H5/接口改任务备注 → PC 可见 | `TASK-2026-00010` 备注写入后 PC 立即可见（当前任务负责人为刘工） |
| 重复创建项目不重复建单 | 二次调用返回同一 `PROJ-0001` |

### 7.4 线上库存变化（Bin）

| 物料 | 发布前 | 全链完成后 |
| --- | --- | --- |
| RACK 原材料仓 | 0 | 0（采购 2 全部领用） |
| RACK 生产在制仓 | 2（历史遗留） | 2 |
| SENSOR 原材料仓 | 40 | 39（用 1） |
| FASTENER 原材料仓 | 50 | 46（用 4） |
| ASSY-X1 产成品仓 | 0 | 0（产 1 发 1） |

## 8. 未覆盖与仍阻断

1. **真实企业微信真人 UAT 仍 `REAL_WECOM_BLOCKED`**：缺 CorpID、AgentID+Secret、可信 HTTPS 回调域名、通讯录/机器人权限；本轮线上 H5 用普通 ERP 账号登录验证，Mock 选身份已在公网禁用。
2. **生产在制仓遗留**：RACK 2 / SENSOR 1 / FASTENER 4（BUILD-80 时代遗留），需确认退回或期初调整（`LM94-03`）。
3. **九阶段负责人**：线上样本九任务默认全部落在刘工，车间李工没有任务；一人多岗/多生产员分派的默认规则需要客户确认（`LM91-05`）。
4. **共用测试口令**：测试账号仍统一口令，未改为独立口令（`SEC-01`）。
5. **数据库恢复演练**：受 `sid_admin` 无 DROP 权限限制，未做异库恢复演练（`DB-02`）。
6. BOM 多层拆分/替代料（`BOM-01`）、发票取消/红冲细节等叶子功能仍未做，按原计划等客户排序。

## 9. 判定

- 发布门槛（P0-1/P0-2/P0-3/P0-4）**全部通过**，增量已真实部署到 https://d.urlxl.cn 并通过线上验收。
- 状态：`ONLINE_PASS`（PC / REST / 真实普通用户登录态 / 库存与单据闭环）。
- 不等于生产上线，也不等于真实企微可用；上述第 8 节事项仍需客户或外部资源确认。

## 10. 发布后缺陷修复（2026-11-08 19:40，PORTAL-FIX-01）

**现象**：客户截图反馈「客户与销售 > 生产类订单」列表右上角没有「新建」按钮，无法在门户里建单。

**根因**：`/cn_portal` 用同源 iframe 打开 Frappe 原生页面，宽度适配 CSS 为了去掉重复导航，整体隐藏了 `.page-head`。而 Frappe v16 把以下操作全部挂在 `.page-head` 内（`frappe/public/js/frappe/ui/page.html`）：

- 列表页主按钮 `.primary-action` → 「添加销售订单」
- 表单页主按钮 `.primary-action` → 「保存 / 提交」
- 次级按钮、菜单、筛选（`.filters`）、刷新、列表视图切换

所以不是「代码不支持」，是**门户整合时藏过头了**；同一处还导致表单页看不到「保存」（此前 UAT 走 REST，未暴露）。

**修复**（commit `4deba804`，只改 `www/cn_portal.html` 的注入 CSS）：
- 不再隐藏 `.page-head`，改为压成 38px 白色操作条；
- 只隐藏与门户重复的 `.page-title`（内含面包屑、侧栏开关）；
- `.page-actions` 右对齐、`flex-wrap:nowrap`，主按钮不换行。

**验证**（真实登录 + 无头 Chrome，本地与线上各一轮）：

| 项 | 本地 1092×680 | 本地 1360×800 | 线上 1092×680 |
| --- | --- | --- | --- |
| 列表「添加销售订单」可见 | 是 | 是 | 是 |
| `.page-head` 高度 | 39px | 39px | 39px |
| 内层标题/面包屑可见 | 否 | 否 | 否 |
| 表单「保存」可见 | 是 | 是 | 是 |
| 从「生产类订单」新建时订单类型默认 | 生产 | 生产 | 生产 |
| 列表行/筛选区正常 | 是 | 是 | 是 |

线上发布方式：单文件替换，替换前备份 `/app/backup/release95/20261108-194454-portal/`，MD5 前后一致（`0b8d06ff…`）。`cn_portal.py` 为 `no_cache=1`，无需清缓存或重启即生效。

截图证据：`poc/deploy/online_portal_order_list.png`、`poc/deploy/online_portal_order_form.png`（本机留档，不含凭据）。

**回归矩阵（本地，Administrator 登录，1092×680，逐页在门户 iframe 内打开）**：

| 列表页 | 主按钮 | 可见 | page-head |
| --- | --- | --- | --- |
| 销售订单 | 添加销售订单 | 是 | 39px |
| 采购订单 | 添加采购订单 | 是 | 39px |
| 采购入库 | 添加采购入库 | 是 | 39px |
| 生产工单 | 添加生产工单 | 是 | 39px |
| 发货单 | 添加销售出库 | 是 | 39px |
| 销售发票 | 添加销售发票 | 是 | 39px |
| 收款单 | 添加收付款凭证 | 是 | 39px |
| 物料 | 添加物料 | 是 | 39px |

> 用销售账号（王明）测采购/工单等无权限页面时 `page-head` 为 -1，是 403 无权限页，属标准权限行为，不是本次缺陷。
