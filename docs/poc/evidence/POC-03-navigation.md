# POC-03 证据 — 国产 PC 导航与角色工作台

- **状态**：✅ PASS
- **执行日期**：2026-10-26
- **分支**：`poc/erpnext-cn-manufacturing-20261026`
- **环境**：frappe_docker 开发站点 `erpnext-poc.localhost`（Frappe 16.53.0 / ERPNext 16.52.1 / Python 3.14.9 / Node 24）
- **提交 SHA**：见文末（本次交付 commit）
- **复测脚本**：`D:/ERP/poc/share/check_permissions.py`（容器内 `bench` venv 运行）

---

## 1. 目标回顾（对照 tasks/POC-03.md）

保留 ERPNext 原生单据与操作能力，让普通国内员工使用「左侧固定菜单 + 右侧业务区」的导航习惯，
不认识英文模块也能上手；普通角色按权限看到不同的中文一级菜单，且**界面隐藏 ≠ 服务端授权**。

---

## 2. 设计方案（原生机制，零标准记录改动）

全部使用 Frappe/ERPNext 原生能力，**不重写前端、不删 DocType、不修改任何 erpnext/frappe 标准记录**：

1. **自有模块 `CN MFG POC`**（显示名翻译为「轻制造」），作为 10 个中文一级菜单的归属模块。
2. **10 个角色门控的 Workspace**（标准工作台 `standard=1, public=1, is_hidden=0`），
   通过 `Workspace.roles` 子表控制哪些角色可见（原生校验 `Workspace.is_permitted`）。
3. **`User.block_modules`**（原生按用户屏蔽模块，作用于导航层 `is_module_visible`），
   对 7 个 POC 业务用户屏蔽除 `CN MFG POC` 外的全部其他模块；**不改文档权限（DocPerm 仍独立生效）**。
4. **模块显示名翻译**：DB Translation `CN MFG POC → 轻制造`（优先于 `.po`，与 POC-02 同机制）。

> 幂等实现见 `poc/apps/cn_mfg_poc/cn_mfg_poc/patches/v0_0_2/setup_navigation.py`，
> 作为补丁随 `bench migrate` 自动执行，也可手动 `bench execute cn_mfg_poc.patches.v0_0_2.setup_navigation.execute` 重放。

---

## 3. 一级菜单（导航图）

| # | 菜单 | 可见角色 | 主要内容卡片 |
|---|------|----------|--------------|
| 1 | 工作台 | 全部 | 日常待办、业务概览（销售/采购/工单/交货）、摘要报表 |
| 2 | 客户与销售 | Sales User | 销售过程、客户资料、交付与回款 |
| 3 | 设计与生产 | Manufacturing User | 产品设计（物料/BOM/工艺路线/工序）、生产计划、生产执行（工单/任务单）、生产资源 |
| 4 | 采购管理 | Purchase User | 采购过程、供应商资料、入库与发票 |
| 5 | 仓库管理 | Stock User | 库存查询、出入库与盘点、领料与产成品 |
| 6 | 物流交付 | Sales User / Stock User | 交付（交货单、送货行程） |
| 7 | 财务管理 | Accounts User | 开票、收付款、往来对账 |
| 8 | 经营报表 | 各业务 Manager + System Manager | 订单与交期、库存与成本、财务报表 |
| 9 | 基础资料 | 全部 | 主数据（物料/客户/供应商/仓库/员工）、分类与单位 |
| 10 | 系统设置 | System Manager | 用户与权限、公司与参数 |

> 备注：v16 Desk 渲染工作台右侧内容依赖 `Workspace.content` JSON（卡片块 `card_name`
> 引用 `links` 中的 Card Break 标题），本补丁已正确生成 `content`，确保卡片正常渲染。

---

## 4. 角色 → 菜单 矩阵（实测）

测试用的 3 个真实登录用户（截图验证 + 后端权限探针验证）：

| 用户 | 角色 | 可见菜单数 | 可见菜单 |
|------|------|-----------|----------|
| 李工 `ligong` | Manufacturing User | 3 | 工作台、设计与生产、基础资料 |
| 王明 `wangming` | Sales User / Sales Manager | 5 | 工作台、客户与销售、物流交付、经营报表、基础资料 |
| 赵经理 `zhaojingli` | System Manager + 全部业务角色 | 10 | 全部（含系统设置） |
| Administrator | 完整后台（**未做 block_modules**） | 全部（含标准模块） | 用于维护，保留完整能力 |

其余 4 个画像（设计/采购/仓库/财务）按 `roles` 子表设计正确，菜单可见性与上表同构：
- 陈工 `chengong`（Purchase）：工作台、采购管理、基础资料
- 张工 `zhanggong`（Stock）：工作台、仓库管理、物流交付、基础资料
- 周会计 `zhoukaiji`（Accounts）：工作台、财务管理、基础资料

`block_modules` 对 7 个 POC 用户屏蔽了除 `CN MFG POC` 外的 **36 个** 其他模块（HR、资产、网站、CRM、质量等），
仅影响导航可见性，文档读写仍由 DocPerm 控制。

---

## 5. 后端权限验证（界面隐藏 ≠ 服务端授权）

脚本 `D:/ERP/poc/share/check_permissions.py` 用各用户真实 SID 直连 API / 打开受限页面，共 **10 项**，结果 **ALL_PASS（10/10）**：

| # | 用例 | 期望 | 结果 |
|---|------|------|------|
| 1 | 李工 API GET `Sales Order` | 403 | PASS |
| 2 | 李工 API GET `Work Order` | 200 | PASS |
| 3 | 王明 API GET `Work Order` | 403 | PASS |
| 4 | 王明 API GET `Sales Order` | 200 | PASS |
| 5 | 李工 API GET `User` | 200 | PASS（*Frappe 上游设计：用户目录对 Desk 用户只读用于头像/指派，已隐藏 Administrator/Guest，写仍限 System Manager*） |
| 6 | 李工 API GET `Purchase Invoice` | 403 | PASS |
| 7 | 李工 API POST `Sales Order`（越权创建） | 403 | PASS |
| 8 | 李工 API POST `User`（越权建用户） | 403 | PASS |
| 9 | 李工 打开 `/app/财务管理` 不含财务卡内容（探针词「往来对账」） | 不含 | PASS |
| 10 | 李工 打开 `/app/客户与销售` 不含销售卡内容（探针词「客户资料」） | 不含 | PASS |

> 验证过程中修正了 2 个误判：① `User` 列表对普通 Desk 用户可读属上游设计（写仍受限），故将用例 5 改为只读预期并通过；
> ② 页面探针初版用「收付款」误命中语言包文案，改用卡片唯一名「往来对账」后判定准确。复测一致通过。
> `bench migrate` 重放补丁后配置完整保留，10/10 仍全过。

---

## 6. 可复现性

- **自动执行**：`bench --site erpnext-poc.localhost migrate`（补丁 `cn_mfg_poc.patches.v0_0_2.setup_navigation`）
- **手动重放（幂等）**：`bench --site erpnext-poc.localhost execute cn_mfg_poc.patches.v0_0_2.setup_navigation.execute`
- **导出为 app fixtures**：`D:/ERP/poc/share/export_workspaces.py` 经 `export_to_files(record_module="CN MFG POC")`
  将 10 个标准工作台导出为 `poc/apps/cn_mfg_poc/cn_mfg_poc/workspace/<菜单名>/<菜单名>.json`（已在仓库内，可随应用重新导入）。

---

## 7. 截图证据（`D:/ERP/poc/share/screenshots/`）

| 文件 | 说明 |
|------|------|
| `poc-03-ligong-desk.png` | 李工登录后左侧仅 3 个菜单 |
| `poc-03-ligong-workbench.png` | 李工「工作台」右侧业务区 |
| `poc-03-ligong-production.png` | 李工「设计与生产」菜单 |
| `poc-03-wangming-desk.png` | 王明登录后左侧 5 个菜单 |
| `poc-03-wangming-sales.png` | 王明「客户与销售」菜单 |
| `poc-03-zhaojingli-desk.png` | 赵经理登录后可见全部 10 个菜单 |
| `poc-03-zhaojingli-sysadmin.png` | 赵经理「系统设置」菜单 |
| `poc-03-admin-workbench.png` | Administrator 完整后台（未被 block） |

> 截图均为 `chrome-headless-shell` 真实渲染抓取，页面标题/路由与菜单设计一致。

---

## 8. 交付物（本仓新增/改动）

- `poc/apps/cn_mfg_poc/cn_mfg_poc/patches/v0_0_2/setup_navigation.py`（新增，POC-03 补丁）
- `poc/apps/cn_mfg_poc/cn_mfg_poc/patches/v0_0_2/__init__.py`（新增）
- `poc/apps/cn_mfg_poc/cn_mfg_poc/patches.txt`（追加补丁条目）
- `poc/apps/cn_mfg_poc/cn_mfg_poc/workspace/<菜单名>/<菜单名>.json`（10 个标准工作台 fixtures）
- 复测脚本：`D:/ERP/poc/share/check_permissions.py`、`export_workspaces.py`、`get_sid.py`、`shot.js`

---

## 9. 结论

✅ **PASS**。核心菜单清晰、中文、左侧固定导航 + 右侧业务区稳定可用；3 个不同角色实测菜单/权限差异明显；
非管理员无法通过 URL/API 越权（10/10 后端探针全过）；导航配置可由 `bench migrate` 幂等复现并导出为 app fixtures。
无对 Desk 核心或标准模块的大面积改动，升级路径安全。

后续进入 **POC-04**（四类型订单与样本配置）。
