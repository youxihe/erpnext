# Workbuddy 产品 V1 任务队列 — 2026-10-29

**这是新阶段唯一活跃队列；原 docs/poc/TASKS.md 是已完成的历史 POC。**

| 顺序 | 任务 | 最小可演示成果 | 状态 | 证据/提交 |
|---|---|---|---|---|
| BUILD-00 | 复核现有 POC 和八个 ERP 模块 | 当前环境/已有功能/缺的主入口清单 | PASS | docs/product/evidence/BUILD-00.md（commit 见 git log） |
| BUILD-10 | ERP PC 核心模块补齐 | 七角色可点击核心流程、四类订单不回退 | PASS | docs/product/evidence/BUILD-10.md |
| BUILD-20 | 三入口共用业务 API | 同一 ERP Site 的订单/库存/任务/客户读写接口与权限 | PASS(LOCAL) | docs/product/evidence/BUILD-20.md |
| BUILD-30 | 企业微信组织与用户身份 | 人员映射、账号绑定/撤权、H5 免登 | LOCAL_PASS / REAL_WECOM_BLOCKED | docs/product/evidence/BUILD-30.md |
| BUILD-40 | 企微自建 H5 | 客户报备/我的订单/我的任务/库存查询 | LOCAL_PASS | docs/product/evidence/BUILD-40.md |
| BUILD-50 | 企业微信 AI ERP 机器人查询 | 真实企微查同一个订单、库存和生产任务 | LOCAL_PASS / REAL_WECOM_BLOCKED | docs/product/evidence/BUILD-50.md + build50-bot.log(16/16) + build50-verify.log(8/8)（提交见 git log） |
| BUILD-60 | 机器人安全业务写入 | 报备客户、Excel 采购入库预览+本人确认 | LOCAL_PASS / REAL_WECOM_BLOCKED | docs/product/evidence/BUILD-60.md + build60-bot-write.log(20/20) + build60-verify.log(10/10) |
| BUILD-70 | 三入口统一验收 | 同身份/同单据/库存同值，真实客户端证据 | LOCAL_PASS / REAL_WECOM_BLOCKED | docs/product/evidence/BUILD-70.md + build70-cross.log(31/31) + build70-cross-restart.log(24/24) + build70-restart-diff.log(9/9) + docs/product/HANDOVER.md |
| BUILD-80 | 四类订单类型化（用户追加，2026-11-07） | 订单类型字段/四类分类入口/流程约束/三入口同步 | PASS(LOCAL) | docs/product/evidence/BUILD-80.md + build80-verify.log(16/16) + 3 张截图（commit 见 git log） |
| BUILD-90 | 轻制造基线与无工序制造验证 | 现有模块保留；无 Job Card 必填也能规范领料/入库，清楚记录差距 | PASS(LOCAL) | docs/product/evidence/BUILD-90.md + build90-audit.json + build90-native-verify.json（7/7，commit 见 git log） |
| BUILD-91 | 固定生产进度项目与任务 | 销售生产订单关联一个 Project + 九任务模板；负责人/目标日/状态/备注/预警 | PASS(LOCAL) | docs/product/evidence/BUILD-91.md + build91-setup.json + build91-verify.json（27/27）+ build91-http.json（24/24）；PROJ-0002 / TASK-2026-00019~00027，SLE 73→73（commit 见 git log） |
| BUILD-92 | 订单执行概览与整机实物流转 | 销售→BOM→缺料→采购→领料→成品入库→一次交货，库存有据；可点击单据链 | PASS(LOCAL) | docs/product/evidence/BUILD-92.md + build92-execute.json（15/15）+ build92-verify.json（26/26）+ build92-http.json（44/44）+ build92-stock-trace.json；SAL-ORD-2026-00006 / PROJ-0003 / 12 条 SLE（73→85），commit 见 git log |
| BUILD-93 | H5/Bot 接通 Project Task 和订单汇总 | 三入口看同一任务/库存/交期，H5可更新本人任务，Bot查询逾期和缺料 | PASS(LOCAL) | docs/product/evidence/BUILD-93.md + build93-setup.json + build93-verify.json（27/27）+ build93-http.json（18/18）+ build93-adapter.json（8/8）；SAL-ORD-2026-00007 / BOM-ASSY-X1-003 / PROJ-0004 / TASK-2026-00037~00045，李工 7 项任务，RACK 缺 2，SLE 恒 85；真实企微真人 UAT 仍 REAL_WECOM_BLOCKED |
| BUILD-94 | 轻制造角色联测和 UAT | 销售/设计/采购/仓库/生产/财务分角色实操；证据、状态及剩余阻断 | PASS(LOCAL) | docs/product/evidence/BUILD-94.md + UAT_BUILD94.md + build94-execute.json（12/12）+ build94-verify.json（27/27）+ build94-stock-trace.json；SAL-ORD-2026-00008 全链 11 张原生单据，李工/刘工双人完成 9 任务时成品仓 0、SLE 92→92，Manufacture 后 92→96，发货后 97；真实企微真人 UAT 仍 REAL_WECOM_BLOCKED；线上 d.urlxl.cn 未同步本轮增量 |
| PORTAL-FIX-01 | 统一导航内页缺「新建/保存」按钮 | 门户 CSS 整体隐藏 `.page-head`，连带藏掉主按钮 | DONE(本地+线上验证) | `docs/product/evidence/RELEASE-95.md` §10；commit `4deba804`；线上列表「添加销售订单」、表单「保存」均可见 |
| RELEASE-95 | 轻制造代码 Review Fix + 线上测试发布 | 缺料公式、真人角色权限、迁移兼容与安全门禁后，将 BUILD-90~94 发布至 d.urlxl.cn | ONLINE_PASS(BUILD-90~94 已上线；真实企微仍 REAL_WECOM_BLOCKED) | docs/product/evidence/RELEASE-95.md + build 证据；线上样本 SAL-ORD-2026-00006 / PROJ-0001 / MFG-WO-2026-00003 / MAT-DN-2026-00005；本地 23/23 + 44/44 + 8/8，线上验收 32/32 |
| UX-96A | 补齐生产进度创建/模板维护/负责人分派入口 | 管理员可从中文门户配置模板、从订单生成项目并分派任务 | ONLINE_PASS | docs/product/evidence/UX-96A.md；线上 38/38 + 浏览器 29/29 + 本地 42/42；样本 SAL-ORD-2026-00005 / PROJ-0002 / TASK-2026-00019~00027，SLE 52→52 |
| UX-96B | BOM 与销售订单显式确认及双向引用 | 销售订单行选用 BOM、BOM 页查询实际引用订单、区分默认建议 | ONLINE_PASS | docs/product/evidence/UX-96B.md；线上 38/38 + 浏览器 29/29 + 本地 42/42；样本 BOM-ASSY-X1-001/002、SAL-ORD-2026-00006（已确认）/00001（仅建议）/00008（选 002）；新增 custom_bom_confirmed 防默认 BOM 冒充确认 |
| FLOW-97 | 多订单需求→合并采购→入库→按工单领料的来源追溯 | 先核实 00001/00006 线上真实单据，再补链式双向追溯和共享库存口径 | ONLINE_PASS（FLOW-97A 审计 + FLOW-97B 上线） | docs/product/evidence/FLOW-97A.md（线上只读审计：两单 MR/PO/PR/WO/SE/DN 交集为空，00006 实物来自无 PO 入库 MAT-PRE-2026-00016，PO-00002 未收货 2 件 → 重复到货风险）；docs/product/evidence/FLOW-97B.md（新增 /order_execution 物料履约表 + /procurement_trace 集中采购来源；线上后端 30/30 + 浏览器 20/20、本地合并用例 40/40、UX-96 回归 42/42，库存零变动）；本地合并样本 MFG-PP-2026-00002 / SAL-ORD-2026-00015~00016 / PUR-ORD-2026-00006 |
| UAT-97R | 线上测试角色和账号整理 | 7 个中文岗位角色档案+管理员；测试账号岗位-A/B可识别，同岗位数据隔离可验证；原生角色保留 | TODO | docs/product/tasks/UAT-97R.md |
| UAT-98 | 全新隔离验收 Site 和期初准备 | 不清现有 d.urlxl.cn；另建干净 Site、完整主数据与移动平均期初库存，提供真人验收入口 | TODO | docs/product/tasks/UAT-98.md |
| UAT-99 | 用户本人分角色端到端测试 | 双销售订单、集中采购、独立工单、仓储制造、整机交货、财务成本手工 UAT | WAITING_FOR_USER | docs/product/UAT_MANUAL_V1.md |

> 2026-11-07 用户追加：BUILD-00~70 完成后确认 `/cn_portal` 统一导航布局可用，要求按客户原始需求配置「四种订单、BOM 拆分」。
> BOM 拆分口径用户要求**先等确认**，登记为 BACKLOG `BOM-01` 暂不实施；本阶段先完成 BUILD-80 四类订单类型化。

## 公共执行规则
- 只允许一个 IN_PROGRESS。每项完成后修改表格状态，添加实测证据位置、Git SHA，并自动认领下一项，不需要用户逐个提示。
- 必须有点击路径、接口/脚本证据、真实测试单号/数值、权限拒绝用例；不允许只靠写代码或截图虚报 PASS。
- 不新增重型 ERPNext 前端/自研库存或总账；先利用 Frappe 原生标准 DocType / REST / 自有 App。
- 真实企微接入依赖自建应用授权、可信域名等外部资源；若尚缺，先做可验证的本地开发，标明 LOCAL_PASS / REAL_WECOM_BLOCKED，**不能给 BUILD-70 整体 PASS**。
- 对安全/账务/库存真实风险只做最小保护；工序人工成本、发票细节等写入 BACKLOG 等用户排序。

## BUILD-00 — 现有 POC 和模块快速核对（首先执行）
目的：避免花时间重新安装、重复造数或写 ERPNext 原生已经有的模块。
- 安全检查本地 D:\ERP\erpnext 的 git status/未提交变更，fetch 并切换 product/erpnext-wecom-ai-v1-20261029，保留用户本地改动。
- 确认 v16 ERPNext/Frappe、隔离站点、Docker/Bench 的实际运行状况，不清理已有 volume；抽样打开原四类订单与生产链路。
- 以八大模块做“一张表”：客户/销售、设计/生产、采购、仓库、物流交付、财务、经营、系统权限。每个模块只标可直接复用 / 需加入口 / 确实缺最小功能。记录中文菜单、源码/单据位置。
- 快速检查 cn_mfg_poc 和原 ai-erp/OpenClaw 能复用什么，明确哪些 API 是 H5/Bot 共用；不写大篇架构报告。
完成：docs/product/evidence/BUILD-00.md 写实际结果及后续最小实现，提交 Git → BUILD-10。

## BUILD-10 — ERP PC 大模块优先，先可用再精细
- 保持左侧中文菜单+右侧功能区，销售/设计/采购/仓库/车间/财务/管理角色有主要入口；物流先保留交付。
- 客户与销售：客户资料/简单报备（最低客户+负责人+必要状态），四类订单创建和交付/收款状态查看。
- 设计/车间：基于原生 BOM、Work Order、Job Card 建“我的任务”入口，能查看和更新进度；不重造 MES。
- 采购、仓库：原生采购申请/单/入库、库存、出库/领料/完工入口能用；管理/财务可从原生报表或简化工作台看必要数据。
- 每个大模块至少 1 个真实业务动作/单据或只读入口；ERP 原生已满足的标复用，不重新写。关键角色做权限负例。
不做：复杂订单 360、美化、大量中国会计本地化、人工费率、复杂审批。
完成：PC 操作路径、截图、样本单据与关键差距写 docs/product/evidence/BUILD-10.md → BUILD-20。

## BUILD-20 — H5 和 Bot 的统一 ERPNext 服务接口
- 使用 Frappe 原生 REST + 有限的自有 Frappe App 接口，不建独立业务权威数据库或过重 Java 网关。
- 首批合同：客户报备/查客户、我的销售订单/交付、我的 Job Card/更新、授权库存查询、采购入库 Excel 草稿准备/确认（解析逻辑可在 BUILD-60 实现）。
- 同一受信身份最终映射 ERP User，执行服务器端角色/公司/仓库/员工归属检查；不把 Administrator token 暴露给 H5/Bot。
- 写入执行输入校验、必要的原始确认和幂等；符合标准 ERPNext 单据的提交机制；日志可以定位用户及单据号。
- 用不同权限角色测试允许/拒绝、一次受控写入；输出简明接口表（路径/请求/响应/权限/错误）与真实 API 回放。
完成：docs/product/evidence/BUILD-20.md + 最小 API 合同 → BUILD-30。

## BUILD-30 — 企业微信组织 + 账号绑定 + 自建应用身份
- 从企业微信成员/部门同步形成“企业 CorpID + 成员 UserID ↔ ERPNext User”绑定；默认**不**把部门自动变为 ERP 财务/库存权限。
- 先做 mock/本地测试，真实环境配置成员授权、企业微信自建应用、合法 HTTPS 可信域名、服务端 OAuth2 身份获取，生成有期限的安全会话；禁用/离职/解绑后失效。
- 账号映射要与原有 OpenClaw 机器人用户主体一致，不允许客户端任意伪造 UserID。
- 如需用户提供 CorpID、AgentID、Secret、可信域名/管理员授权，仅列配置项及本地安全放置位置，不索要聊天中明文 Secret。
完成：真实企微成员免登并可访问对应 ERP 权限的 API；没有真实配置则标真实企微 BLOCKED，而非假 PASS。证据 docs/product/evidence/BUILD-30.md → BUILD-40。

## BUILD-40 — 企微自建 H5 业务入口
- 移动端中文首页及四个核心入口：客户报备、我的销售订单/交付、我的车间生产任务、库存查询。无需完整复制 ERP PC。
- H5 只经 BUILD-20 的正式业务 API 读写；不能绕过企业微信身份或使用共享管理员密钥。
- 客户报备能写入 ERPNext；车间员工能完成/反馈本人任务；我的订单/库存按权限读取；PC 同步能看到新数据。
- 先本地移动端可用，再真实企业微信客户端打开测试，记录截图、实际 ERP 单据与角色权限拒绝。
完成：docs/product/evidence/BUILD-40.md；真实企微信息不足时不得标 REAL PASS → BUILD-50。

## BUILD-50 — AI ERP 机器人只读链路（优先复用旧 OpenClaw）
- 查看 youxihe/ai-erp 和 F:\aierp-openclaw 的原通道、身份绑定、SOP、查询工具；不要修改旧 JSH 当前运行时。
- 为 ERPNext 建独立受控工具适配，查询有权仓库存量、我的订单/交付进度、我的车间任务、简要经营数据。
- 使用企微本人身份绑定 ERP User；不能靠提示词自报身份；数据来自同一个 ERPNext Site，而非模型猜测。
- 真实企业微信客户端进行“这个订单到哪一步”“传感器还有多少库存”“我今天有什么任务”的测试，与 PC/H5 数值对照。
完成：docs/product/evidence/BUILD-50.md；缺 Bot API 权限先保留本地验证证据并标 BLOCKED → BUILD-60。

## BUILD-60 — AI 机器人首批安全写操作
- 自然语言报备客户：最少字段/查重→预览→本人明确确认→ERPNext 正式客户/报备单，PC/H5 可见。
- 一个 Excel 采购入库模板：收到文件→安全解析/逐行校验→预览草稿→本人确认→走合法 Purchase Receipt/标准采购业务单据；库存发生一次真实变化。
- 重用原 AIERP POC 的草稿、确认、幂等、审计思想，不复用旧 JSH 业务 ID 或直接改 MySQL 库存。
- 测试重复确认不能重复入库、无权仓库拒绝、无效文件拒绝、用户取消草稿后不扣库；记录正式单据号及前后库存。
完成：docs/product/evidence/BUILD-60.md + 真实企微测试对话；未联通仅能标本地通过 → BUILD-70。

## BUILD-70 — 三入口联合验收与交付
- 同一测试客户、测试订单、仓库物料与 2 名不同角色；PC 创建记录→H5 和 Bot 可查；Bot 报备客户→PC/H5 可见；H5 更新车间任务→PC/Bot 立即一致；Bot Excel 入库→PC/H5 库存变动仅一次。
- 测登录身份、人员撤权、越权、重复提交、真实用户确认；重启后业务单据仍在，机器人恢复连接。
- 提供用户体验清单：PC 地址、企微应用/H5 入口、Bot、账号安全交付方式、四类样本订单、测试 Excel 和操作步骤。
- 真实客户端 UAT 通过才算最终完成；不把模拟环境/HTTP 200/生成页面算已上线。
完成：docs/product/ACCEPTANCE.md 的真实结果 + docs/product/evidence/BUILD-70.md、未解决项记录到 BACKLOG.md；等待用户正式体验与反馈。

## 2026-11-08 增量任务：轻生产、重业务单据（优先级覆盖旧 BUILD-10/20 的工序细节）
正式决策：`docs/product/decisions/LIGHT_MANUFACTURING_20261108.md`。**BUILD-00～80 既有 PASS、LOCAL_PASS、REAL_WECOM_BLOCKED 全部保留**；不重新排队、不重做旧 POC。只对新增功能做增量建设，不破坏现有 PC/H5/机器人能力。按 BUILD-90→94 推进；细节继续写 BACKLOG。

### BUILD-90 先审计，做最小原生验证
- 检查当前 `git status`、产品分支、部署 Site、`/cn_portal`、`/wecom_h5` 和机器人实际状态，保留 Workbuddy 现有最新改动，不 reset 数据库。
- 确认原生 Project Template/Project/Task 能按销售订单关联并生成固定任务；若已有能力直接复用，不建立冗余任务表。
- 关键技术验证：在 ERPNext v16 **BOM 无 Operations/无 Job Card 报工**场景，是否仍可 Work Order→生产领料/转移→Stock Entry Manufacture→成品入库。记录真实测试单据与库存；如不支持，仅选最小配置/替代路径，不强迫生产人员做工时报工。
- 说明已完成的四类订单/导航与生产模板的改造差异，并输出 `docs/product/evidence/BUILD-90.md`。
- Gate：制造标准单据仍可靠、不会因任务状态变更触发库存；此任务仅做短验证、不铺大而全 PRD。

### BUILD-91 生产固定任务（用户最关心的简单体验）
- 以实际客户 Excel 的九阶段为默认**可配置**模板：机架焊接、机加工件加工、内钣金焊接、电控板组装、管道焊接、机构件组装、电气组装、外蒙板组装、调整老化。
- 一张生产类销售订单可建立/关联一个生产进度 Project，按模板生成 Task；去重、重复点击幂等，能找到原销售订单。
- 任务最小字段：名称、负责人、目标日期、状态（待开始/进行中/已完成/异常）、完成时间、备注和附件；允许修改/分派。
- 目标日期已过且未完成=逾期；未来三日内到期且未完成=临期（3 日可配置）；按角色在 PC 查看“我的任务”“订单生产进度”。
- 保留 ERPNext 原生 Job Card 的后台能力，但本期员工界面不能强制打开或提交 Job Card；不能由 Project Task 自动触发库存过账。
- 用两个普通角色演示任务更新及权限拒绝，保存真实 Project/Task ID 与 `docs/product/evidence/BUILD-91.md`。

### BUILD-92 订单执行概览 + 标准交易闭环
- 延续用户已认可的 `/cn_portal` 一级顶部/二级左侧导航；不重构导航，不另写全 ERP。
- 从一张“整机一次发货”的生产类 Sales Order 出发，聚合 Item/BOM 的订单选用关系、Production Plan/Material Request、Purchase Order/Receipt、Work Order、Stock Entry、Delivery Note 和 Sales Invoice/Payment Entry 的**真实引用/状态**。
- 销售订单概览可见：产品/数量/承诺交期、BOM、缺料/已采购/已入库/已领料、固定任务完成数和逾期数、实物完工入库、一次交货、开票/回款；点击跳原生单据。财务字段按权限开放。
- 分角色用真实原生单据执行：采购申请/下单、仓库采购入库、仓库领料、正式制造完工入库、Delivery Note 整机发货；库存数量和价值合理，严禁 Project Task 标记完成即扣库/入库。耗材/零部件直接出库、服务不扣库存继续通过。
- 优先复用现有 POC 单据与新建测试订单，给出 `docs/product/evidence/BUILD-92.md` 的单据号/库存增减/角色操作路径，不为复杂 BOM 多阶或逐件交货阻塞。

### BUILD-93 三入口接力，不等 ERP 叶子功能完善
- 优先在原 BUILD-20 共用 API 上增加/调整 `orders.summary`、`production.tasks.mine`、`production.tasks.update`、`materials.shortage` 的轻量契约，返回**真实** ERPNext/Project Task/单据来源、当前授权 User。
- H5 “我的生产任务”只需本人任务列表、目标日期/临期逾期、状态更新、备注/附件；销售订单与采购缺料用轻量查询即可。
- 机器人能够基于同一 Site 说出订单当前进度、任务逾期、BOM 缺料；不得让模型根据普通 ToDo 进度编造真实制造完工量。
- 保存 PC/H5/Bot 本地互相一致的测试证据；真实企业微信成员与真实机器人如仍缺权限，状态保留 `REAL_WECOM_BLOCKED`，列出具体需要用户介入的资源。
- 不反复重建以前已实现的客户报备/Excel 写入闭环；记录 `docs/product/evidence/BUILD-93.md`。

### BUILD-94 分角色联合验收和交接
- 用一笔新的或可复现的生产订单、整机一次发货，走销售→设计→采购→仓库→生产进度→仓库完工入库→发货→财务；不同角色分别操作各自页面并保留单据号和库存变化。
- 至少两名生产人员完成模板任务更新；有目标日期/逾期预警；**所有任务已完成也不能改变成品仓数量**，入库必须有原生 Manufacture 事务。
- 验证四类型订单依旧可用、服务单不会扣库存、耗材/零部件不触发生产；权限越界和重复写入拒绝。
- PC 更新任务→H5/Bot 查询一致；H5 更新任务→PC 可见。真实企微是否可用必须单独判定。
- 输出 `docs/product/evidence/BUILD-94.md`、一页角色操作 UAT、真实单号/页面 URL、未解决 BACKLOG；不因账务叶子功能或 UI 美化延迟交付。

**明确与旧规划的调整**：旧 BUILD-10/40/70 可能仍要求车间员工直接填写 Job Card。本次新方案明确改成 Project Task 状态反馈；原生 Work Order/Stock Entry 仍负责合法入库出库。不要修改历史 BUILD 的 PASS 证据，只应增量核对新业务模型。


## 2026-11-08 发布门槛 RELEASE-95（已完成，ONLINE_PASS）
- **结果**：BUILD-90~94 + 本轮 Review Fix 已真实部署到 https://d.urlxl.cn，线上验收 32/32，见 `docs/product/evidence/RELEASE-95.md`。部署源 `12861af4`。
- 线上样本单：`SAL-ORD-2026-00006` / `PROJ-0001` / `TASK-2026-00010~00018` / `MFG-WO-2026-00003` / `MAT-STE-2026-00008,00009` / `MAT-DN-2026-00005` / `ACC-SINV-2026-00006` / `ACC-PAY-2026-00006`。
- 真实企业微信真人 UAT 仍 `REAL_WECOM_BLOCKED`；共用测试口令、在制仓余料、多生产员分派等问题见 BACKLOG `SEC-01 / LM94-03 / LM91-05`。

## 2026-11-08 发布门槛 RELEASE-95（原始任务要求，保留备查）
- **当前产品代码 HEAD** `e1b87ec766c1f9f61d7d0bfdb29de1de42d1a2f2`。BUILD-90~94 为 LOCAL_PASS，线上 `https://d.urlxl.cn` 的 BUILD-90~94 仍未发布，真实企业微信真人 UAT 仍阻断。
- 详细 release task、发现、Gate、部署与验收步骤见 `docs/product/releases/RELEASE_95_TEST_20261108.md`。执行前先核对本分支最新 HEAD，不能仅按本处旧 SHA 部署。
- **优先处理两项产品风险**：缺料公式重复计入采购已收数量；原始脚本使用 `insert(ignore_permissions=True)`，不能替代采购、仓库、财务真人账户在标准 PC/API 中的单据提交验收。
- **发布前安全门槛**：核验线上 Site、数据库大小写兼容/迁移补丁、完成数据库+文件备份且可回滚；防止公网 Mock 任意选用户/共用密码泄露，禁止未经授权更改其他客户环境。
- 完成线上真实验收且无重大风险后才能把 RELEASE-95 标记 `ONLINE_PASS`，反之 `BLOCKED` 并记录准确原因，不能只凭 Git push 或本地 PASS 宣布发布成功。
- **合并策略**：独立产品分支就是 v16 测试部署来源。默认 `develop` 属于 v17，不创建跨大版本合并 PR，不将 POC 代码直接合并到 `develop`。

## 2026-11-08 用户现场体验反馈：业务管理入口补齐（当前下一组任务）
用户体验线上 /production_board 和 /order_execution 后反馈：管理员找不到九阶段模板管理、订单项目创建/分派入口；不清楚 Sales Order Item ↔ BOM 的显式绑定与双向引用。

**当前优先 UX-96A → UX-96B，保留 RELEASE-95 ONLINE_PASS，不重复测试或发布历史 POC**。详细要求与 Gate 见 `docs/product/tasks/UX-96A.md`、`UX-96B.md`。两项都完成后发布到既有 d.urlxl.cn 测试站点并进行实名角色验证。

> **2026-11-08 完成**：UX-96A / UX-96B 已发布 d.urlxl.cn 并完成真实角色验收（后端 38/38、浏览器 29/29、本地 42/42，库存零变动）。
> 证据见 `docs/product/evidence/UX-96A.md`、`UX-96B.md`。验收中额外修掉两个真实缺陷：
> ① 部署脚本 `clear-cache` 在 bench 根目录执行导致服务未重启；② 「已提交改 BOM 需受控变更」规则因字典键判断写错从未生效。
> 并新增 `Sales Order Item.custom_bom_confirmed`，避免 ERPNext 自动带入的默认 BOM 被当成「本单已确认」。

- 生产任务模板是 Project Template「整机生产九阶段」，具体阶段由 Template Task 引用；Project.sales_order ↔ Sales Order.project；Task.project/source_sales_order 关联。现有后端 `production.create_project` / `assign_task` 可复用，目前 /production_board?view=order **只读**，未提供创建/分派 UI。
- BOM 选用字段为 `Sales Order Item.bom_no`（子表、行级）；当前 order_execution 在该字段为空时回退产品默认 BOM 进行物料展示，必须明确标注**默认建议不是本单已确认 BOM**。BOM 页面需要反向查询显式引用的 Sales Order Item、Work Order。
- 主要做业务入口、配置和关联导航，不建全新 MES/BOM 库存业务模型，不让 Project Task 操作触发库存事务。
- 标配权限服务端校验、实际 Administrator/生产经理/销售角色、测试数据、线上 URL/截图。避免退化到只通过脚本操作。


## 2026-11-08 新增 FLOW-97：多销售订单共享物料、采购合并追溯
用户线上反馈 SO 00001/00006 销售相同设备，BOM 共用，但订单执行概览无法理解各自采购需求、采购单、入库单和实际领料关联，尤其是合并采购。属于销售/采购/仓储主流程问题，优先于非关键叶子功能。
执行前读 docs/product/tasks/FLOW-97.md。先做线上只读事实审计；不要根据同一 BOM、SKU 或时间接近捏造单据关系；审计确认后最小补关联导航和共享库存说明，不新开发 MRP/库存预留引擎。


## 2026-11-09 真人 UAT：UAT-98 → UAT-99
已确认：采购面向共用物料仓，生产工单按销售订单独立，原材料移动加权平均；车间只管九阶段任务，不做工时与 Job Card 报工。新增阶段不重复开发 ERPNext 原生库存和制造。
UAT-98 由 Workbuddy 准备隔离站点、基础资料和期初，禁止在现有 d.urlxl.cn 做任何事务清空、公司交易删除、SQL 批量删除或清零库存。UAT-99 必须由用户本人操作，不能拿 Workbuddy 的自动执行脚本冒充人工验收。环境和测试标准详见 docs/product/tasks/UAT-98.md 与 docs/product/UAT_MANUAL_V1.md。


## 2026-11-09 用户人工测试优先：UAT-97R
用户正在 d.urlxl.cn 线上**测试环境**进行人工业务流程测试，优先消除角色过多、账号无法识别的体验问题。Workbuddy 先执行 docs/product/tasks/UAT-97R.md 并上线验证。此任务**不依赖新 Site UAT-98**，不能因其尚未执行而阻断角色整理。UAT-98/99 保留供后续独立干净数据验收；不对当前站点删除历史订单、库存或账务。
