# Workbuddy AGENTS — ERPNext + 企业微信 + AI ERP 产品 V1
生效日期：2026-10-29。目标分支：product/erpnext-wecom-ai-v1-20261029。

## 北极星（用户已确认）
**让一个客户同时体验中文 ERP PC、企业微信自建 H5、企业微信 AI ERP 机器人，三个入口操作同一个 ERPNext Site 的真实业务数据、业务权限和单据。**
现在优先补齐大模块、打通三入口，不纠缠发票取消细节、工序人工成本、复杂审批、报表美化等叶子功能。发现后写入 docs/product/BACKLOG.md，等待用户评估优先级。只有主流程不通、越权/泄密、错误库存/重复账务等关键风险可以阻断主线。

## 必读
- docs/product/README.md：新阶段总目标与已有成果。
- docs/product/QUEUE.md：唯一产品阶段任务队列、每项任务详细要求和验收门槛。
- docs/product/ARCHITECTURE.md：共享 API、身份权限和数据权威源。
- docs/product/ACCEPTANCE.md：PC/H5/Bot 联合验收标准。
- docs/product/BACKLOG.md：叶子功能暂缓池。
- docs/poc/README.md、docs/poc/UAT.md、docs/poc/evidence：旧阶段的证据，只供参考，禁止重新做 POC-00 至 POC-06。

## 环境事实与边界
- 用户 Windows 工作区 D:\ERP；ERPNext 源码 D:\ERP\erpnext；已有 ERPNext POC 环境与 D:\ERP\poc 有关。
- 本分支从已完成 POC 的实际 HEAD 69c4507b 派生。保留 ERPNext v16 + Frappe v16 稳定配对，不误切仓库默认 develop（ERPNext v17 开发分支）。
- 当前源码中已有 POC 扩展 poc/apps/cn_mfg_poc，中文菜单和四类订单已有实测记录；优先复用，避免为重命名、重构、拆仓库延迟主线。长期业务代码尽量独立 Frappe App/配置，少改 ERPNext 原生源码。
- 旧 JSH ERP + OpenClaw 项目在 youxihe/ai-erp / F:\aierp-openclaw；允许调研复用 SOP/工具思路，不允许覆盖 JSH 现有数据库、运行时、绑定信息和插件。
- 业务类型：生产（BOM→工单/任务→领料/完工→交付）；耗材/零部件（直接库存采购/交付，无生产）；服务（只做服务记录，不自动扣库存）。不做原料合成药水 MIX。
- 所有业务数据库以 ERPNext DocType 为权威。PC、企微 H5、机器人不得各自维护销售订单/库存/采购/任务的第二份真相。
- 当前只针对隔离测试 Site 写入虚构数据；严禁未经批准部署公网、操作真实客户生产环境、重置未知 Docker 卷和提交密钥。

## 执行与自动续派
1. 单 Workbuddy 主 Agent，单活跃任务，严格按 docs/product/QUEUE.md 的 BUILD-00→BUILD-70 顺序推进。
2. 一项做完：实测+权限负例+真实数据/单号+文档证据+Git commit/push，然后自动做下一项，无须等用户逐项提醒。
3. 状态只允许 TODO / IN_PROGRESS / PASS / BLOCKED；不可把写了代码、页面 200、Mock 结果当真人验收。
4. 如果缺企业微信 CorpID/AgentID/Secret、可信 HTTPS 域名或 Bot 权限，先交付可本地验证的模块，写清最少需要的配置，真实企微 UAT 必须保持 BLOCKED；不能编造凭据。
5. 不要用 Administrator 共享 Token 代替企微员工权限；企业微信人员须绑定 ERP User，服务端验证数据范围与停用撤权。
6. 机器人及 Excel 重要写操作必须预览→本人明确确认→幂等→原生 ERPNext 单据，防止重复过账与越权。
7. 禁止把密钥、密码、Token、企业通信录隐私写进 Git 或测试报告。使用本地 ignored env，并提供示例模板。
8. 成果只推本产品分支；不要往 upstream 或默认 develop 合并，遇不确定业务规则先保留最简单可用行为并登记待评估。

**BUILD-90～94 已于 2026-11-08 全部 PASS(LOCAL)，见 docs/product/QUEUE.md 与 docs/product/UAT_BUILD94.md。已完成 BUILD-00～80 为历史成果，不得重复执行。下一步由用户决定优先级：① 把 BUILD-90～94 增量同步到线上 d.urlxl.cn（LM94-01）；② 真实企业微信真人 UAT 所需凭据（仍 REAL_WECOM_BLOCKED）；③ BOM-01 复杂拆分/替代料口径。**
## 2026-11-08 用户最终确认：轻制造实施方向（最高优先级）
- 决策全文：`docs/product/decisions/LIGHT_MANUFACTURING_20261108.md`。与此前「生产必须使用 Job Card 更新工序/工时」的描述冲突时，**以本决策为准**。
- 业务重点是销售订单、设计 BOM、缺料采购、采购入库、工单领料、实物完工后的成品入库、Delivery Note 整机一次发货、开票收款；采购、仓库、销售、财务须实际使用标准单据。
- 生产只做固定阶段任务：优先 Project Template + Project/Task，记录负责人、目标日期、状态、完成时间、备注/附件、临期/逾期。**不要求生产人员操作 Job Card、正式工序报工、人工成本或详细工位。**
- 原生 Work Order/Stock Entry **不能省略**，由仓库或授权人员执行标准库存事务。生产任务标记完成**绝不能自动完工入库**，防止账实不符。
- BOM 按标准产品优先、按订单选用/非标另版；不要求所有产品都有多级 BOM。第一阶段整机一次交付，不做拆组件交货或物流轨迹。
- 保留已落地的 `/cn_portal` 顶部一级/左侧二级中文导航，优先完善订单执行概览，而非重做界面。
- 以增量任务 BUILD-90～94 接续现有主队列。BUILD-30/40/50/60/70 的既有 LOCAL_PASS 不能当 REAL_WECOM_PASS；真实企微接入继续是阶段验收重点。
- 用户已经在聊天中披露过公用测试密码；禁止复述/提交旧口令，尽快核查独立凭据/管理员公网访问并做最低限度保护。



## 当前上线测试任务（2026-11-08）
BUILD-90~94 已有本地 PASS 证据，**当前新任务为 RELEASE-95**：
读取 `docs/product/releases/RELEASE_95_TEST_20261108.md`，先做关键 Review Fix、真实角色权限验收、部署数据库迁移/备份门槛，满足后部署 `https://d.urlxl.cn` 并做线上实测。
这不是生产发布，不允许直接对上游 `develop` 合并。线上未真正验证前，不得写 ONLINE_PASS。
