# RELEASE-95：BUILD-90～94 Review Fix 与 d.urlxl.cn 线上测试发布
> 创建于 2026-11-08。**任务状态：TODO，尚未部署**。负责人：Workbuddy。
> 仓库：youxihe/erpnext；部署源：product/erpnext-wecom-ai-v1-20261029。
> 创建时已审阅 HEAD：e1b87ec766c1f9f61d7d0bfdb29de1de42d1a2f2；部署时必须核对最新 HEAD。

## 0. 发布决策
现有 BUILD-90～94 的本地功能和测试报告足够支持**准备测试发布**，但发布前存在以下不可省略的风险核查。用户已授权**线上测试环境**升级与验收，不代表授权重置数据库、覆盖其他服务或真实客户正式系统。

Workbuddy 本地报告：BUILD-90 7/7、BUILD-91 27/27 和 HTTP 24/24、BUILD-92 26/26 和 HTTP 44/44、BUILD-93 27/27 和 HTTP 18/18、BUILD-94 12/12 + 27/27。验证的核心业务正确：生产 Task 全完成时 SLE 92→92，仓库正式 Manufacture 后 92→96，Delivery Note 后 97。这个数据只能证明**本地 POC**，不能等价于线上可用。

### P0-1 缺料计算重复扣减（修复后才可让采购使用）
在 `poc/apps/cn_mfg_poc/cn_mfg_poc/order_execution.py`：
- `order_summary()` 中缺料用 `max(0, required_qty - available_now - received_qty - issued_net)`。
- `available_now` 取当前 Bin 库存，正常已包含本次 `Purchase Receipt` 收货；`received_qty` 再次作为可用量扣减，会造成**重复计入已收货、低报缺料**。
- 不能只删除字段而忽略订单已完工、部分领料、多个订单共享仓库、不同仓库等问题。首期可给出受控的保守估算与明确口径；在没有预留关系时不能把“粗略缺料”当成最终采购建议。
- 加自动测试：例如需求 4、当前实际可用 2、历史已收到货 2、尚无领料时应仍缺 2；再测已有 WIP 领料、已完工订单、不同仓库和权限。修复后重跑 BUILD-92/93/94 回归并记录数量/明细。

### P0-2 真实业务人员单据权限必须实测（可能影响 UI 实用性）
- `docs/product/evidence/BUILD-92.md` 说明真实业务单据链在脚本里执行了 `frappe.set_user(岗位用户)` + `insert(ignore_permissions=True)`。这可以证明 ERPNext 流程在测试站点能提交，但**不能证明这些角色从 PC、原生 REST 或 H5 入口真的拥有相应 create/submit DocPerm**。
- 使用销售、采购、仓库、财务**真实登录态**至少测试创建销售订单 / Purchase Order / Purchase Receipt / Work Order 所需提交权限 / Stock Entry Manufacture / Delivery Note / Sales Invoice / Payment Entry。可按角色测试独立的最小典型操作，避免重复造完整一套订单。
- 如果标准 DocPerm 不满足，最小配置授权或通过明确受控业务 API 完成；测试读/写/submit 和越权拒绝，绝不能把所有账号都赋 System Manager 或共享 Administrator token。
- 把脚本模拟、REST 调用和 UI 实测分别标记，不可混用口径。

### P0-3 数据库迁移 / 站点兼容 / 备份
- `docs/product/BACKLOG.md` 的 LM94-01 明确记录线上 `d.urlxl.cn` 仍是 BUILD-80，并提到 **Workbuddy 本机** `poc/deploy/DEPLOY.local.md`、表名大小写补丁、`patch_mysql8_compat.sh`、`bench migrate`。
- 上述 `poc/deploy` 目录**不在当前 GitHub 产品分支**；不能假设 ChatGPT/GitHub push 能直接部署，也不能把未经审阅的本地脚本当成受控发布流水线。
- 在 Workbuddy 本地现场读取部署指引和脚本、确认实际 SSH/Compose/Bench Site、DB 版本，**保留现有云端数据库和附件**；先对数据库+files 备份并验证恢复策略；检查表名大小写、Custom Field/Project Template 是否和线上已有对象冲突、patch 是否幂等。
- 必须正确处理补丁与 migrate 次序，并记录真实输出。迁移时如报错，停止、诊断或回滚，不得反复重置/重建 Site。普通测试数据只在隔离测试站点写入。
- 部署自有 app 的生产任务 API、HTML 页面、fixtures 及适配器的受控版本；按现场需要进行 `bench migrate`、构建/清缓存、重启服务；**不要更新 ERPNext/Frappe 到 v17**。

### P0-4 公网测试安全底线
- 此测试环境曾在聊天中披露多账号共用密码：确认已轮换到独立密码，不在 issue/doc/log 写口令，避免 Administrator 公网直接反复试用。
- 真实企微尚未授权，线上测试 H5 如果处于 `mock_mode=1`，**必须阻止任意公网访客通过“选角色”冒充业务人员读取/写入**。允许使用真正的普通 ERP 用户登录做受控 H5/接口测试，Mock 登录与真实微信 UAT 严格区分。
- 机器人 API 不能共享管理员 Token 或将测试适配器 HMAC Secret 写入 Git。
- 本次不要求跑通真实企微信息，`REAL_WECOM_BLOCKED` 保持原样。

## 1. 执行步骤（门禁式）
1. 检查本地工作区脏文件与 Git HEAD；保护未提交内容，核对最新产品分支；完成 P0-1 与 P0-2；在本地 POC Site 重跑增量和旧四类型单据回归。
2. 查看线上 d.urlxl.cn 具体宿主/容器、数据库、版本、当前自有 App SHA 和存量数据；确认归属及备份恢复条件（P0-3）。必要时可先在同版本独立 Site 演练迁移。
3. 完成 P0-4 公网测试安全检查。若无法确保账号与 Mock 隔离，标 BLOCKED 并说明最小补救，不做外网升级。
4. 上述 gate 均通过后，以**最新经测试的产品分支 commit** 部署到 d.urlxl.cn，执行站点迁移/缓存更新/重启，保存版本和部署证据。
5. **线上** 用至少三种真实普通用户登录态复测：销售、仓库/采购、生产；财务也要核对收付款状态。新建独立测试整机订单或使用已存在的线上样本，不能把本地的 SAL-ORD-2026-00008 当成线上已存在。
6. 核对页面和行为：`/cn_portal`；`/production_board?view=mine`、`?view=order`；`/order_execution`；`/wecom_h5`。四类订单、九阶段任务、到期预警、BOM/缺料、原生生产领料→Manufacture→整机一次交货、财务状态；H5 更新任务后 PC 可见；任务状态更新不会触发库存；未授权用户拒绝；重复提交不重复过账。
7. 真实企微信息未就绪时，只能写“**HTTP / LOCAL/MOCK PASS，REAL_WECOM_BLOCKED**”；本轮不因此妨碍用户先体验 PC 的轻制造。
8. 按下方模板提交 Git 发布报告，更新 `docs/product/QUEUE.md` 的 RELEASE-95 为 `ONLINE_PASS` 或 `BLOCKED`，不能只写 PASS。

## 2. 发布验收报告模板（Workbuddy 创建）
输出 `docs/product/evidence/RELEASE-95.md`：
- 部署日期/时间、发布人、产品源 SHA、本地与线上对照版本；
- 线上 Site URL、ERPNext/Frappe 与自有 App 的运行 SHA（不暴露登录口令/数据库密钥）；
- 发布前备份标识、迁移补丁与 migrate 结果、回滚方法、部署操作摘要；
- 缺料修正前后对照（具体订单/物料/仓/需求/库存/缺料）；
- 真实各角色登录和 docstatus 权限测试；失权负例与操作截图；
- 线上 PC 地址、H5 地址与受保护访问方式；九阶段任务/订单概览可点击入口；
- 线上示例单据真实编号、Stock Ledger/Bin 数量前后变化、九任务完成与库存解耦证明；
- 线上未覆盖功能、真实企业微信 BLOCKED 的最小所需外部授权；
- 明确状态：`ONLINE_PASS` / `BLOCKED`，且要说明是否实际发布。**仅 Git 提交不代表已发布**。

## 3. 验收通过后用户重点看什么
从 `https://d.urlxl.cn/cn_portal` 进入，先查看订单执行概览（销售订单、BOM、采购、仓储、完工、发货）；再切到固定生产进度，看九阶段负责人/计划时间/异常与预警；再以车间普通角色访问 `/wecom_h5` 更新本人任务（受控模拟验收，不等于真企微）并回到 PC 验证一致。
