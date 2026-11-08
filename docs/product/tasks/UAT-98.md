# UAT-98 — 为人工全链路验收准备全新独立 Site

状态：TODO。只准备环境，不自动宣告真人验收通过。

## 为什么不清现有 d.urlxl.cn
线上存在旧测试订单、PO、PR、WO、SE、取消单据、在制仓余料、公开演示历史和企微模拟配置。旧备份只验证过文件与行数，没有在独立数据库完整恢复。ERPNext 虽提供 Delete Company Transactions，仍可能遗漏自定义 Project/Task 或破坏历史依据。因此不得原地清空。

## 工作步骤
1. 保护本地 Git 未提交变更，读取当前产品分支、线上应用版本与发布记录；检查 MySQL8 兼容补丁、服务器容量、创建新库/用户权限、现有 Site/DNS/SSL 配置。任何资源不足先报告 BLOCKED，绝不能借机清理旧站。
2. 保留 d.urlxl.cn 及所有旧数据库、Stock Ledger、GL、单据、附件、用户绑定；先完成全套旧站数据库+文件+应用的备份，并在隔离库或隔离容器中验证真实可恢复，不以 dump completed 或表数一致代替恢复演练。
3. 用独立数据库、新 Site 安装与产品分支兼容的 ERPNext v16 + Frappe v16 + 当前 cn_mfg_poc（记录 Git SHA），执行兼容补丁/迁移、导入中文菜单、角色、用户权限、业务类型、九阶段 Project Template、Sales Order Item 的本单 BOM 确认字段、共用业务 API。真实企业微信密钥与旧 Mock 身份绝不复制；新站外网必须访问受限，给用户独立账号密码并安全交接。
4. 从配置/脚本导入虚构 Company（CNY）、财政年度、科目表、成本中心、客户、供应商、物料分类/UOM、原料/WIP/成品仓、四类订单所需 Item 与 BOM。只复制真实需要的配置和主数据，严禁复制任何老 Sales Order、MR、PO、PR、WO、SE、DN、发票、Payment、业务 Project/Task、GL/SLE/库存。原生模板 Task 可以保留。
5. 在没有业务交易时先核对 Item/Company/Stock Settings 的 Valuation Method 为 Moving Average；再用 Stock Reconciliation（Purpose=Opening Stock）录入虚构期初：RACK 原料仓 1件，估值100元/件；SENSOR原料仓10件，80元/件；FASTENER原料仓30件，2元/件；WIP/成品均零。不得用直接改 Bin/Stock Ledger 或已发生交易后切换方法；金额以及仓库真实名称可记录映射。
6. 记录启动基线：新 Site/DB/版本、每种 DocType 业务单据 0 张、起始 SLE 和 GL（仅允许期初凭证）、Bin 各仓数量与价值、Stock Ledger 与财务账户是否一致、各角色菜单及权限；验证 Site 重启与备份恢复。公网无任意 Mock 选用户越权。
7. 产出 docs/product/evidence/UAT-98.md，写可访问 URL、用户安全凭据交付方式、部署脚本及配置重放方式、真实恢复演练、库存/金额初始快照、已解决问题和阻断；最后标 READY_FOR_USER_UAT 而非 UAT-99 PASS。

## 禁止事项
没有用户新的明确批准不得对 d.urlxl.cn 运行 Delete Company Transactions、SQL DELETE/TRUNCATE、Stock Reconciliation 清零、bench reinstall/drop-site；不得让自动化程序代替用户逐单提交并声称完成验收；不能在 Git 提交密码、Token、Secret。新站无法建立就如实标 BLOCKED。
