# POC 用户验收记录

**状态：POC-00～POC-06 全部执行完毕。** 除明确标注的已知缺口外，验收点均 PASS，均有真实单据/日志/截图支撑。详见 `docs/poc/evidence/POC-00~06`。

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
| 共享材料需求/预留负例 | **PASS**（POC-06） | 超卖负例：库存 40 卖 100 交货 → `NegativeStockError` 缺 60（allow_negative_stock=0） | 见 POC-06-handover.md 第 3 节 N1 |
| 角色越权直链拦截 | **PASS**（POC-06） | 销售用户读 GL Entry / Payment Entry / 建收款单 / 做总账凭证 均 `PermissionError`；对照项读销售订单放行 | 见 POC-06-handover.md N2-a~e |
| 无工单直接完工入库 | **PASS**（POC-06） | 不建工单完工 5 台 → `FinishedGoodError` 拦截 | N3 |
| 服务类物料误建工单 | **PASS**（POC-06） | 服务项 INSTALL-SVC 建工单 → `MandatoryError: bom_no` 拦截 | N4 |
| 非法数量订单 | **PASS**（POC-06） | 数量 −1 订单 → `ValidationError`：合计金额须 ≥ 0 | N5 |
| 已结清发票重复收款 | **PASS**（POC-06） | 再收款 → `ValidationError: Paid Amount is mandatory`（可收金额 0） | N6-a |
| 取消已收款发票 | **FAIL（已知缺口 GAP-06-01）** | v16 未阻止取消（探针已回滚，数据无损） | 建议收紧 cancel 权限 + 红冲 SOP |
| 重启后数据持久化 | **PASS**（POC-06） | 容器 stop/start 与 up -d 重建后 17 项指标完全一致 | 同时修复了「重启后 Web 不自启」 |
| 四类订单财务闭环 | **PASS**（POC-06） | 4 张发票（17,600/800/750/800）+ 4 张收款单，未收合计 0 | 服务类状态停留 To Deliver（服务无实物交付，属正常） |

## 待用户亲测
用户只需：打开本机地址 → 用中文测试账号登录 → 沿左侧菜单分别找四类订单 → 重点打开生产类销售订单，逐项点 BOM / Work Order / Job Card / Stock Entry / Delivery Note / Sales Invoice。未能直接找到的菜单或深层跳转要原样记录，而非替用户宣布使用简单。

## 最终差距分析
- **ERPNext 原生即可使用**：销售订单/交货/发票/收款；BOM（含工序工位）、生产计划、MRP 缺料、工单、生产任务单（Job Card）、领料与完工入库、库存台账与总账；多仓、多计量单位、批次序列号。
- **需配置（已在本次 POC 完成，可复现）**：简体中文默认值（8 处空翻译补丁）、中文工作台与角色门控（10 个工作台 / 36 模块屏蔽）、中文支付方式（现金/银行转账）、业务类型字段（生产/耗材/零部件/服务）、采购单价与仓库默认值。
- **需独立 Frappe App 扩展**：`cn_mfg_poc`（工作台 fixtures + patch 脚本）。若上线，建议追加：中国会计准则科目模板、增值税发票字段与打印格式、工位小时费率默认值、已收款发票取消保护钩子。
- **不适合当前客户 / 需注意**：不支持「无工单完工」这类灵活倒冲（需 `skip_transfer` 或工单补录）；服务类订单状态停留 To Deliver；工作台自定义数字卡区块在前端不渲染；Job Card 产能排程有上游缺陷（已用 `disable_capacity_planning` 规避）。
- **未确认项**：产能负荷视图与多订单合并排产未验证；多公司/多币种未验证；批次与序列号追溯未验证；实际打印格式（送货单/发票）未做中国样式定制。
- **与 JSH ERP 对照后的选型建议**：轻制造为主选 ERPNext（生产全链路原生免费，不必为工单/总账买插件）；纯贸易零售且 Java 团队选 JSH 落地更快。详见 `docs/poc/evidence/POC-06-handover.md` 第 6 节。

