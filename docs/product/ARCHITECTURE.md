# 产品 V1 最小架构（业务主线优先）

## 总体形态
- ERPNext v16 + Frappe：**唯一业务权威源**。Sales Order / Customer / BOM / Production Plan / Work Order / Job Card / Purchase Order / Purchase Receipt / Stock Entry / Delivery Note / Invoice / Payment 等继续采用 ERPNext 原生 DocType 及过账规则。
- 自有 Frappe App：承接中文工作台、最简客户报备、本人任务视图、必要的共用业务 API 和企微身份映射。现有 poc/apps/cn_mfg_poc 先复用，长期可迁出产品 App；先不要为重构影响演示。
- PC：ERPNext Desk + 中文左侧导航和角色工作台，不另写整套 ERP 后台。
- 企业微信自建应用 H5：手机端常用业务 UI，通过身份授权调用同一 Frappe API。
- 企业微信 API 模式机器人 + OpenClaw：解析用户意图、自然语言和 Excel，调用受控 ERPNext API；机器人不得直接把模型生成值写数据库。
- 本轮是单一客户隔离 POC Site。未来优先按客户独立 Site/数据库交付，不建设共享 SaaS 后台。

## 逻辑主线
PC Desk → ERPNext DocType → ERPNext Site 数据库
企业微信 H5 → 企业微信 OAuth 用户会话 → 自有 Frappe API → 同一个 ERPNext Site
企业微信 Bot → OpenClaw/业务 SOP → 用户身份绑定 → 同一组受控 Frappe API → 同一个 ERPNext Site

PC、H5、Bot 可以有会话、文件、预览草稿、临时缓存，不可新建第二套独立权威的订单、库存、财务状态与生产任务表。

## 本期最少共用接口
- 客户：新增/报备，按授权查询客户及报备归属。
- 销售：当前用户订单列表、订单明细、交付/收款摘要。
- 生产：当前用户任务列表、任务进度/完成反馈（以标准 Job Card/约定标准任务为准）。
- 库存：按公司、仓库与角色权限查询现存数量及物料。
- 采购/Excel：上传模板并解析、草稿预览、校验、本人确认、原生单据提交、结果状态。
- 经营：授权用户查看 ERPNext 现成报表或基本摘要。

尽量使用 Frappe 已提供的 REST /api/resource 和少量受控的 /api/method 接口。对核心业务边界统一使用自有业务函数做服务端鉴权，而不是让机器人直接任意 CRUD。参考：https://docs.frappe.io/framework/user/en/guides/integration/rest_api

## 企业微信身份 / 权限（不可省略的底线）
- 企业 ID + 成员 UserID 与 ERPNext User 有明确绑定和唯一性校验；企业通讯录部门不是财务、仓库等业务权限。
- H5 在企业微信内通过 OAuth2 等官方机制确认真实成员身份，校验回调和 state、生成安全的站点会话；不能信任浏览器传来的任意 userId。
- Bot 真实消息身份经过通道认证及绑定，同一个 WeCom 成员映射同一个 ERP User；BotID 仅是通道上下文，不是业务授权。
- 不能用 ERPNext Administrator 通用 token 让所有普通员工拥有库存与财务全部权限。必须服务端检查员工本人的订单/Job Card、被授权仓库、可写单据类型以及必要的数据域。
- 离职、禁用、解绑或权限变更后，旧 H5 会话与机器人绑定均应拒绝继续操作。
- 重要写操作：服务端校验输入→未过账预览→用户本人明确确认→幂等及防重放→原生审核/提交→返回正式单据号。确认失败不能提前扣减库存。
- 保留审计：请求用户、渠道、时间、业务动作、ERP docname、状态；日志不包含密钥、完整 Excel 敏感内容。

## 资源与运行边界
- 当前 PC/Python/WSL/Docker/Bench 的实际运行信息由 BUILD-00 现场核验；旧 POC 登录地址不是现在可用的保证。
- 真实企业微信 H5 需要管理员配置自建应用、通讯录授权和可信 HTTPS 域名；真实 Bot 需要 API 机器人权限/通道配置。未具备时本地可继续做代码，但真人联通必须标 BLOCKED。
- 旧 JSH ERP 以及 F:\aierp-openclaw 的服务/密钥/插件保持原样，避免覆盖运行中的旧演示。新 ERPNext 适配器独立部署、独立配置。
- 永远不能把真实企业密钥/Token、密码、客户通讯录、生产业务数据或测试用户会话提交 Git。
- 接口开发和配置不允许批量修改 ERPNext 核心制造/库存/账务逻辑；需要上游 patch 的问题先标注原因与影响。

## 决策暂缓池
复杂成本核算、发票取消细节、全部财务本地化、扫码硬件、MES/APS、复杂 CRM、完整移动 ERP、全量 Excel 模板、AI 多步骤自主执行等，均不阻断首轮三端演示。涉及越权、数据破坏、重复过账等例外需最小处置。
