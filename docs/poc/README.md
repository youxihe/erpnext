# ERPNext v16 中文轻制造 POC — Workbuddy 入口

## 用户目标
在 D:\ERP\erpnext 基于 fork 源码完成：①隔离安装与初始化；②默认简体中文；③符合国内 PC 左侧菜单/右侧工作区的简洁界面；④创建生产、耗材、零部件、服务四类订单，尤其生产订单完整生命周期真实 UAT。完成后由用户实际打开浏览器体验，决定是否继续选型。

## 仓库/工作区
- GitHub: https://github.com/youxihe/erpnext
- POC branch: poc/erpnext-cn-manufacturing-20261026（从 version-16 16.52.1 派生）
- Windows 源码: D:\ERP\erpnext；工作区根：D:\ERP
- 这个仓库是 ERPNext **App 源码**。Frappe、Bench、数据库、Redis、后台服务另需安装；不能将仓库等同于完整独立运行项目。
- 本 POC 优先 Docker Desktop + WSL2 + 官方 frappe_docker 的 development/可自定义 app 方案。若 Windows 卷挂载体验差，使用 WSL2 Linux 文件系统开发副本，并明确与 D:\ERP\erpnext 源码的同步和提交路径。
- 不使用官方 pwd.yml 一次性 demo 替代真实开发环境；其限制会妨碍自定义订单字段、菜单与自有扩展应用的持久化验收。
- 版本必须对齐：ERPNext v16 16.52.1（当前基线） + Frappe 16 满足该应用依赖 + Python 根据 pyproject.toml 要求（当前 >=3.14）。**不要**使用 fork 默认 develop/v17 作为本期 POC。
- 先看本机已有 Docker/WSL2/Bench/端口情况，别覆盖 D:\ERP\ai-erp / JSH ERP 和 OpenClaw 运行态。
- 样本、最终验证和可复测操作见 docs/poc/TEST_DATA.md、docs/poc/UAT.md。

## 执行顺序（单 Agent 串行）
- POC-00 环境审计/版本锁定：docs/poc/tasks/POC-00.md
- POC-01 安装/初始化：docs/poc/tasks/POC-01.md
- POC-02 默认简体中文：docs/poc/tasks/POC-02.md
- POC-03 国内 PC 菜单：docs/poc/tasks/POC-03.md
- POC-04 四类订单基础/样本：docs/poc/tasks/POC-04.md
- POC-05 生产完整生命周期：docs/poc/tasks/POC-05.md
- POC-06 负例/复测/用户交接：docs/poc/tasks/POC-06.md

所有工作必须更新 docs/poc/TASKS.md 状态表；一个任务完成并有证据才能转下一个。明确缺口填 FAIL/BLOCKED，**不允许为了凑演示成果直接伪造数据/库存状态**。

## 可验证的目标，不是已完成承诺
一个用户无需打开英文后台、无需知道 ERPNext 工厂级术语，在左侧导航里找到客户销售、设计生产、采购、库存、交付、财务、报表。用户能自己从四种订单看到相应生命周期，并点击生产订单追溯真实 BOM、工单、任务、领料、成品、交付和成本。复杂度过高或不可简化之处要原样暴露并记录，以支撑 ERPNext vs JSH 的真实选型。

## 交付工件
- 本地地址和可登录测试账号（密码通过本机安全渠道交付，绝不 Git 提交）。
- Docker/Bench 运行与重启说明、实际版本 SHA、所用数据库和端口、安装可复现性。
- 中文与菜单配置的可重复导入方法（不只截图或只存在数据库的点选修改）。
- 测试数据/订单编号列表、链接和实际单据状态、库存/成本前后变化。
- UAT PASS/FAIL 与后续核心定制工作量/适配风险，以及推荐保留或放弃 ERPNext 的理由。
