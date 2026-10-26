# POC-06 负面测试、重启复测与交接

- 状态：**PASS**
- 日期：2026-10-26
- 环境：`poc-frappe` / `poc-mariadb` / `poc-redis-cache` / `poc-redis-queue`（Docker，端口仅绑 127.0.0.1）
- 站点：`erpnext-poc.localhost`，Windows 访问 http://erpnext-poc.localhost:18000
- 版本：ERPNext 16.52.1 / Frappe 16.53.0 / Python 3.14.9 / MariaDB 11.8 / Node 24.22.1

---

## 1. 交付结论

| 交付项 | 状态 | 说明 |
|---|---|---|
| 真实可用的中文 ERP 环境 | **PASS** | 容器化、卷持久化、开机自启（本次改造见第 4 节） |
| 简体中文界面与菜单 | **PASS** | POC-02/03；10 个中文工作台、角色门控 |
| 四类订单真实操作 | **PASS** | POC-04；生产/耗材/零部件/服务，均已完成到「已交付 + 已收款」 |
| 生产订单完整生命周期 | **PASS** | POC-05；BOM→计划→缺料采购→工单→报工→领料→完工→交付→开票→收款 |
| 负面测试（越界拦截） | **PASS（9/10 拦截，1 项已知缺口）** | 见第 3 节，缺口 GAP-06-01 已给处置建议 |
| 重启后数据不丢 | **PASS** | 17 项指标重启前后完全一致（第 4 节） |
| 交接文档与验收路径 | **PASS** | 本文档 + `docs/poc/UAT.md` |

---

## 2. 用户验收指引

### 2.1 打开系统
1. 浏览器（Chrome/Edge）访问 **http://erpnext-poc.localhost:18000**
2. 若域名不通，改用 http://127.0.0.1:18000
3. 账号：`Administrator`（管理员，全功能）；业务账号见下表
4. 密码：见本机 `D:\ERP\poc\CREDENTIALS.local.md`（**不进 Git**）

| 账号 | 角色 | 应看到的菜单重点 |
|---|---|---|
| `wangming@erpnext-poc.localhost` | 销售用户/销售经理 | 客户与销售、物流交付 |
| `chengong@erpnext-poc.localhost` | 采购用户/经理 | 采购管理、基础资料 |
| `zhanggong@erpnext-poc.localhost` | 仓库用户/经理 | 仓库管理、库存报表 |
| `ligong@erpnext-poc.localhost` | 制造用户 | 设计与生产（工单、任务单、物料移动） |
| `zhoukaiji@erpnext-poc.localhost` | 财务用户/经理 | 财务管理、经营报表 |

### 2.2 验收路线 A：四类订单（约 5 分钟）
左侧菜单 → **客户与销售 → 销售订单**，逐张打开（列表可按「业务类型」筛选）：

| 业务类型 | 订单号 | 金额 | 已做的动作 |
|---|---|---|---|
| 生产 | `SAL-ORD-2026-00001` | 17,600 | BOM 生产 → 工单 → 完工 → 交货 → 开票 → 收款 |
| 耗材 | `SAL-ORD-2026-00002` | 800 | 库存直接出库（50→40），无工单 |
| 零部件 | `SAL-ORD-2026-00003` | 750 | 库存直接出库（8→3），无工单 |
| 服务 | `SAL-ORD-2026-00004` | 800 | 无任何库存单据，直接开票收款 |

打开任意订单后，右下「关联」或顶部的 **交货单 / 销售发票** 按钮可跳到下游单据。

### 2.3 验收路线 B：生产完整闭环（约 10 分钟，重点）
左侧菜单 → **设计与生产**，按顺序点开：

| 步骤 | 菜单 | 单号 | 看点 |
|---|---|---|---|
| 1 | 物料清单 | `BOM-ASSY-X1-001` | 单台用 RACK 2 / SENSOR 1 / FASTENER 4，两道工序：装配 60 分钟、检验 30 分钟 |
| 2 | 生产计划 | `MFG-PP-2026-00001` | 计划 2 台，来源 `SAL-ORD-2026-00001`；物料需求里 RACK 缺 3、SENSOR 缺 2 |
| 3 | 采购管理 → 物料申请 | `MAT-MR-2026-00001` | 缺料转采购申请 |
| 4 | 采购管理 → 采购订单 | `PUR-ORD-2026-00001` | RACK 3×200 + SENSOR 2×300 = 1,200 |
| 5 | 采购管理 → 采购入库 | `MAT-PRE-2026-00002` | 入库 1,200，进「原材料仓」 |
| 6 | 生产工单 | `MFG-WO-2026-00001` | 2 台，已完成；源仓原材料仓 / 车间仓生产在制仓 / 收料仓产成品仓 |
| 7 | 生产任务单 | `PO-JOB00001` / `PO-JOB00002` | 装配（李工，60 分钟）/ 检验（张工，30 分钟），完成数量各 2 |
| 8 | 物料移动（工单发料） | `MAT-STE-2026-00003` | 三种料由原材料仓 → 生产在制仓，合计 1,440 |
| 9 | 物料移动（工单入库） | `MAT-STE-2026-00004` | 耗料 1,440 → 产成品 2 台 ×720 入产成品仓 |
| 10 | 物流交付 → 交货单 | `MAT-DN-2026-00004` | 2 台 ×8,800 = 17,600，产成品仓 2 → 0 |
| 11 | 财务管理 → 销售发票 | `ACC-SINV-2026-00002` | 17,600，状态 Paid |
| 12 | 财务管理 → 收款单 | `ACC-PAY-2026-00002` | 现金 17,600，应收账款 → 现金 |

**核对点**：BOM 标准成本 720 元/台 = 完工单实际单位成本 720 元/台；四张发票未收金额合计 0。

### 2.4 验收路线 C：库存与财务
- 仓库管理 → 报表 → **库存余额(收发存汇总表)**：选公司 + 日期区间，可见 5 类物料结存
- 财务管理 → **应收账款汇总**：未收 0
- 经营报表 → **销售订单分析**

---

## 3. 负面测试结果

脚本：`poc/scripts/poc06_negative.py`（事务内执行，失败即回滚，不留脏数据）

| 编号 | 越界操作 | 期望 | 实测 | 系统返回 |
|---|---|---|---|---|
| N1 | 库存 40 包却卖 100 包并交货 | 拦截 | **拦截** | `NegativeStockError`：缺 60 包（`allow_negative_stock=0` 生效） |
| N2-a | 销售用户读总账凭证 `GL Entry` | 拦截 | **拦截** | `has_permission('GL Entry')=False` |
| N2-b | 销售用户读收款单 `Payment Entry` | 拦截 | **拦截** | `has_permission('Payment Entry')=False` |
| N2-c | 销售用户创建收款单 | 拦截 | **拦截** | `PermissionError` |
| N2-d | 对照：销售用户读销售订单 | 放行 | **放行（符合预期）** | `has_permission=True`，证明权限按角色精细控制 |
| N2-e | 销售用户直接做总账凭证 | 拦截 | **拦截** | `PermissionError` |
| N3 | 不建工单直接完工入库 5 台 | 拦截 | **拦截** | `FinishedGoodError`：缺少成品行 |
| N4 | 给服务项 `INSTALL-SVC` 建工单 | 拦截 | **拦截** | `MandatoryError: bom_no`（服务无 BOM，无法排产） |
| N5 | 数量为 −1 的订单行 | 拦截 | **拦截** | `ValidationError`：合计金额必须 ≥ 0 |
| N6-a | 对已结清发票再收一次款 | 拦截 | **拦截** | `ValidationError`：Paid Amount 必填（系统不给可收金额 0） |
| N6-b | 取消已有收款的销售发票 | 拦截 | **放行 → 已知缺口 GAP-06-01** | v16 未阻止取消动作（探针已回滚，数据无损） |

**结论：10 项越界场景中 9 项被系统原样拦截，1 项（取消已收款发票）需靠权限与流程约束。**

### GAP-06-01 取消已收款发票未被阻止
- **现象**：对 `ACC-SINV-2026-00002`（已全额收款）执行取消，系统未报错。
- **风险**：账务链条断裂，收款单变孤儿，应收/现金勾稽失真。
- **处置建议（上线前实施）**：
  1. 在「角色权限管理」中把 `Sales Invoice` / `Payment Entry` / `Journal Entry` 的 **取消(cancel)** 与 **删除(delete)** 权限从 `Accounts User` 收回，只留 `Accounts Manager`；
  2. SOP 明确：已收款的发票不得取消，改走红冲（Credit Note）或退货流程；
  3. 若客户要求系统级硬约束，可在 `cn_mfg_poc` 里加 `Sales Invoice.before_cancel` 校验钩子（约 10 行代码）。
- **本次处理**：POC 阶段仅记录，不做权限改造（避免影响演示账号操作）。

---

## 4. 重启复测（持久化 + 自启动）

### 4.1 测试步骤
1. 采集 17 项指标快照（`poc/scripts`... 见 `poc/share/poc06_baseline.py`）
2. `docker compose stop` → 全部 4 个容器停止 → `docker compose start`
3. 复核快照；再 `docker compose up -d`（重建 frappe 容器验证卷持久化）并复核

### 4.2 结果：17 项指标重启前后**完全一致**

| 指标 | 重启前 | 重启后 |
|---|---|---|
| 销售订单 / 交货单 / 销售发票 / 收款单 | 4 / 4 / 5 / 5 | 4 / 4 / 5 / 5 |
| 生产计划 / 生产工单 / 生产任务单 / BOM | 1 / 1 / 2 / 1 | 1 / 1 / 2 / 1 |
| 库存移动 / 总账凭证 / 库存台账 | 4 / 52 / 49 | 4 / 52 / 49 |
| 用户 / 工作台 / 数字卡 | 9 / 33 / 61 | 9 / 33 / 61 |
| 应收余额 / 库存总值 / 销售额 | 0 / 2,380 / 19,950 | 0 / 2,380 / 19,950 |

### 4.3 发现并修复：重启后 Web 服务不自启
- **问题**：compose 中 `poc-frappe` 的 `command: sleep infinity`，容器重启后 bench 的 web/socketio/worker/schedule 不会自己起来，用户访问 18000 直接 502/连接失败。
- **修复**（`poc/frappe_docker/docker-compose.yml`，已入库）：
  - `command: bash -lc "bash /workspace/scripts/poc-start.sh; sleep infinity"`
  - 四个服务全部加 `restart: unless-stopped`
  - `frappe` 增加 `depends_on: mariadb(healthy) / redis-cache / redis-queue`
- **验证**：`docker compose up -d` 重建容器后不执行任何手工命令，25 秒内 http://erpnext-poc.localhost:18000/login 返回 **HTTP 200**，`/workspace/run/*.pid` 四个进程自动就绪。

---

## 5. 数据现状快照（2026-10-26）

**主数据**：物料 7、客户 1（苏州华新装备有限公司）、供应商 1（昆山精工零部件有限公司）、仓库 9、工位 2（装配工位/检验工位）、工序 3、员工 3（李工/张工/刘工）

**库存（有结存）**

| 物料 | 仓库 | 数量 | 单位 | 金额 |
|---|---|---|---|---|
| FILTER-KIT 过滤耗材包 | 贸易品仓 | 40 | 包 | 2,000 |
| FLANGE-ASSY 替换法兰组件 | 贸易品仓 | 3 | 件 | 360 |
| FASTENER 紧固件 | 原材料仓 | 4 | 件 | 20 |
| **合计** | | | | **2,380** |

**财务**：销售额 19,950（4 张有效销售发票：17,600 + 800 + 750 + 800），未收 0，现金账户已入账 19,950。

---

## 6. 与 JSH ERP（管伊佳）对比与选型建议

> JSH 信息依据官网/公开资料（检索日期 2026-10-26）：开源版 Apache-2.0，覆盖零售、采购、销售、仓库、财务、报表；**生产管理（BOM、生产任务）、总账、多级审核、手机端为付费插件**；技术栈 SpringBoot 2 + MyBatis + Vue + Ant-Design-Vue，MySQL 8 + Redis。
> ERPNext 信息为本 POC 实测。

| 维度 | ERPNext 16（本次 POC 实测） | JSH ERP（管伊佳） |
|---|---|---|
| 授权 | GPLv3（社区版免费，无功能插件墙） | Apache-2.0，开源版免费但生产/总账/审核等为付费插件 |
| 生产制造 | **原生完整**：BOM（多阶）、生产计划、MRP 缺料、工单、工序/工位、生产任务单（Job Card）、领料/完工、副产物 | 开源版无生产；生产为付费插件（BOM + 生产任务） |
| 进销存 | 原生（采购/销售/库存/多仓/批次序列号/多计量单位） | 强项，贴合国内商贸习惯 |
| 财务 | 原生总账、应收应付、发票收款、多币种、成本核算 | 开源版有收付款/往来账；总账为付费插件 |
| 中文本土化 | 翻译完整但部分术语偏港台（本次已修 8 处），无中国会计准则科目模板 | 原生国内习惯（含中国会计科目、单据格式） |
| 操作手感 | 表单字段多、概念偏国际化，需培训 | 单据更贴近国内老板/业务员习惯，上手快 |
| 权限 | 角色 + DocPerm + 工作台门控（本次已做 10 个工作台 + 36 模块屏蔽） | 精确到菜单/按钮，配置更直白 |
| 技术栈与二开 | Python/Frappe，扩展用 DocType/Script/自定义 App | Java/SpringBoot，Java 团队更易接手 |
| 部署 | Docker，官方镜像；本次已做开机自启 | Docker/安装包，需 JDK、MySQL8、Redis、Nginx |
| 适用结论 | **有真实生产制造诉求（BOM/工艺/工单/成本）时明显占优** | 纯贸易/零售进销存且预算敏感时更轻快 |

**建议**：
1. 若客户以「轻制造 + 交付安装」为主（本次演示的四类订单场景），选 **ERPNext**：生产链路原生免费、可长期演进，不必为工单/总账买插件。
2. 若客户 90% 业务是贸易零售、只偶尔组装，且团队是 Java 栈，**JSH** 落地成本更低。
3. 两条路的共同前提是先做**主数据治理**（物料编码、BOM、仓库、科目），本次 POC 已把制造业必需的主数据形态跑通，可直接复用为实施清单。

---

## 7. 遗留项总表

| 编号 | 问题 | 影响 | 处置 |
|---|---|---|---|
| GAP-05-02 | 工单工序成本为 0（工位小时费率未设） | 成品成本只含材料，不含人工/制费 | 设 `Workstation.hour_rate`（建议 装配 100 元/h、检验 80 元/h）→ 新建 BOM 版本 → 新建工单 |
| GAP-05-03 | 生产任务单员工显示 `HR-EMP-00001` 而非「李工」 | 体验 | 员工命名改用姓名，或列表/打印改用 `employee_name` |
| GAP-06-01 | 已收款发票可被取消，未系统级阻止 | 账务风险 | 收紧 cancel 权限 + SOP + 可选钩子（见第 3 节） |
| OBS-06-01 | 工作台自定义「数字卡」区块在前端不渲染 | 观感 | 已回退为原生文字卡片；如需 KPI 磁贴，改用标准 workspace 的 `number_card` 参考实现或做自定义页面 |
| UP-05-01 | 上游缺陷：Job Card 自动排程崩溃（`get_time(datetime)`） | 工单提交报错 | `Manufacturing Settings.disable_capacity_planning=1` 规避；不影响报工与库存 |
| — | 服务类订单状态停留「To Deliver」 | 观感 | 服务项无实物交付，属 ERPNext 正常行为；可用「关闭订单」收口，或流程上只做到开票收款 |

---

## 8. 运维命令

```powershell
# Windows（推荐）
D:\ERP\erpnext\poc\scripts\poc.ps1 start     # 起容器 + bench 服务（容器已自启，此命令幂等兜底）
D:\ERP\erpnext\poc\scripts\poc.ps1 stop      # 停 bench + 停容器（数据保留）
D:\ERP\erpnext\poc\scripts\poc.ps1 status    # 容器状态 + 站点可达性
D:\ERP\erpnext\poc\scripts\poc.ps1 backup    # 备份到 D:\ERP\poc\backup
```

```bash
# 容器内等价
docker exec poc-frappe bash /workspace/scripts/poc-start.sh
docker exec poc-frappe bash /workspace/scripts/poc-stop.sh
cd D:\ERP\poc\frappe_docker && docker compose ps
```

**备份**：`bench --site erpnext-poc.localhost backup --with-files`，产物在 `sites/erpnext-poc.localhost/private/backups/`。
**日志**：`/workspace/logs/{web,socketio,worker,schedule}.log`。

---

## 9. 文件索引

| 路径 | 说明 |
|---|---|
| `docs/poc/TASKS.md` | 任务队列与 PASS 记录（含提交号） |
| `docs/poc/UAT.md` | 用户验收记录（验收点 → 实测 → 证据） |
| `docs/poc/evidence/POC-00~06-*.md` | 各阶段证据 |
| `poc/scripts/poc04_*.py` | 四类订单：主数据 + 下单 + 交货 |
| `poc/scripts/poc05_*.py` | 生产闭环：prep / stage1~4 / verify / costfix / paymode |
| `poc/scripts/poc06_*.py` | 负面测试 / 财务补齐 / 工作台快捷入口与数字卡 |
| `poc/frappe_docker/docker-compose.yml` | 容器编排（含自启动与重启策略） |
| `poc/apps/cn_mfg_poc/` | 自定义 App（中文工作台、角色门控、fixtures） |
| `D:\ERP\poc\share\screenshots\` | 全部截图（不在 Git，本地留存） |
