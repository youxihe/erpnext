# FLOW-97 — 多订单集中采购与订单级物料追溯

状态：TODO。工作分支：product/erpnext-wecom-ai-v1-20261029。
用户核心疑问：SO 00001、SO 00006 使用相同成品 ASSY-X1 / 同类 BOM，采购申请、采购订单、入库、原料领用究竟怎么绑定？两单共同采购会怎样？

## 核心模型（Workbuddy 必须遵守）
- BOM 是产品的制造配方，同一个 BOM 多个 SO 可复用。BOM 共用不等于 PO/PR 共用。
- 需求与采购：Sales Order Item → Production Plan（可合并多单，来源子表 Production Plan Item Reference）→ Material Request Item → Purchase Order Item → Purchase Receipt Item → 共用原材料仓。
- 实物领用：Sales Order Item → Work Order（sales_order / sales_order_item / bom_no / production_plan）→ Stock Entry（work_order）→ Manufacture 成品入库 → Delivery Note Item（against_sales_order）。
- 采购入公用仓后，库存属于该物料和仓库，不会自动锁定某张 SO。未经实际库存预留/分配或批次追踪，不可宣称某个 PR 的 2 件实物归 SO00001。应该展示采购需求来源、到货、某工单实际领了多少三个不同事实。
- 已核对 ERPNext v16 字段：Production Plan.prod_plan_references 保留源 SO Item（包括合并计划）；Material Request Item.production_plan / sales_order / material_request_plan_item；Purchase Order Item.material_request_item / material_request / production_plan / sales_order；Purchase Receipt Item.purchase_order_item / purchase_order / material_request_item；Work Order.sales_order / sales_order_item；Stock Entry.work_order。无引用字段的手工采购不可能反推真实订单来源。
- 当前自有 App order_execution._linked() 主要按子表 sales_order 直接查 MR/PO/PR，可能漏掉 Production Plan 汇总采购。当前 order_summary() 给每个订单分别展示相同 Bin 的完整现存量，而 materials_shortage() 另按交期模拟分配同仓库存；口径需要明确，模拟分配≠正式预留。

## 第一阶段 FLOW-97A：线上只读事实审计，最优先
1. 安全检查本机未提交改动，fetch 目标分支；确认线上 Site 与当前版本。用已授权的只读查询/ERPNext UI，不修改或提交现有线上单据。
2. 对 SAL-ORD-2026-00001 和 SAL-ORD-2026-00006 分别核对产品行、bom_no、custom_bom_confirmed、提交状态、Production Plan Item Reference、Material Request Item、Purchase Order Item、Purchase Receipt Item、Work Order、Stock Entry、Delivery Note。
3. 输出逐项真实链接表：源 SO + 行 → 目标 DocType/单号 + 行 → 数量 → 状态/docstatus → 真实引用字段 → 直接引用/间接引用/仅同 SKU 无法证实。回答两个订单是否同计划、是否有共用 PO/PR、分别真正领料多少。如历史 00001 无来源链，明确写不存在/未找到，不能以共用 BOM 冒充共用采购。
4. 检查现有订单执行概览是否遗漏了间接采购来源和共享库存；区分缺 UI 与缺基础来源数据。写 docs/product/evidence/FLOW-97A.md；审计完成后再做 B。
5. 若线上没有合并采购样本，可在独立 POC site 造两笔测试 SO、一张合并的 Production Plan、一或多张 MR 及一张汇总 PO/PR，真实验证标准原生关系；不能擅自在 d.urlxl.cn 制造过账。

## 第二阶段 FLOW-97B：尽量靠 ERPNext 原生字段补小型双向视图
1. 在 /order_execution 增加“物料需求及采购履约”按订单行/材料展开：本单 BOM 需求、原生计划/申请来源、相关 PO Item、PR Item、已采购/已收货、对应 Work Order 已领/已耗。每个数字都能点击真实原生单据与源行；未能证明的关联标“来源不可证实”。
2. 给采购角色增加简洁“集中采购来源”查询：从一张 PO 的物料明细追溯对应 MR / Production Plan / 各 SO 需求及数量；同一 PO 可从多张 MR 拉入多个明细行。采购入库从 PO Item 关联到 PR Item。反向 SO 也能找到此 PO 的相关行。
3. 如果采购把多个 MR 对同一 SKU 的需求压成 **单个 PO Item**，原生 material_request_item 为单值，不能一行直接映射多笔 MR Item；不要偷用一个销售订单号填满整笔采购。先提供“一个 PO 多来源明细行”的轻量原生方案；若客户坚持合并成一行且要按 SO 定量分摊，记录需求分配表建议，交用户评估后再开发。
4. 单订单当前可用库存是共享 Bin，不应每张 SO 都当独占的可用数量；如果按交期模拟分配需明确显示“估算/未预留”，本单已领料必须按其对应 Work Order Stock Entry 汇总。采购入库已反映在 Bin 中，不能二次扣减。
5. 区分草稿/已提交/取消、部分收货、重复 MR、不同仓库与数据权限；不可通过 SKU/时间强行推定采购来源。订单财务金额须按实际角色过滤。全程不要改标准库存账、总账或制造过账规则。
6. 先跑本地合并采购两 SO 用例、权限和原四类订单回归，再按现有发布规范备份部署 d.urlxl.cn；线上验证优先使用只读关联和已有订单，不破坏既有记录。

## 最终验收
- 用户从 SO00001 和 SO00006 都能看到实际存在的需求、采购、入库及领料路径，没有的明确说明；不能把相同 BOM 当成采购关联。
- 同一张 PO 承载两张订单需求的场景，采购/销售双向能看到来源与各自数量；部分采购入库、领料、取消对数值正确。
- 用真实角色验证不能越权查别人订单或财务金额；报告给出原生单据号、来源字段、页面入口、仓库数量差异和未支持的边界。
- Git 记录 docs/product/evidence/FLOW-97A.md、FLOW-97B.md，更新 QUEUE 的 LOCAL_PASS / ONLINE_PASS，不得只写 PASS。
- 不做复杂 APS/MRP、正式库存预留、采购费用分摊、MES 报工及物料逐件追踪。
