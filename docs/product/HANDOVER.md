# ERPNext × 企业微信 H5 × AI 机器人 — 交接文档（公开版）

> 更新日期：2026-11-19 · 分支 `product/erpnext-wecom-ai-v1-20261029` · 最新提交 `d4e19107`
>
> **凭据说明**：本仓库是 public fork，因此本文**不含任何明文密码**。
> 含服务器 SSH、数据库、Administrator 与 9 个业务账号密码的完整版存放在私有仓库
> `youxihe/ai-erpnext`（文件名 `HANDOVER-FULL.md`）。需要登录时向项目负责人索取。

---

## 0. 速览

| 项 | 值 |
|---|---|
| 线上站点 | `https://d.urlxl.cn` |
| 入口 | `/cn_portal` 统一中文导航（推荐）、`/desk` 原生 Desk、`/wecom_h5` 企微 H5 |
| 健康检查 | `curl -s https://d.urlxl.cn/api/method/ping` → `{"message":"pong"}` |
| 代码主体 | `poc/apps/cn_mfg_poc/cn_mfg_poc/`（自有 Frappe App） |
| 线上应用根 | `/app/erpnext-v1/` |
| 当前状态 | 三入口核心流程线上可用；真实企微真人 UAT 仍 `REAL_WECOM_BLOCKED` |
| 最近修复 | DESK-HOME 遗留路由兼容、门户菜单权限过滤、Desk 首页 `Page.read`、门户退出登录 |

---

## 1. 最原始的用户需求

### 1.1 立项目标（2026-10-29）

客户能同时使用：
1. **中文 ERPNext PC** 完成主要销售/设计/采购/仓库/生产/财务/管理流程；
2. **企业微信自建 H5** 完成最常用移动操作；
3. **企业微信 AI ERP 机器人**通过自然语言/Excel 对同一 ERPNext 数据查询、草稿、确认与写入。

验收核心不是把 ERPNext 细节全打磨完，而是 **三入口 + 同一 ERP 数据 + 核心业务可操作**。

### 1.2 北极星与边界

> 一个客户同时体验中文 ERP PC、企微 H5、企微 AI 机器人，三个入口操作同一个 ERPNext Site 的真实业务数据、业务权限和单据。

- 先补大模块、打通三入口；不纠缠发票取消、工序人工成本、复杂审批、报表美化。
- 复用 Frappe 原生 DocType / REST / 自有 App，不自研库存或总账。
- 所有业务数据以 ERPNext DocType 为唯一权威，PC/H5/Bot 不存第二份真相。
- 缺企微外部授权时标 `REAL_WECOM_BLOCKED`，不把 Mock 当真人验收。

### 1.3 用户追加与后续确认

- **2026-11-07**：确认 `/cn_portal` 中文导航可用，要求配置四类订单（生产/耗材/零部件/服务）与 BOM 拆分。四类订单已落地；**BOM 拆分口径用户要求先等确认**，见 `BACKLOG.md` 的 `BOM-01`。
- **2026-11-08**：确认「重单据、轻生产」——采购/仓库/销售/财务用正式单据；生产只维护固定九阶段任务的负责人/目标日/状态/备注，不要求 Job Card 报工；Work Order / Stock Entry 不能省，任务完成不能自动入库；整机一次交付。详见 `decisions/LIGHT_MANUFACTURING_20261108.md`。
- **后续反馈**：门户缺退出入口、liugong 门户菜单能看但原生页 403、重新登录仍提示没权限、用户给出 `getpage(name=home)` 404 的 curl——均已修复，见 `evidence/` 下 PORTAL-LOGOUT / PORTAL-PERM-101 / PAGE-PERM-102 与提交 `d4e19107`。

### 1.4 尚未完成

`UAT-98` 独立干净验收 Site（TODO）、`UAT-99` 用户本人分角色人工验收（WAITING_FOR_USER）、真实企微 UAT、`BOM-01`、`DATA_SCOPE_GAP`（Desk 列表行级隔离）。

---

## 2. 代码地图

```bash
本地：D:/ERP/erpnext
分支：product/erpnext-wecom-ai-v1-20261029
remote：ghssh = git@github.com:youxihe/erpnext.git（HTTPS 被代理拦，用 SSH）
禁止合并/切换到上游 develop（ERPNext v17 开发分支）。
```

```
poc/apps/cn_mfg_poc/cn_mfg_poc/
├── api.py                    三入口共用 API：orders.summary / production.tasks.mine
│                             / production.tasks.update / materials.shortage
│                             / materials.trace / purchase.options / purchase.trace
│                             / my_orders / stock_balances / my_jobs
├── crm.py                    Lead→Customer→Sales Order（convert_lead / create_customer 等）
├── role_setup.py             7 个中文岗位档案与账号同步（PROFILES / sync_identities）
├── production.py             九阶段 Project/Task 生成、分派、预警
├── order_execution.py        订单执行概览、缺料计算
├── procurement_trace.py      多订单物料来源与采购履约追溯（只读）
├── hooks.py                  doc_events / app_include_js / patches
├── patches/v0_0_*/           幂等数据补丁
├── www/
│   ├── cn_portal.py|html     统一中文导航门户（菜单按真实权限过滤 + 403 友好兜底）
│   ├── customer_center / customer_detail / lead_detail
│   ├── order_execution / procurement_trace / role_profiles / wecom_h5
└── public/js/
    ├── desk_home_compat.js   v16 遗留 /desk/home → /desk 重定向
    ├── lead_crm.js / customer_crm.js  Desk 内「转客户 / 创建销售订单」按钮
    └── cn_mfg_poc.js
```

其它：
- 企微机器人适配器：`product/adapter/erpnext-bot-tools`。
- 任务队列与证据：`docs/product/QUEUE.md`、`tasks/`、`evidence/`、`decisions/`、`BACKLOG.md`。
- 部署脚本与本地私有记录：`D:/ERP/poc/deploy/`（不在本仓库内）。

近期提交：

| SHA | 说明 |
|---|---|
| `d4e19107` | DESK-HOME 兼容：遗留 `/desk/home` 重定向 `/desk`（已部署线上） |
| `aff0b4f3` | PAGE-PERM-102：给 Desk User 补 `Page.read` |
| `a1e7ab17` | PORTAL-PERM-101 门户菜单按真实权限过滤 |
| `94e898fa` | 门户与岗位页补真实退出登录 |
| `902bcbe3` | CRM-100 客户报备→正式客户→销售订单主线 |

---

## 3. 线上环境（不含凭据）

### 3.1 架构

```
Internet --HTTPS--> nginx (80/443)
                      |-- /socket.io/ --> 127.0.0.1:19000  [node socketio.js]
                      |-- /           --> 127.0.0.1:8800   [gunicorn, wsgi:application]
                                              +--> 云 MySQL 8.0.30-txsql  / brj_erp
                                              +--> 本机隔离 Redis 7  127.0.0.1:6380
                                                     db1 cache / db2 queue / db3 socketio
```

依用户决定不装 Docker（服务器内网与云数据库同段，装 Docker 有断网风险），沿用 nginx + 本机进程形态。

### 3.2 关键路径与服务

| 项 | 值 |
|---|---|
| 应用根 | `/app/erpnext-v1/`（apps / sites / env / logs） |
| 自有 App | `/app/erpnext-v1/apps/cn_mfg_poc/` |
| nginx | `/etc/nginx/conf.d/d.urlxl.cn.conf` |
| 证书 | `/data/cert/d.urlxl.cn/`（**2027-02-05 到期**） |
| 备份 | `/app/backup/<任务名>/<时间戳>/` |
| systemd | `erpnext-v1-{redis,web,socketio,worker,schedule}`，全部 enabled + active |
| 日志 | `/app/erpnext-v1/logs/`（`web-error.log`、`worker.log` 等） |
| 运行时 | Python 3.14.7 / Frappe 16.53.0 / ERPNext 16.52.1 / gunicorn / click 8.1.8 |

### 3.3 账号清单（密码见私有仓库）

登录名后缀仍是 `@erpnext-poc.localhost`（从本地 POC 迁移，未改名以免破坏关联数据）；`Administrator` 首字母大写。

| 显示名 | 登录名前缀 | 岗位档案 |
|---|---|---|
| 管理员 | `Administrator` | — |
| 经营管理-A-赵经理 | `zhaojingli` | 经营管理 |
| 销售-A-王明 | `wangming` | 销售业务 |
| 设计生产-A-刘工 | `liugong` | 设计生产 |
| 采购-A-陈工 | `chengong` | 采购业务 |
| 仓库-A-张工 | `zhanggong` | 仓库管理 |
| 车间-A-李工 | `ligong` | 车间执行 |
| 财务-A-周会计 | `zhoukaiji` | 财务业务 |
| 销售-B-对照 | `xiaoshou-b` | 销售业务 |
| 车间-B-对照 | `chejian-b` | 车间执行 |

自 2026-11-09 起每个账号独立随机密码。岗位档案定义在 `cn_mfg_poc/role_setup.py`；原生英文 Role 不要改名/删除，岗位调整只改 `PROFILES` 再跑 `sync_identities()`（幂等）。

---

## 4. 部署与发布

完整逐步记录见本地私有文件 `D:/ERP/poc/deploy/DEPLOY.local.md`。这里给出日常增量发布的正确姿势。

### 4.1 发布前备份

线上 `/app/backup/<任务名>/<YYYYMMDD-HHMMSS>/` 至少包含数据库与应用目录。数据库导出必须带连接参数，否则会静默产出 0 字节：

```bash
MYSQL_PWD='<见私有仓库>' mysqldump -h <内网地址> -u <账号> brj_erp > brj_erp.sql
```

### 4.2 上传与生效

```bash
# ssh_tool.py put 的远程路径必须是【相对路径】(sftp cwd=家目录)，绝对路径会 ENOENT
# Git Bash 下必须加 MSYS_NO_PATHCONV=1，否则 /tmp/x 被转成 Windows 路径
MSYS_NO_PATHCONV=1 python D:/ERP/poc/deploy/ssh_tool.py put <local> <relative_remote>

# 清缓存必须在 sites 目录执行，且 clear-cache 不带 --site
cd /app/erpnext-v1/sites && bench clear-cache
sudo systemctl restart erpnext-v1-web erpnext-v1-worker erpnext-v1-schedule
curl -s https://d.urlxl.cn/api/method/ping
```

- 纯模板/JS 改动**不需要 migrate**。
- 有 DocType/Custom Field 变更才考虑 migrate；**线上不要跑 `bench migrate`**（表名大小写补丁不覆盖 schema 层），先在测试环境验证。

### 4.3 升级 Frappe 后的补丁重放（顺序不能反）

线上 MySQL 是 `8.0.30-txsql` 且 `lower_case_table_names=1`，Frappe 源码有 3 个文件被打了兼容补丁（`mysqlclient.py`、`database.py`、`reportview.py`，各有 `.orig` 原始备份）。升级覆盖后必须按顺序重放：

```bash
./patch_lower_case_tables2.sh    # 先：表名大小写
./patch_mysql8_compat.sh         # 后：MySQL 8 超时语法（幂等）
redis-cli -h 127.0.0.1 -p 6380 -n 1 FLUSHDB
sudo systemctl restart erpnext-v1-web erpnext-v1-worker erpnext-v1-schedule
```

`.orig` 不含任何补丁，单独用它回滚会同时丢掉两个补丁。

### 4.4 回滚

```bash
sudo rm /etc/nginx/conf.d/d.urlxl.cn.conf && sudo nginx -t && sudo systemctl reload nginx
sudo systemctl stop erpnext-v1-{web,socketio,worker,schedule,redis}
# 数据/代码用 /app/backup/<任务>/<时间戳>/ 恢复
```

---

## 5. 验证基线

| 验收 | 结果 |
|---|---|
| 首次上线全量验收 | 29/29 PASS（`deploy/acceptance_online.sh`） |
| `get_count` 专项 | 18/18 PASS |
| UAT-97R 角色账号 | 线上 118/118、A/B 隔离 14/14 |
| CRM-100 | 线上 38/38 + 浏览器 16/16 |
| PORTAL-PERM-101 | 线上回归 100/100；liugong 菜单 42→24 项（0 不可达） |
| PAGE-PERM-102 | 9 账号无 403，重启后权限仍在 |
| DESK-HOME | 9 账号浏览器实测：`/desk/home` 平滑跳 `/desk`，无报错 |
| UX-96 / FLOW-97 | 38/38 + 浏览器 29/29；后端 30/30 + 浏览器 20/20 |

浏览器验证用本机 Chrome（`C:\Program Files\Google\Chrome\Application\chrome.exe`）+ Playwright `channel="chrome"`；登录选择器 `#login_email`、`#login_password`，按钮文本「继续」。

线上数据基线：SLE 84、GL 94、企微绑定 4 条；验收要求库存与单据数零变动。

---

## 6. 已知问题

| 项 | 状态 |
|---|---|
| 真实企微 UAT | `REAL_WECOM_BLOCKED`：缺 CorpID、AgentID+Secret、可信回调域名、通讯录与机器人权限 |
| `DATA_SCOPE_GAP` | Desk 客户/销售订单列表无行级隔离，是否加 User Permission / if_owner 待用户确认 |
| `BOM-01` | 复杂 BOM 拆分/替代料口径，用户要求先等确认 |
| `UAT-98` / `UAT-99` | 干净验收 Site TODO；用户本人人工验收 WAITING_FOR_USER |
| 应付账龄 403 | chengong 点标准报表因 SQL 引用 Journal Entry 运行时 403，`guardIframe()` 已友好覆盖 |
| 证书 | 2027-02-05 到期，需续期 |
| 登录名后缀 | `@erpnext-poc.localhost`，改后缀需迁移关联数据 |
| socket.io | 监听 `0.0.0.0:19000`，建议限制安全组 |
| SEC-01 | 管理员公网访问收紧 / 独立口令，未完成 |

---

## 7. 三入口体验清单（历史保留，供人工测试）

### 7.1 PC

`/cn_portal` 顶部一级模块 + 左侧二级菜单，按当前账号角色过滤，内容区打开原生页面。未登录跳 `/login` 并回跳。重点看：客户与销售 → 客户报备/客户；设计与生产 → 生产任务单/我的任务；库存 → 库存余额；采购 → 采购入库单。

### 7.2 企微 H5

`/wecom_h5`。Mock 模式直接选成员免登；四个入口：客户报备 / 我的订单 / 我的任务 / 库存查询。真实模式走企微 OAuth（仍 BLOCKED）。

### 7.3 AI 机器人

OpenClaw 插件 `product/adapter/erpnext-bot-tools`。只读工具：`erp_whoami` / `erp_stock_query` / `erp_my_orders` / `erp_order_progress` / `erp_my_jobs` / `erp_mgmt_summary`；写草稿工具：`erp_excel_template` / `erp_purchase_excel_preview` / `erp_report_customer_preview` / `erp_my_drafts`。确认方式：**本人私聊回复口令**「确认采购 PID-xxxxx」「确认报备 BD-xxxxx」；群聊口令不生效，模型不能自行调用确认动作。

测试对话示例：
```
我是谁
SENSOR 还有多少库存
SAL-ORD-2026-00005 到哪一步了
我今天有什么任务
给我一张采购入库 Excel 模板
（发回填好的 Excel）帮我入库
确认采购 PID-00029
帮我报备客户 苏州新元精密机械有限公司
确认报备 BD-00028
```

### 7.4 样本单据

| 类型 | 单号 |
|---|---|
| 销售订单 | `SAL-ORD-2026-00001` ~ `00013`（CRM-100 样本为 `00013`） |
| 客户报备 | `CRM-LEAD-2026-00001` ~ `00011`（`00011` → CRM100 验收客户 → `SAL-ORD-2026-00013`） |
| 生产工单 | `MFG-WO-2026-00001` ~ `00003` |
| 采购入库 | `MAT-PRE-2026-00001` ~ `00016` |
| 项目 / 任务 | `PROJ-0001` ~ `0004` / `TASK-2026-00010` ~ `00045` |

Excel 模板：`docs/product/samples/采购入库模板.xlsx`，列名：物料编码 / 物料名称 / 数量 / 单位 / 单价 / 供应商 / 仓库。

---

## 8. 接手规则（红线）

1. 不重置数据库、不清理未知 Docker 卷、不删 `d.urlxl.cn` 的交易/库存/GL/Project/Task。
2. 不把公网仓库当凭据存放处；不在聊天里复述密码。
3. 不用 Administrator 共享 Token 代替企微员工权限。
4. 不给原生英文 Role 改名/删除；岗位调整只改 `role_setup.PROFILES` 再 `sync_identities()`。
5. 不用 `owner`/`modified_by` 猜首次报备人；`custom_first_reporter` 只在 `set_first_reporter()` 写。
6. 客户转化走 `crm.convert_lead`（复用原生 `make_customer` + `update_lead_status`），同名客户只返回已有客户、不改归属。
7. Project Task 不能自动触发库存过账；完工入库只由授权人员用原生 Work Order / Stock Entry。
8. 不向上游 `develop` 或默认分支合并；只推本产品分支。
9. 不把 HTTP 200 / Mock 成功写成真人验收 PASS。

**接手后建议**：① 确认私有仓库 `youxihe/ai-erpnext` 中的完整凭据可读；② 轮换 Administrator 与 SSH 密码；③ `ping` 自检；④ 用 liugong 登录 `/cn_portal` 与 `/desk` 确认最近三个权限修复；⑤ 等用户定 UAT-98 / 真实企微 / BOM-01 优先级。

---

## 9. 文档索引

- 总览与规则：`README.md`、`AGENTS.md`、`ARCHITECTURE.md`、`ACCEPTANCE.md`
- 任务队列与待办：`QUEUE.md`、`BACKLOG.md`
- 决策：`decisions/LIGHT_MANUFACTURING_20261108.md`
- 证据：`evidence/BUILD-00..94.md`、`RELEASE-95.md`、`UX-96A/B.md`、`FLOW-97A/B.md`、`UAT-97R.md`、`CRM-100.md`、`PORTAL-LOGOUT.md`、`PORTAL-PERM-101.md`、`PAGE-PERM-102.md`
- 人工验收：`UAT_MANUAL_V1.md`、`tasks/UAT-98.md`
- 完整凭据版：**私有仓库 `youxihe/ai-erpnext` → `HANDOVER-FULL.md`**
