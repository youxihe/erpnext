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

**当前第一个任务：BUILD-00，见 docs/product/QUEUE.md。**