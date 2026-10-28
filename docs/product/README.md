# ERPNext × 企业微信 H5 × AI 机器人 — 产品化 V1

## 2026-10-29 确认目标
客户能够同时使用：
1. 中文 ERPNext PC 端完成主要销售/设计/采购/仓库/生产/财务/管理流程。
2. 企业微信自建 H5 完成最常用移动操作。
3. 企业微信 AI ERP 机器人通过自然语言/Excel 对相同 ERPNext 数据进行查询、草稿、确认与写入。

验收核心不是把 ERPNext 全部细节打磨完，而是 **三入口、同一 ERP 数据、可操作的核心业务模块**。

## 不重复已有 POC
仓库：youxihe/erpnext
产品分支：product/erpnext-wecom-ai-v1-20261029
原 POC 分支：poc/erpnext-cn-manufacturing-20261026（保留）
已记录 POC-00 至 POC-06 完成：ERPNext 16.52.1 / Frappe 16.53.0、中文菜单、四类销售订单、BOM、生产计划、采购补货、Job Card、领料/成品入库、交付、收款。
之前本机入口：http://erpnext-poc.localhost:18000；仅为历史记录，实际运行状态以 Workbuddy BUILD-00 当下检查为准。
POC 现有扩展：poc/apps/cn_mfg_poc；本地隔离 Docker/Bench 与 D:\ERP\poc 关联。
原 JSH/OpenClaw 项目：youxihe/ai-erp、F:\aierp-openclaw，可借鉴已有企微 API 模式机器人、身份绑定、Excel 预览/确认链路，但不得直接修改现有运行时。

## 文件与执行顺序
- AGENTS.md：统一执行规则（新阶段覆盖旧 POC 暂缓企微的限制）。
- docs/product/QUEUE.md：**完整任务与验收，Workbuddy 只需要读这个并逐个执行**。
- docs/product/ARCHITECTURE.md：架构、数据与安全边界。
- docs/product/ACCEPTANCE.md：最终三端验收矩阵。
- docs/product/BACKLOG.md：细节问题和用户待定优先级。
- docs/poc/**：历史 POC 文件和代码证据，不再把旧任务当活跃队列。

工作顺序：
BUILD-00 现状复核 → BUILD-10 ERP PC 大模块补齐 → BUILD-20 共用 API → BUILD-30 企业微信组织身份 → BUILD-40 H5 → BUILD-50 机器人查询 → BUILD-60 机器人客户报备/Excel 写入 → BUILD-70 三端联合验收。

每项任务结束后需提交到本产品分支，记录实际运行版本、页面/接口、业务单号、权限负例与 PASS/BLOCKED；满足条件就继续下一项。遇到企微可信域名或管理员配置缺失，只问用户最少必要资源，不把 Mock 标 REAL PASS。

## 范围原则
**本阶段先补大模块，不钻细节。**
已有原生订单/采购/制造/财务尽量复用。新增开发优先客户报备、我的车间任务、角色工作台、统一业务 API、企微同步与身份、H5 常用操作、AI 查询与受控写操作。
发票取消特殊规则、人工成本、复杂 APS、复杂税控、报表润色等先记 BACKLOG；危及真实数据安全的操作必须先限制权限。