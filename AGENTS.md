# AGENTS.md — ERPNext 中文轻制造 POC（2026-10-26）

本文件只适用于 youxihe/erpnext 的 ERPNext 验证分支。进入工作前必须先读 docs/poc/README.md、docs/poc/TASKS.md、docs/poc/UAT.md；按任务号严格顺序执行。用户使用 Workbuddy，Windows 工作区 D:\ERP，源代码 D:\ERP\erpnext。

## 项目目标与业务事实
本轮只验证 ERPNext 是否能够作为**国内中小企业订单驱动型轻制造 ERP** 的底座；不进行 JSH ERP 正式迁移，不开发企微/H5/机器人。
四类销售订单：
- 生产类：销售单→产成品BOM→缺料及采购→工单/车间任务→生产领料→完工入库→销售交付→开票/收款追溯。
- 耗材类：销售单→库存或采购→直接出库。不得触发 BOM/生产工单。
- 零部件类：销售单→库存或采购→直接出库。不得触发 BOM/生产工单。
- 服务类：非库存服务项目；仅记录服务履约，不自动产生库存扣减/生产任务。
明确排除原料合成药水/MIX、复杂 MES、APS、重 CRM、税控对接、企微应用和全新 Vue 前端。

## 分支、环境与安全
- 选型基线：本 POC 分支由 ERPNext version-16 的 2026-10-22 版本 16.52.1（base SHA ade850bbd6a7412e9994a9637d2c5c713771632a）创建；原 fork 默认 develop 属于 ERPNext 17 开发线，禁止直接混用 develop、version-16 的 Frappe/ERPNext。
- ERPNext 是 Frappe 应用源码，不是把仓库下载到 Windows 就能直接启动的服务器。必须使用独立 Bench + 兼容 Frappe + MariaDB/Redis 等完整环境。Windows 推荐 WSL2 + Docker Desktop + 官方 frappe_docker **可自定义 App 的开发环境**。一次性 pwd.yml 不可作为验收环境（不能正常安装自有 App）。
- Python 要按所选版 pyproject.toml 的 requires-python 核对；v16 当前声明 >=3.14，Frappe 要满足 >=16.50.0,<17.0.0。运行时安装命令应以当时官方文档和实际镜像/依赖为准，不要猜。
- 所有服务和数据库与 D:\ERP\ai-erp/JSH ERP、本机 OpenClaw、其他项目隔离；先排查端口冲突，优先仅监听 localhost。不得清理任何未知 Docker volume、MySQL 库或既有工作目录。
- 密码、Token、密钥只存本地忽略文件；Git 不提交真实口令、session、敏感数据；不能把测试默认口令公开部署到公网。
- 优先标准 ERPNext/Frappe 配置（Workspace、Role、Custom Field、User、Item、BOM、Work Order、Job Card、Stock Entry），新增需求尽量独立 Frappe custom app/fixtures，不批量改上游核心。
- 真实提交采购入库/销售出库/生产过账仅限新建的隔离 POC site，必须验证是测试数据；严禁对正式系统执行。

## 工作规则
1. 只做 TASKS.md 中第一个未 PASS 的任务；完成后留下可重复操作脚本/配置、验收记录、问题和 Git 提交，再认领下一项。前置任务 BLOCKED 不得绕过。
2. 在每项开始前先检查已有实现，严禁盲目重建/重置站点、容器、数据库；脚本要可重复运行，尽可能幂等。
3. 每项状态只允许 TODO / IN_PROGRESS / PASS / BLOCKED；PASS 必须有证据和复测方式，不得仅凭生成代码或网页 200。
4. 遇到平台权限、环境资源、重要流程差异，报告问题和下一步，而不是模拟成功或编造单据编号。
5. 任务完成后更新 docs/poc/TASKS.md 状态和 docs/poc/UAT.md 实际信息（URL、版本、单号、PASS/FAIL）；提交并 push 到此 POC 分支。不要向 upstream frappe/erpnext 发 PR，也不要自动合到默认 develop。
6. 最终给用户一个在本机浏览器就能实际登录验收的中文演示环境；交付后先停止新增功能，等待用户体验反馈。

## 必须核查的参考
- https://github.com/frappe/frappe_docker
- https://docs.frappe.io/framework-git/getting-started/installation
- https://docs.frappe.io/erpnext/system-settings
- https://docs.frappe.io/erpnext/production-plan
- https://docs.frappe.io/erpnext/work-order
- https://docs.frappe.io/erpnext/job-card
