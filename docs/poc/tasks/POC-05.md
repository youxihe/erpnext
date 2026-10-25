# POC-05 — 生产订单完整生命周期（最高优先级业务验证）

## 目标
用**一张真实测试生产类销售订单**串起 ERPNext 原生 BOM、Production Plan、Material Request、Purchase Order/Receipt、Work Order、Job Card、Stock Entry、Delivery Note、Sales Invoice/Payment Entry；所有过账仅发生在隔离 POC 库。不能只截图单据列表就声称闭环完成。

## 唯一主样本
使用 docs/poc/TEST_DATA.md 的“设备装配 X1 × 2 台”，每台 2 个机架、1 个传感器、4 个紧固件。初始库存设定导致明确缺料；让物料需求、采购、生产领料有真实发生的理由。不做原料合成药水/MIX。

## 必须实际验证的步骤
1. 销售：创建客户、生产类型销售订单 ×2 台，录入承诺交期、价格和负责人并 Submit；真实订单号写 UAT。
2. 设计：建立标准 Item BOM（数量、单位、原料/可用性、Operation），确定是否能针对本次订单选择特定 BOM 版本并追溯；不同 BOM 版本不是一张可随意覆盖的草稿。不能证明订单专属 BOM 就标为产品差距。
3. 计划/采购：从这张销售订单建立 Production Plan；根据 BOM 展开原料和初始现存量计算缺口，用原生 Material Request → Purchase Order → Purchase Receipt 补货入库，保留单据之间的 reference。核对库存增加与在途数量变化；不允许仅凭手工把现存量直接改大。
4. 生产：根据 Production Plan 建 Work Order ×2 台，选择已批准 BOM、WIP 仓库、领料仓、成品仓；保留与原销售订单可核对的关系。
5. 任务：至少定义 2 个操作（例如“装配”“检验”）和真实测试 Workstation/Employee，产生对应 Job Card；指派人员、计划时间、实际开始结束、完成数量，记录迟延/进度状态。核对标准 Job Card 是否真的符合车间人员任务粒度，而非把所有任务当真实 MES。
6. 仓库领料：提交 Material Transfer for Manufacture / 对应 Stock Entry，核对原材料仓下降、在制品仓变化、工单领用记录；不能只变更工单状态。
7. 完工：提交制造完成的 Stock Entry(Manufacture)，产成品实际入库、WIP 物料消耗与成本可追溯，数量与 BOM/实际领料一致。若能实现，尝试分次完成 1 台 + 1 台。
8. 交付：基于原 Sales Order 建真实 Delivery Note，发出产成品 2 台（至少验证一次部分交付状态），成品仓库存下降，销售订单已交/未交数量正确。
9. 轻财务：基于销售订单/交付建立 Sales Invoice 与 Payment Entry 测试登记，核对已开票/已收款/余额；解释 ERPNext 原生财务单据可能正式生成会计分录，与用户所需纯台账之间的差异，不擅自实现税务模块。
10. 追溯/经营：销售员能够从订单找到 BOM、采购、生产工单、Job Card、领料、完工、交货、开票收款；管理者核对实际物料成本与预计 BOM 成本。若某一跳没有标准关系或页面入口，明确 GAP 并给最低改造建议。
11. 反向校验：记录本次主要物料初始库存、采购入库、领料、成品入库、交付后的最终数量和金额；任何过账失败留原因，不手工篡改终态充数。

## 验收标准
- 按真实单据执行，所有编号、提交状态、创建人、时间、来源与数量互相对应；库存不是模拟值。
- 至少 2 个 Job Card 的人员、计划/实际时间和完成数量可见。
- 有订单→生产→仓储→交付→财务真实链路，且 1 个关键缺料采购已发生。
- BOM/Job Card 对用户是否过于复杂、订单特定设计、材料预留、成本查看等形成逐条 **原生可用/需配置/需扩展/不支持** 结论。
- docs/poc/evidence/POC-05-production.md 与 docs/poc/UAT.md 写出操作记录、单据编号、真实差距。
