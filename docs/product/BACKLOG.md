# 细节 Backlog — 先登记，用户决定何时做

## 三档优先级
- S0：主流程无法操作、数据损坏/错库存/重复过账、权限越界或泄密。允许立刻做最小安全隔离与修复，不放任明显风险。
- S1：本阶段大模块/三入口缺少必要主功能，比如客户报备不能写入、车间任务无法更新、企微身份无法映射。归当前 BUILD 任务处理。
- S2：非关键叶子功能，登记后请用户决定是否排期；Workbuddy **不得**为了顺手完善而中断主线。

## 已知细节先暂缓
| 来源 | 事项 | 当前决定 |
|---|---|---|
| POC GAP-06-01 | 已收款发票取消的高级流程和红冲限制 | 暂不做细节；普通用户不开放危险 cancel/delete，若可造成错账则先最小限制 |
| POC GAP-05-02 | 工序人工、工位小时费率/制造费用精算 | 暂缓 |
| POC GAP-05-03 | Job Card 员工编号改中文姓名 | 暂缓，除非阻断车间辨认任务 |
| POC UP-05-01 | 复杂自动排程/工作站产能安排 | 暂缓，首批只要人工任务进度 |
| POC 服务订单 | 非库存服务订单 To Deliver 的展示优化 | 暂缓，首批允许轻量履约记录 |
| POC 工作台 | KPI 数字卡渲染、报表/页面美化 | 暂缓，能看数据即可 |
| 后续产品化 | 正式中国会计准则科目模板、税控/电子发票 API | 暂缓 |
| 后续产品化 | 复杂客户报备保护期、营销 CRM | 暂缓 |
| 后续产品化 | 全量生产 MES、APS 排程、条码硬件 | 不在本阶段 |
| 后续产品化 | 所有 Excel 入出库模板、完整机器人工具集 | 首批只做一个安全采购入库闭环，后续按需求扩展 |
| 后续产品化 | 多企业共享 SaaS、全新 Vue PC 后台 | 不在本阶段 |
| BUILD-50 OBS-50-01 | `frappe.logger` 默认级别 ERROR，cn_api/cn_bot 的 INFO 审计不落盘；bot 侧已改直接写站点日志，BUILD-20 的 api 侧待统一 | S2，建议与审计方案一起统一处理 |
| BUILD-50 OBS-50-02 | 机器人适配器密钥目前由本机文件注入，正式部署需改密钥管理并叠加来源 IP 白名单 | S2，上线前必须做 |
| BUILD-50 OBS-50-03 | `order_progress` 进度文案仅由订单状态推导，未纳入物流在途/部分出库细粒度口径 | S2 |
| BUILD-60 OBS-60-01 | Excel 解析只读取单元格值（`data_only=True`），不支持批次/序列号、多币种入库 | S2，按需求扩展 |
| BUILD-60 OBS-60-02 | 真实企微文件消息（Excel 附件下载）依赖 Bot API 授权；当前本地联调用 `ERP_BOT_MEDIA_DIR` 模拟「文件已落媒体目录」 | S1，真实 UAT 前必须打通 |
| BUILD-70 OBS-70-01 | 机器人网关账号只有 `All/Guest`，管理类接口（如通讯录同步）需另用管理员 Token；网关角色是否扩权待定 | S2，建议保持最小权限 |
| BUILD-70 OBS-70-02 | 撤销权限走 SQL 直接改 `tabUser`，若改为 UI 操作需注意 Frappe 缓存与事务快照（脚本内读数需先结束事务） | S2，仅测试脚本相关 |
| BUILD-70 OBS-70-03 | 本轮所有验收均在 Mock 企微通道下完成；真实企微 8 个联合场景尚未有人做过 | S0（阻断 V1 最终完成），需用户授权后执行 |
| BUILD-70 OBS-70-04 | 体验账号统一测试密码已重置（本机文件记录，不进 Git）；正式交付前应改为各自独立密码并强制首次修改 | S1，上线前必须做 |
| UI-01 | `/cn_portal` 统一导航原型已交付（顶部一级 + 左侧二级 + 同源 iframe）；未做：登录后默认跳门户、原生页面「返回统一导航」入口、移动端适配、菜单配置化 | S2，见 `NAVIGATION.md` 路线 A，待用户体验后定优先级 |
| UI-02 | 是否引入 Solvronix Desk 3.0（顶部菜单栏主题）或自研 Desk 布局 app，需先验证 Frappe 16.53 兼容性与可回退性 | S2，见 `NAVIGATION.md` 路线 B/C，需用户决策 |
| BOM-01 | BOM 订单归属、多级和拆分粒度 | **用户 2026-11-08 已明确基本方向**：标准 BOM 优先，非标订单选用独立版本，优先单层满足真实采购，分层规则/替代料等复杂细节继续由客户确认。基础订单→BOM→采购在 BUILD-90/92 验证，不再全项阻断 |
| BUILD-80 | 生产类订单是否强制要求 BOM / 工单；订单行混合类型是否要拦 | 本轮未加强校验，避免与 BOM-01 口径冲突；混合行保持允许 | S2，随 BOM-01 一起评估 |
| BUILD-80 | 四类分类入口目前仅在 `/cn_portal` 注入，原生 Desk 只有「销售订单」+ 标准筛选 | 用户已确认统一导航为主入口；若以后要原生 Desk 也有四个入口，需自定义 Page 或 Query Report | S2，按实际使用反馈决定 |

## 新发现问题如何记录
日期、模块/场景、现象、真实影响、可重现路径、S0/S1/S2、建议处理方式、是否用户已批准。S2 一律先留在这里，不自动新建开发任务；如需升级到 S1 请在 QUEUE 中注明理由，重大范围调整交用户判断。

## 2026-11-08 轻制造新增后续议题
- 生产任务模板是否按设备类别变化；九项仅为目前客户 Excel 的首版样例。**BUILD-91 做模板可配置，细颗粒依赖待用户优先级评估。**
- BOM 复杂多层、替代料、自动合单采购、多项目跨工单预留、精细制造成本：暂缓，先确保每单物料需求和采购/领料/入库真实闭环。
- 生产任务复杂工序/Job Card 强制报工、人工费用、生产百分比换算：**不在本阶段**；原生能力保留，不强制车间使用。
- 交付逐组件发货、复杂包装、运输轨迹：**不在本阶段**，首期整机一次交货。
- 统一导航此前已经落地并获用户认可，避免无意义的 UI 重构；后续只按真实使用痛点调整。

## BUILD-90 实测后新增观察
| 编号 | 事项 | 决定 |
| --- | --- | --- |
| LM90-01 | `Task.status` 原生选项 Open/Working/Pending Review/Overdue/Template/Completed/Cancelled，与决策「待开始/进行中/完成/异常」不一致 | S2，BUILD-91 做最小映射，不重造状态机 |
| LM90-02 | `Project Template Task` 子表仅 2 字段，无 start/duration/task_weight/description | S2，九任务负责人与目标日期在生成 Task 时按规则计算 |
| LM90-03 | 现有 `my_jobs` / `update_job_progress` 基于 Job Card，与新的 Project Task 任务视图形成两套「我的任务」 | S2，BUILD-93 做兼容迁移或收口，员工界面不强制 Job Card |
| LM90-04 | BUILD-90 只验证 `skip_transfer=1` 的直达 Manufacture 路径 | S1，BUILD-92 结合真实工单再验 `Material Transfer for Manufacture` 两段式与防重复扣库 |

## BUILD-91 实测后新增观察
| 编号 | 事项 | 决定 |
| --- | --- | --- |
| LM91-01 | ERPNext v16 `Project.after_insert() → copy_from_template()` 内部用 `.insert()` 建 Task，而原生 Task DocPerm 只授权 `Projects User / HR Manager` 建单；生产经理走纯原生模板复制会抛 `PermissionError` 并留下 0 任务的 Project | S2。本期由 `create_project()` 读模板行、复用原生日期算法、用 `ignore_permissions=True` 生成原生 Task（角色已在服务端前置校验）；以后若要在原生 Desk 直接用模板复制，需评估给 `Manufacturing Manager` 补最小 `Custom DocPerm`，注意 `setup_custom_perms` 会整体切换权限表 |
| LM91-02 | 生产人员（Manufacturing User）在原生 Desk 没有 Task 读写权限，只能通过 `/production_board` 受控 API 更新本人任务 | S2。符合「员工界面不重造 ERP」的方向；若客户要求原生 Desk 也能编辑，再评估最小 DocPerm 和 owner 级约束 |
| LM91-03 | `Task.production_attachment` 字段已建，H5/机器人的附件上传与文件权限尚未接通 | S1，BUILD-93 结合真实企微文件授权处理；缺授权期间保持 BLOCKED |
| LM91-04 | 生产类订单 `SAL-ORD-2026-00001` 已完成交付，未建生产进度 Project；当前仅 `SAL-ORD-2026-00005` 有 PROJ-0002 | S2。BUILD-92 若需要历史订单概览，再决定是否补建，不自动批量造数 |
| LM91-05 | `setup_template()` 会自愈并清理「无 project / is_template=0 / status=Open 且 start/duration 与九阶段一致」的孤儿 Task | S2。仅清理本脚本失败产物，绝不触碰项目下正式 Task；线上首次执行需先核对是否存在同名 Task |

## BUILD-92 实测后新增观察
| 编号 | 事项 | 决定 |
| --- | --- | --- |
| LM92-01 | 现有 `SAL-ORD-2026-00005` 是采购件 SENSOR、无 BOM 且无任何关联单据；BUILD-92 另建 `SAL-ORD-2026-00006`（ASSY-X1 整机）跑完整链路 | S2。历史订单不改动；若要让老订单也能显示概览，需先由客户确认是否补建 BOM/项目 |
| LM92-02 | `BOM-ASSY-X1-001` 标准版带 2 道工序，本轮按 BOM-01 方向为订单建独立无工序版本 `BOM-ASSY-X1-002`，通过 `Sales Order Item.bom_no` 记录选用关系 | S2。复杂多层 BOM、替代料、自动合单采购仍归 `BOM-01`，等客户确认口径 |
| LM92-03 | 分角色执行时原生单据用 `insert(ignore_permissions=True)` 提交（POC 角色画像未逐一配置每个原生 DocType 的 submit DocPerm），仅以 `frappe.set_user` 记录真实 owner | S1，正式上线前需按最小 DocPerm 收紧，并复测各岗位在原生 Desk 的提交权限 |
| LM92-04 | `Production Plan` 在新订单链路中未使用；概览只展示实际存在的原生单据，不虚填 | S2。若客户要求按计划自动下单，再评估 Production Plan → Material Request 自动化 |
| LM92-05 | 财务金额在 `order_summary()` 中对非 Accounts/System Manager 角色剔除（含单据行 `grand_total`），但原生 Desk 的表单权限仍由 ERPNext 自身控制 | S2。上线前需核对原生 Sales Invoice / Payment Entry 的角色权限是否与概览口径一致 |
