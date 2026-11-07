# 统一导航适配调研与原型（2026-11-07）

## 需求

国内用户习惯「顶部深色一级模块 + 左侧浅色二级菜单 + 右侧内容区」的一体化后台布局（参考截图样式），
而 Frappe v16 Desk 是「Apps 桌面 → Dock 模块 → Sidebar 侧栏 → 卡片工作区」的西式结构，模块切换层次深、入口分散。

目标：所有业务场景在一个统一导航里，且仍操作同一套 ERPNext 真实数据。

## GitHub / 社区调研结论

调研时间 2026-11-07，本环境版本 Frappe 16.53.0 / ERPNext 16.52.1。

| 方案 | 形态 | 版本/活跃度 | 能否满足「顶部一级 + 左侧二级」 | 备注 |
|---|---|---|---|---|
| **Frappe v16.50+ 原生导航**（官方） | Apps → Module(Dock) → Sidebar → DocType/Report/Workspace | 官方，v16.50 起 | ❌ 仍是左侧三层 | 官方明确 Desktop Icon 网格正在退役，未来方向是 Apps 屏 + Dock + 模块侧栏。可配置自定义侧栏，但不能改成顶部一级布局。[文档](https://docs.frappe.io/framework/user/en/desk/navigation/desktop) |
| **Solvronix Desk 3.0「Workspace Classic」** | 顶部菜单栏**替代**侧边栏 + App 首页 + 表单白卡 | MIT，34 stars / 50 forks，最近提交 2026-10-30 | ⚠️ 只做顶部单层，**没有左侧二级** | 最接近的成熟开源方案。明确支持 Frappe v16 全系（v16.0–v16.50+，含 v16.50 Dock 导航）；可按用户/角色/公司/全站启用、随时切回、升级不丢布局；不改业务逻辑。[仓库](https://github.com/Solvronix/Solvronix-Desk) |
| **sidebar_menu**（aryacahil） | 自定义全局侧边栏，拖拽分组，独立于 Workspace | MIT，14 commits | ❌ 只有侧栏 | 适合重排左侧菜单，不改布局结构。[仓库](https://github.com/aryacahil/sidebar_menu) |
| **SlimDesk Navigator**（mohsinalimat） | 60px 常驻细侧栏，跨模块不丢上下文 | v15/v16+ | ❌ 只有侧栏 | 解决的是「模块间来回跳」，不是顶部一级。[仓库](https://github.com/mohsinalimat/v16_slimdesk_navigator) |
| **Enhanced Sidebar**（ibrahim317） | 自定义链接 + 分组 | MIT，2025-12 | ❌ 只有侧栏 | 论坛回复指出 v16 已原生支持按 workspace/module/app 自定义侧栏，该插件主要面向 v15 |
| **frappe_desk_theme**（dhwani-ris / Blaze） | 配色、字号、隐藏侧栏、登录页 | MIT | ❌ 只改视觉 | 不动导航层级 |

**结论：GitHub 上没有专门做「国内 Ant Design Pro 式 顶部一级 + 左侧二级」双层布局的成熟 Frappe 插件。**
最接近的是 Solvronix Desk 3.0，但它用顶部栏**替代**侧栏，形态仍不同；且它是第三方 app，需要
`bench get-app` → `install-app` → `bench build`，会改变站点资产，与本阶段「零侵入、不影响现有环境」的约束有冲突。

## 已交付：零侵入统一导航原型 `/cn_portal`

地址：<http://127.0.0.1:18000/cn_portal>（未登录自动跳登录页并回跳）

- 顶部深色一级：工作台 / 客户与销售 / 设计与生产 / 采购管理 / 仓库管理 / 物流交付 / 财务管理 / 经营报表 / 基础资料 / 系统设置
- 左侧二级：直接读取现有 `Workspace Link`（含 Card Break 分组），**与 PC 原生 Desk 共用一份配置**
- 角色过滤：复用 `Workspace.roles` —— 赵经理 10 个模块 / 86 项；王明 5 个；李工 3 个；张工 5 个
- 内容区：同源 iframe 打开原生单据/报表页面，注入样式隐藏内层 Dock/Sidebar，避免双套导航
- 首页：四个关键单据计数 + 十个模块入口卡片
- 右上：原生 Desk / 企微 H5 / 全屏；内容区工具条：返回首页、新窗口打开、显示/隐藏原生导航

**实现文件**（仅新增两个文件，无 DocType、无 migrate、无数据写入）：
- `poc/apps/cn_mfg_poc/cn_mfg_poc/www/cn_portal.py` — 角色过滤 + 菜单推导
- `poc/apps/cn_mfg_poc/cn_mfg_poc/www/cn_portal.html` — 布局与交互

**已验证**：
- 4 个账号登录均 200，未登录 301 跳登录页
- 菜单按角色正确过滤，无残留模板变量
- 点击「客户与销售 → 销售订单」iframe 加载成功，内层原生导航被隐藏，列表铺满内容区（截图见 `evidence/cn-portal-page.png`）

## 后续三条路线（待定优先级）

| 路线 | 工作量 | 效果 | 风险 |
|---|---|---|---|
| **A. 原型深化（建议先试）** | 小 | 完全贴合国内布局；补：登录后默认跳门户、`app_include_js` 给所有原生页面加「返回统一导航」入口、菜单配置化、移动端适配、多主题 | 低，仍只在自有 app 内 |
| **B. 装 Solvronix Desk 3.0** | 中 | 官方市场可用的成熟主题，顶部菜单栏、白牌、命令面板、暗色模式 | 中：需验证 16.53（其声称 v16.50+）、bench 装 app + build 会改站点资产；且**没有左侧二级** |
| **C. 自研 Frappe app 改 Desk 布局** | 大 | 布局完全可控，可长期随 v16/v17 演进 | 高：需跟 Frappe 前端路由/Dock 机制深度耦合，升级易碎 |

建议路径：先按 A 让业务用户实际用两周，收集「哪些菜单最常用 / 是否需要常驻顶部栏」，
再决定是引入 B 还是投入 C。若选 B，先在独立分支与独立 Site 验证 16.53 兼容性，确认可卸载回退后再上主环境。

## 参考链接

- Frappe v16 发布说明（新桌面 UI）：<https://frappe.io/blog/engineering/announcing-version-16>
- v16.50 导航层级讨论：<https://discuss.frappe.io/t/frappe-erpnext-v16-50-the-future-of-desktop-icons-and-desk-navigation/165108/1>
- 官方 Desk 导航文档：<https://docs.frappe.io/framework/user/en/desk/navigation/desktop>
- Solvronix Desk：<https://github.com/Solvronix/Solvronix-Desk>
- v16 如何给 Workspace 建菜单（社区讨论，可见文档滞后）：<https://discuss.frappe.io/t/how-to-create-a-menu-for-a-workspace-in-frappe-version-16/159223/1>
