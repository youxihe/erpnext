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

## 内页宽度设置（2026-11-07，一次修复 + 一次补全）

### 第一版（`b3807b6b`）：只修了字段区

现象：表单页字段只占中间约 900px，左右各留约 235px 空白。根因不是 iframe 窄——
1600×950 视口下 iframe 宽 1380px、`.page-container` 1370px；是 Frappe v16 的
`.section-body { max-width: 900px; margin: auto }`，加上列 `max-width: 33.33%`，每列只剩 300px。
第一版只覆盖了 `.section-body`，因此用户反馈「没改全、看着别扭」。

### 第二版：按 DOM 实测把整张表单统一到一个宽度

在 BOM 表单 `BOM-ASSY-X1-001` 上逐层量过，Frappe v16 把**同一张表单的不同区块分别限宽并居中**，漏一处就错位：

| 区块 | 原生规则 | 第一版之后 |
|---|---|---|
| 折叠标题 `.section-head` | `max-width: var(--page-max-width)` = 900px + `margin:auto!important` | 仍 900px 居中，比铺满的表格左边缘缩进 235px |
| 字段区 `.section-body` | 同上（`body:not(.full-width)`） | 已铺满 1340px |
| 页脚评论/活动 `.form-footer` | `max-width: var(--page-max-width)` = 900px | 仍 900px 居中 |
| 活动条目 `.timeline-content` | `max-width: var(--timeline-content-max-width)` = 700px | 仍 700px |
| 子表格 `.form-grid` | `max-width: 100%` | 已铺满 1310px（与上面几块不齐） |

也就是「表格铺满、标题和评论区缩在中间」。另外左侧栏底部把 Administrator 的 46 个角色全平铺出来，
糊成一长串小字，也是观感问题。

**修法**：`stripCss()` 不再逐块打补丁，而是把 `--page-max-width` / `--timeline-content-max-width`
两个 CSS 变量与下列容器统一到同一个 `contentMax`：
`:root`、`.section-head`、`.form-section-description`、`.section-body`（含 `.std-form-layout` / `.form-dashboard-section`）、
`.form-footer`、`.after-save`、`.comment-box`、`.comment-input-wrapper`、`.new-timeline`、`.timeline-item`、
`.timeline-content`、`.form-grid`。
铺满时变量取 `100%` 而不是 `none`（`timeline.scss` 里还有一处 `width: var(--timeline-content-max-width)`，设 `none` 会让宽度失效）。
左侧栏角色改成「前 2 个 + 等 N 项」摘要，完整名单保留在 `title` 悬停中。

**两个设置位置，任选其一**：
1. 工具条「**内容宽度**」按钮：`铺满 → 1200px → 原生 900px` 三态循环，即时生效，选择存在浏览器 `localStorage`。
2. 源码 `www/cn_portal.html` 的 `DEFAULT_CONTENT_MAX`：`0` = 铺满（当前默认）、`1200` = 折中、`900` = ERPNext 原生。

实测（Administrator，1600×950，iframe 1380px）：

| 容器 | 修复前 | 修复后 |
|---|---|---|
| `.section-head` | x=235 w=900 | x=15 w=1340 |
| `.form-footer` | x=235 w=900 | x=0 w=1370 |
| `.comment-box` | x=250 w=870 | x=15 w=1340 |
| `.timeline-content` | max-width 700px | x=50 w=1305，max-width none |
| `.form-grid` | 1310 | 1310（不变，现已与标题对齐） |

回归 `18/18` 通过：BOM 标题/正文/页脚/评论框/时间线全铺满、全页无 900/700px 限宽残留、
三态（1200 / 900 / 铺满）一致生效且居中、列表页与 Lead 表单不受影响、1100px 窄视口无横向溢出。
日志 `evidence/cn-portal-width-full-verify.log`，脚本 `product/scripts/portal_width_full_verify.js`。
截图：`evidence/cn-portal-bom-before.png`（修复前）、`cn-portal-bom-top-fixed.png`、
`cn-portal-bom-bottom-fixed.png`（评论区/活动区）、`cn-portal-bom-900-fixed.png`、
`cn-portal-list-fixed.png`、`cn-portal-lead-fixed.png`、`cn-portal-narrow-fixed.png`。

**部署注意**：`D:\ERP\erpnext\poc\apps\...` 是 Git 工作副本，容器内 `/workspace/development/frappe-bench/apps/cn_mfg_poc/...`
来自独立 Docker volume，改完必须 `docker cp` 同步，否则页面仍渲染旧模板；浏览器侧需 Ctrl+F5 清缓存。

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
