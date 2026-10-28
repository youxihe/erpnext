# BUILD-00 — 现有 POC 和模块快速核对

日期：2026-10-29 ｜ 执行：Workbuddy Agent ｜ 分支：`product/erpnext-wecom-ai-v1-20261029`
结论：**PASS**。环境完好可直接进入 BUILD-10，无需重装或重造数。

## 1. Git 与分支安全同步

- `D:\ERP\erpnext` 工作区干净（无未提交变更），旧 POC 分支 `poc/erpnext-cn-manufacturing-20261026` 保留在 `69c4507b`。
- HTTPS 走本机代理返回 502，改用 SSH `git@github.com:youxihe/erpnext.git` 成功 fetch（`origin` fetch URL 已是 HTTPS，本次用显式 SSH URL 拉取，不影响远端配置）。
- 本地新建跟踪分支并切换：`product/erpnext-wecom-ai-v1-20261029` = 远端 `c5b339be`（docs(product): define shared ERP architecture…），其父提交即 POC HEAD `69c4507b`，历史连续、无回退。

## 2. 运行环境实测

| 项 | 实测值 |
|---|---|
| ERPNext / Frappe / Python | 16.52.1 / 16.53.0 / 3.14.9（v16 稳定配对，未漂移到 develop） |
| 已装 App | frappe、erpnext、**cn_mfg_poc**（源码在容器与仓库 `poc/apps/cn_mfg_poc`） |
| Site | `erpnext-poc.localhost`（隔离，唯一站点），公司：昆山启程智能设备有限公司（QC，CNY，China） |
| 容器 | poc-frappe / poc-mariadb(healthy) / poc-redis-cache / poc-redis-queue，Up 2 days，compose 已带 `restart: unless-stopped` 与启动即拉起 bench |
| PC 入口 | http://erpnext-poc.localhost:18000 → 登录页 HTTP 200；`/app/工作台`、`/app/客户与销售`、`/app/sales-order` 均正常渲染（截图 build-00-*.png） |
| REST | `/api/method/frappe.auth.get_logged_user`、`/api/resource/Sales Order` 携带会话 Cookie 从宿主机访问均正常返回 JSON → H5/Bot 共用 API 的传输层可直接用 |
| 数据卷 | 未清理任何 volume；单据存量与 POC-06 收尾一致 |

## 3. 四类订单与生产链路抽样（真实数据完好）

| 单据 | 实测 |
|---|---|
| SAL-ORD-2026-00001 生产 | 17,600 / 交付 100% / 开票 100% / Completed |
| SAL-ORD-2026-00002 耗材 | 800 / Completed（`business_type` 字段在位） |
| SAL-ORD-2026-00003 零部件 | 750 / Completed |
| SAL-ORD-2026-00004 服务 | 800 / To Deliver（服务无实物交付，符合预期） |
| 生产链 | BOM-ASSY-X1-001 → MFG-PP-2026-00001(Completed) → MFG-WO-2026-00001(2/2) → PO-JOB00001 装配 / PO-JOB00002 检验（均 Completed）→ MAT-STE-00003 领料 / 00004 完工（提交态） |
| 库存 | FASTENER 4 @原材料仓、FILTER-KIT 40 @贸易品仓、FLANGE-ASSY 3 @贸易品仓 |

用户与角色（7 个业务账号齐全）：王明=销售、陈工=采购、李工=制造员工、刘工=制造经理、张工=仓储、周会计=财务、赵经理=管理；Employee 表已把李工/张工/刘工 `user_id` 绑到对应 ERP User → 「我的车间任务」的归属链路已具备。Job Card 员工归属在子表 `Job Card Time Log.employee`（HR-EMP-00001 等）。

## 4. 八大模块一张表

| 模块 | 结论 | 说明（中文菜单 / 源码或单据位置） |
|---|---|---|
| 客户/销售 | **可直接复用** | 工作台「客户与销售」13 链接；Sales Order/Customer/Contact/Address 原生；`business_type` 自定义字段在位。缺：客户报备入口（原生 Lead=销售线索已在菜单，可直接充当报备单） |
| 设计/生产 | **可直接复用**（缺"我的任务"入口） | 「设计与生产」14 链接；BOM/生产计划/工单/Job Card 全链路有真实单据。缺：按登录员工过滤的任务视图与完成反馈入口 |
| 采购 | **可直接复用** | 「采购管理」12 链接；MR→PO→PR 已有真实单据（MAT-MR-2026-00001 → PUR-ORD-2026-00001 → MAT-PRE-2026-00002） |
| 仓库 | **可直接复用** | 「仓库管理」13 链接；4 个业务仓+库存台账/SLE 在位 |
| 物流交付 | **可直接复用** | 「物流交付」3 链接；交货单 4 张真实单据 |
| 财务 | **可直接复用** | 「财务管理」11 链接；发票 5 / 收款单 5 / GL 52 行，中文支付方式已建 |
| 经营 | **可直接复用** | 「经营报表」13 链接（原生 Report 视图，角色门控 6 角色） |
| 系统权限 | **可直接复用** | 「系统设置」+36 模块屏蔽+7 用户角色门控（POC-03 实测 10/10） |

**确实缺的最小功能（→ BUILD-10/20）**：
1. 客户报备的业务闭环（报备→查重→确认→转客户）——用原生 Lead 承载，补「报备」中文入口与状态流；
2. 「我的车间任务」角色入口（Job Card 按登录员工 `Employee.user_id` 过滤）；
3. 三入口共用受控 API（Frappe 原生 REST + cn_mfg_poc 白名单接口）。

## 5. 可复用资产盘点

- **cn_mfg_poc**（`poc/apps/cn_mfg_poc`）：10 个中文工作台 fixtures、中文翻译补丁、导航 patch。**无任何 API/DocType/whitelisted 方法**（`tabDocType where module='CN MFG POC'` 为空）→ BUILD-20 起在此 App 内加 `api/` 模块与 DocType，不新建 App。
- **旧 ai-erp（JSH）**：`docs/poc/03-erp-gateway.md` 的网关模式可直接移植思想：草稿表→确认→原生单据、幂等键返回原单号、行锁防超卖、按钮级权限校验、`GW-{类型}-{草稿主键}` 单号。这些是 BUILD-20/60 的合同蓝本（Frappe 侧改用 DocType 存草稿）。
- **F:\aierp-openclaw**：目录仅 bin/node/node_modules/state/package.json——OpenClaw 运行时壳与 state；**不改动**。BUILD-50 调研其通道配置方式后接入。
- **H5/Bot 共用 API 面（BUILD-20 输入）**：客户报备/查客户、我的订单/交付、我的 Job Card/更新、授权库存查询、采购入库草稿/确认。全部走 `/api/resource` + `/api/method/cn_mfg_poc.api.*`，身份走 ERP User（企微绑定在 BUILD-30 落地）。

## 6. 已知边界（不阻断，记 BACKLOG）

- 服务类订单 To Deliver 展示、发票取消保护（GAP-06-01）、工序人工成本（GAP-05-02）等继续按 BACKLOG.md 暂缓。
- Job Card 产能排程上游缺陷仍用 `disable_capacity_planning=1` 规避（不影响任务进度反馈）。

## 7. 复测方式

```bash
# 环境：docker ps（4 容器 Up）+ curl 登录页 200
MSYS_NO_PATHCONV=1 docker exec -w /workspace/development/frappe-bench poc-frappe \
  /workspace/development/frappe-bench/env/bin/python /tmp/build00_probe.py   # 只读探针
# 截图：/app/工作台、/app/客户与销售、/app/sales-order
```
探针脚本入库：`product/scripts/build00_probe.py`；快照：`docs/product/evidence/build00.json`。
