# POC 用户验收记录

**状态：进行中。** POC-00～POC-05 已 PASS；负面测试/交付（POC-06）待补。以下验收点均有真实单据或截图支撑。

## 环境
- URL：http://erpnext-poc.localhost:18000 （已可访问，Windows 浏览器直连，系统代理已关闭）
- Windows 入口：hosts 已加 `127.0.0.1 erpnext-poc.localhost`；SocketIO 端口 19000
- Git POC branch/head：poc/erpnext-cn-manufacturing-20261026 / ea9d3ceb43c76039c39354f704a63b860d1423d9
- ERPNext / Frappe / Python 版本：16.52.1 / 16.53.0(version-16) / 3.14.9（bench 5.31.1, MariaDB 11.8, Node 24.22.1）
- Docker/Bench 目录、site、端口、持久化 volume：
  - 编排：`D:\ERP\poc\frappe_docker\docker-compose.yml`
  - 容器：poc-frappe / poc-mariadb / poc-redis-cache / poc-redis-queue
  - site：`/workspace/development/frappe-bench/sites/erpnext-poc.localhost`（Docker 卷 `poc-workspace`）
  - 数据库卷：`poc-mariadb-data`；端口仅绑定 127.0.0.1（web 18000-18005，socketio 19000-19005）
- 启动/停止/备份/恢复命令：见 docs/poc/evidence/POC-01-install.md 与 `poc/scripts/poc.ps1`
- 账号：Administrator（**密码本机安全交付，见 D:\ERP\poc\CREDENTIALS.local.md，不进 Git**）

## 四类真实单据
| 类型 | 销售订单 No. | BOM | 工单 No. | 任务 No. | 采购/库存 No. | 交付 No. | 财务 No. | 验收结果 |
|---|---|---|---|---|---|---|---|---|
| 生产类 | SAL-ORD-2026-00001（设备装配 X1 ×2） | BOM-ASSY-X1-001（单台 720） | MFG-WO-2026-00001（2 台，已完成） | PO-JOB00001 装配 / PO-JOB00002 检验 | MR-00001 → PO-00001 → PRE-00002；领料 STE-00003 / 完工 STE-00004 | MAT-DN-2026-00004（交 2 台，成品仓 2→0） | SINV-2026-00002 → PAY-2026-00002（17600 已收，应收 0） | **PASS**（POC-05） |
| 耗材类 | SAL-ORD-2026-00002（过滤耗材包 ×10） | 不适用 | 无（0） | 不适用 | MAT-RECO-2026-00001 初始化 50 | MAT-DN-2026-00001（交 10，库存 50→40） | 待 POC-06 | **PASS**（POC-04） |
| 零部件类 | SAL-ORD-2026-00003（替换法兰组件 ×5） | 不适用 | 无（0） | 不适用 | MAT-RECO-2026-00002 初始化 8 | MAT-DN-2026-00002（交 5，库存 8→3） | 待 POC-06 | **PASS**（POC-04） |
| 服务类 | SAL-ORD-2026-00004（设备安装服务 ×1） | 不适用 | 无（0） | 不适用 | **无自动库存单据（已验证 0 条 Stock Entry）** | 服务无库存交付 | 待 POC-06 | **PASS**（POC-04） |

## 端到端测试状态
| 验收点 | 实际结果 PASS/FAIL/BLOCKED | 证据/单号/数值 | 差距与处理 |
|---|---|---|---|
| 环境真实运行且重启持久化 | **PASS**（POC-01） | docker compose down/up 后登录、Company、System Settings、apps 全部保留 | — |
| 系统及新用户默认简体中文 | **PASS**（POC-02） | 8 处 zh 空翻译用 cn_mfg_poc patch 修复；新用户/新会话中文 | 详见 POC-02-l10n.md |
| 左侧菜单/右侧操作区、角色权限 | **PASS**（POC-03） | 10 个角色门控中文工作台 + block_modules；3 角色实测 + 10/10 后端探针 | 详见 POC-03-navigation.md |
| 四种业务类型真实订单可提交查询 | **PASS**（POC-04） | SAL-ORD-2026-00001~00004（生产/耗材/零部件/服务）均可提交、列表筛选 | 详见 POC-04-orders.md |
| 耗材与零部件直接出库 | **PASS**（POC-04） | MAT-DN-00001/00002 真实扣减库存；无 BOM/工单 | 过滤耗材 50→40、法兰 8→3 |
| 服务无库存扣减 | **PASS**（POC-04） | INSTALL-SVC 无任何 Stock Entry / Work Order（均为 0） | 服务类订单 SAL-ORD-2026-00004 |
| 生产 BOM 和订单关系 | **PASS**（POC-05） | BOM-ASSY-X1-001 默认 BOM，单台材料 720 元；WO/PP 均回指 SAL-ORD-2026-00001 | 详见 POC-05-production.md |
| BOM 缺料与采购补货 | **PASS**（POC-05） | 2 台需求 RACK 4 / SENSOR 2，库存 1 / 0 → 缺 3 / 2 → MR-00001 → PO-00001(1200) → PRE-00002 | FASTENER 库存 12 富余，不采购 |
| 生产工单和两道 Job Card | **PASS**（POC-05） | MFG-WO-2026-00001 提交自动生成 PO-JOB00001 装配(60min,李工) / PO-JOB00002 检验(30min,张工)，均已完成 2 台 | Job Card 员工显示编号（GAP-05-03） |
| 原料仓→在制仓领料 | **PASS**（POC-05） | MAT-STE-2026-00003：RACK 4 / SENSOR 2 / FASTENER 8 由原材料仓转生产在制仓，1440 元 | — |
| 完工成品入库/成本 | **PASS**（POC-05） | MAT-STE-2026-00004：耗料 1440 → 成品 2 台 ×720 入产成品仓，与 BOM 标准成本一致 | 工序人工未计入（GAP-05-02） |
| 销售交付/部分交付 | **PASS**（POC-05） | MAT-DN-2026-00004 交 2 台，订单交付 100%，成品仓 2→0 | 部分交付场景见 POC-04 耗材/零部件 |
| 销售开票收款关联 | **PASS**（POC-05） | ACC-SINV-2026-00002 17600 → ACC-PAY-2026-00002 现金 17600，应收余额 0，订单 Completed | 中文支付方式「现金/银行转账」已建 |
| 共享材料需求/预留负例 | 未执行 | | |
| 角色越权直链拦截 | 未执行 | | |

## 待用户亲测
用户只需：打开本机地址 → 用中文测试账号登录 → 沿左侧菜单分别找四类订单 → 重点打开生产类销售订单，逐项点 BOM / Work Order / Job Card / Stock Entry / Delivery Note / Sales Invoice。未能直接找到的菜单或深层跳转要原样记录，而非替用户宣布使用简单。

## 最终差距分析
- ERPNext 原生即可使用：
- 需配置：
- 需独立 Frappe App 扩展：
- 不适合当前客户：
- 未确认项：
- 与 JSH ERP 对照后的选型建议：
