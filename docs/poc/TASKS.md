# Workbuddy 串行任务队列与记录

创建日期：2026-10-26。此表为 **计划**，尚不表示安装或开发完成。每次仅一项 IN_PROGRESS，前项不 PASS 不得自动往后。

| 序号 | 任务 | 状态 | 证据/提交 | 备注 |
|---|---|---|---|---|
| POC-00 | 本机审计和版本锁定 | **PASS** | docs/poc/evidence/POC-00-environment.md（commit d5bb7564） | 2026-10-26 完成源码/版本/隔离审计 |
| POC-01 | Docker/Bench 安装初始化及可重启 | **PASS** | docs/poc/evidence/POC-01-install.md（commit d5bb7564） | 2026-10-26 site erpnext-poc.localhost 可用 |
| POC-02 | 简体中文默认值及翻译验收 | **PASS** | docs/poc/evidence/POC-02-l10n.md（commit fd7b27c4） | 2026-10-26 8 处 zh 空翻译用 cn_mfg_poc patch 修复 |
| POC-03 | 国产 PC 菜单与角色入口 | **PASS** | docs/poc/evidence/POC-03-navigation.md（commit ebb5eb21） | 2026-10-26 10 个角色门控中文工作台 + block_modules 屏蔽 36 模块，3 角色实测差异 + 10/10 后端权限探针全过 |
| POC-04 | 四类型订单与样本配置 | **PASS** | docs/poc/evidence/POC-04-orders.md（commit d556fcb6） | 2026-10-26 四类订单 SAL-ORD-2026-00001..04 提交；耗材/零部件交货真实扣减 50→40、8→3；服务类 0 工单 0 库存 |
| POC-05 | 生产订单完整业务单据与库存生命周期 | **PASS** | docs/poc/evidence/POC-05-production.md | 2026-10-26 生产计划→缺料采购→工单(2 工序)→Job Card→领料→完工→交付→开票→收款全链路；成品 720 元/台与 BOM 勾稽一致，应收 0 |
| POC-06 | 负面测试、复测、交付 | TODO | 待执行 | 依赖05 |

## 状态和交付规则
- 每项需要写入：实际开始结束日期、环境/提交 SHA、测试步骤、实测单号/URL、截图或日志路径、PASS/FAIL 原因、未解决事项。
- 任务文件写清目标与具体 DoD，不允许只把文档改为 PASS 却无服务器/ERP 页面的实际执行。
- 配置若仅存在数据库，必须另存可复现的导入脚本或 fixtures 并验证重新导入流程；敏感参数用环境模板，数据测试与系统配置分离。
- 任何步骤失败，不得跳过更改数据状态；可修复后重试，或设 BLOCKED 记录需用户介入的最小问题。
- 不要求整合所有功能到新前端，也不允许为这轮 POC 构建企微机器人。
- 每个任务执行完将源代码、脚本、文档、证据提交到本 POC 分支，push 后留下 commit SHA。
