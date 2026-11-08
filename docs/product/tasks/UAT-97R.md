# UAT-97R — 线上测试角色精简、中文岗位档案与明显的测试账户名称

> 状态 TODO。用户正在 https://d.urlxl.cn 在线手工测试；此任务针对**现有测试站点**，与 UAT-98 独立新 Site 任务无依赖。完成后在线验证，不清空订单/库存。
> 首要目标：用户看到账号就知道岗位，并能通过 A/B 对照测试菜单权限和数据隔离；不是从数据库把 ERPNext 系统角色直接删掉。

## 1. 业务角色（本期唯一对用户展示和维护的 7 个中文 Role Profile）

| 中文岗位档案（Role Profile） | 现有主账号（保留 Email/ID） | 推荐显示名 User.full_name | 主要权限/业务 |
|---|---|---|---|
| 经营管理 | zhaojingli@erpnext-poc.localhost | 经营管理-A-赵经理 | 公司经营/订单进度/授权报表；如现有含 System Manager 必须单独审计并说明，不默认当成普通管理权限 |
| 销售业务 | wangming@erpnext-poc.localhost | 销售-A-王明 | 客户报备、四类销售订单、交付进度 |
| 设计生产 | liugong@erpnext-poc.localhost | 设计生产-A-刘工 | BOM、生产工单、Project/Task 模板与分派 |
| 采购业务 | chengong@erpnext-poc.localhost | 采购-A-陈工 | 物料需求、集中采购、PO 与采购来源查询 |
| 仓库管理 | zhanggong@erpnext-poc.localhost | 仓库-A-张工 | 采购入库、原料/WIP/成品仓、领料、完工入库、交货单 |
| 车间执行 | ligong@erpnext-poc.localhost | 车间-A-李工 | 本人九阶段生产任务状态/备注；不直接过账、不读敏感价格 |
| 财务业务 | zhoukaiji@erpnext-poc.localhost | 财务-A-周会计 | 销售/采购发票、应收应付、收付款、财务报表 |

- **系统管理员**单独保留原生 `Administrator`，不作为正常业务角色测试，更不能删除/改账号 ID；其界面可标注“系统管理员”，但后端仍为 Administrator。
- 第一版没有独立“物流、质量、销售经理、采购经理、仓库主管、财务主管”岗位档案：物流发货先由仓库/销售协同，质量/复杂流程以后按需要开，别提前拆成 20 多种中文岗位。
- Role Profile 是**聚合原生 Role 的中文业务模板**。例如销售业务可包含 Sales User 等必要原生角色；仓库可含 Stock User 等；经营管理与设计生产根据现有已验证能力选择最低限度的原生 Role/DocPerm。不要根据本表凭空复制所有 Manager 角色给用户。
- 官方 ERPNext Role Profile 本来就是用来把一个业务岗位所需的多个 Role 绑定为一套配置，不要求把 ERPNext 内部英文 Role 改名成中文。

## 2. 原生角色（技术标识）清理原则 — 不能直接批删
1. 先导出当前线上全量 Role / Role Profile / Has Role / User Permission / Custom DocPerm / Workspace Role / 角色接口映射，保存脱敏证据和完整备份。记录哪些 Role 属于 ERPNext/Frappe 内置，哪些是自定义、哪些未被引用。
2. **保留并不重命名**所有 ERPNext/Frappe 标准技术 Role，如 Sales User、Sales Manager、Purchase User、Stock User、Manufacturing User、Accounts User、System Manager、All/Guest/Desk User 等。cn_mfg_poc 当前 Workspace 按这些英文标识判定显示权限，代码里也有 has_role/role map；重命名或删除会损坏权限。
3. 仅从七个普通测试账号上撤销无关的**额外角色授权**；任何移除前先以角色登录态验证 create/read/write/submit/cancel 需求。不要无意撤销管理员的 System Manager 权限造成锁死。
4. 仅对确实为旧 POC 创建、无用户绑定、无 DocPerm/Workspace/Role Profile/自有代码/企微映射引用的**非标准自定义 Role**，在完整报告中列举后可安全删除；不满足证据则保留并隐藏于“业务岗位”入口，不得做模糊匹配批量删除。
5. 让普通业务测试用户只看到七个中文岗位带来的菜单和授权；管理员在 ERPNext 原生 Role 列表依然可以看到众多技术 Role，这是底层框架正常现象。可以增加“业务岗位管理”入口只展示中文 Role Profile，**不能伪称已经删除所有标准 Role**。

## 3. 测试账号的名称与隔离用例
- **保留所有已有 User.name/email**，不修改、合并或重建这些用户；否则原 Sales Order.owner、Task 负责人、WeCom 绑定、审计日志、通知等可能失联。仅修改 First Name/Last Name/full_name 或系统实际影响头部用户名的安全字段。
- 显示名统一格式 **“岗位-A-姓名”**。在 `/cn_portal` 顶部、用户下拉/用户列表、`/production_board` 当前账号处尽量显示一致；如果原生 Desk 头像只取 User.full_name，优先直接复用，不做大规模前端重写。角色档案名称则只写“销售业务”等稳定中文名，A/B 是**测试用户标识**，不是独立 Role。
- 至少新增 1 个销售对照账户：`销售-B-对照`；至少新增 1 个车间对照账户：`车间-B-对照`。用户名/邮箱遵守站点唯一规范并由 Workbuddy 在本机安全配置生成，严禁借用真实企业邮箱；创建新账户不复制 Administrator/财务/其他角色。必要时测试仓库数据域，可追加 `仓库-B-对照`，但必须先具备不同仓库的合理权限隔离规则，不为了数量乱造用户。
- 销售 A/B 用同一个中文“销售业务” Role Profile，分别创建虚构客户/订单并测试可见性；**同角色并不自动意味着数据隔离**，若尚无按销售负责人、客户区域或公司权限划分的 User Permission/业务查询条件，记录 `DATA_SCOPE_GAP`，不能假装 A/B 看不到对方订单。不要未经用户确认就全局强加新的数据范围规则，阻断原生采购/交付协作。
- 车间 A/B 同 Role Profile，分派不同 Task，证明每人只能更新本人任务、查看自己负责的任务；跨账号修改返回 403/PermissionError，并证明 Project Task 与实际库存无自动过账关系。
- 经理是否能看到所有订单为单独授权行为，不用 Administrator 账户来证明业务经理权限。

## 4. 线上执行要求
1. 审计先行：列出当前 7 个现有业务用户的账号、User.full_name、Role Profile、Has Role、额外角色/数据域、Workspace，以及自有 API role checks；报告只留必要的脱敏标识，不泄露密码。
2. 在 d.urlxl.cn **只做角色/用户配置迁移和必要的显示层改动**；不删除任何已提交业务单据、数据库、库存、BOM、Project/Task、财务凭证或当前 Web/App/微信绑定。升级前备份数据库 + 站点文件，并留可回退的原角色/账号授权快照。
3. 角色档案、User.full_name、角色授权变更实现**幂等**，重跑不会产生重复角色/账号；如由 Frappe App migration/fixture 管理，避免以后部署把人工调整覆盖。保持已有用户密码不变仅供短期测试？**否：旧共用测试密码已被披露，必须轮换为独立强密码**，本地安全交付，不在 Git/聊天输出明文。为不同身份切换建议使用独立浏览器 Profile 或无痕会话，切换账号前 logout，避免 Cookie 混杂。
4. 至少使用 Administrator 和 7 个业务账号真实登录操作：岗位名显示、菜单精简、业务入口可达；Sales Order、BOM、MR、PO、Purchase Receipt、Stock Entry、Work Order、Delivery Note、Sales/Purchase Invoice、Payment Entry、Project Task 的 read/create/submit 权限按照岗位执行正/负例。禁止通过 `ignore_permissions=True` 模拟普通岗位。
5. 同角色销售 A/B 分别验证“菜单相同、账号不同、数据范围是否隔离”；同角色车间 A/B 分别验证本人任务。H5、机器人仍然使用用户身份的后端绑定，若是 Mock/本地环境应保留 REAL_WECOM_BLOCKED，不要通过头像名称猜测身份。
6. 部署后核验 /cn_portal、/desk、/production_board、/order_execution、/procurement_trace、/wecom_h5 原有入口可访问，BOM确认、销售订单→工单→领料/入库链不退化。
7. 记录角色变化前后差异、七中文 Role Profile 到原生角色的映射、用户登录账号 vs 显示名映射、去除/保留的授权原因、真实登录证据、跨账号数据负例、Git commit 与线上 SHA 到 `docs/product/evidence/UAT-97R.md`；更新 QUEUE 为 ONLINE_PASS 或 BLOCKED，并明确实际哪些数据范围尚未限制。

## 不做
- 不删除 ERPNext/Frappe 标准 Role、DocType、Workspace；不统一把底层 Role 改中文导致升级冲突。
- 不重做公司组织体系或生产角色复杂矩阵；不为测试角色清理而改变库存/财务实际过账数据。
- 不让同一账号通过改显示名伪装成多个角色；A/B 是两个独立账号，不是一个账号切换权限。
- 不让用户在聊天或 Git 里共享密码、Secret 或自动登录 Token。
