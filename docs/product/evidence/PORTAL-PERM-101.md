# PORTAL-PERM-101 门户菜单按真实权限过滤（2026-11-09）

状态：**ONLINE_PASS**（本地 `erpnext-poc.localhost` + 线上 `d.urlxl.cn` 均验证；纯模板/视图改动，无 schema、无数据变更）。

## 0. 用户反馈与根因

用户（liugong@erpnext-poc.localhost，设计生产角色）登录门户后，能看到「设计与生产」等模块下的菜单项，但点进原生页面提示：

> 角色权限管理中未授权用户 liugong@erpnext-poc.localhost 访问 页面

即「菜单能看、点进去 403」。

**根因**：门户菜单由 `cn_mfg_poc/www/cn_portal.py` 的 `_build_menu` 按 Workspace / Workspace Link 静态推导，只对 Workspace 的 `roles` 子表做**粗粒度**过滤；而 DocType / Report / Page 是否真能打开，取决于各自独立的 DocPerm 与 Report.ref_doctype 权限（**细粒度**）。两套数据不同源，必然出现不一致。

实测反例（设计生产账号）：42 条菜单里 **16 条**会被 Desk 拒绝——销售订单 / 采购订单 / 交货单 / 供应商 / 客户组 / 供应商组 / 销售分析 / 采购分析 / 库存余额 / 账龄 / 总账等。

## 1. 复现

- 用 liugong 真实账号访问 `/desk/manufacturing`、`/desk/home` 等，页面弹出中文 403。
- 抓包定位：`POST /api/method/frappe.desk.desk_page.getpage`（`name=manufacturing`）返回 403；Administrator 同页面正常。
- 门户右上「原生 Desk」链接写死 `/desk/home`，liugong 打开即触发 Workspace Page 权限校验。

## 2. 修复（cn_mfg_poc/www/cn_portal.py + cn_portal.html）

- 新增 `_item_permitted(item)`：
  - `kind=="DocType"` → `frappe.has_permission(target, "read")`
  - `kind=="Report"` → `_report_permitted`（见下）
  - `kind=="Page"` → `_page_permitted`（Page.roles 子表 + Page DocPerm）
  - `kind=="URL"` → 映射到客户中心的 Lead/Customer 按底层 DocType 判断；其余自定义页（order_execution / production_board / …）各自在页面内校验
- `_report_permitted(name)` 与 `frappe.desk.query_report.get_report_doc` **完全同口径**：`Report.is_permitted()`（报表 Has Role 子表）+ `has_permission(report.ref_doctype, "report")`。
  - **关键差异**：旧逻辑用 ref_doctype 的 **read** 级判断，会放行一批「能读单据、但没有报表级权限」的账号；Frappe 在 `get_report_doc` 里用的是 **report** 级，二者不一致正是菜单放行、点进去却 403 的来源，现已改为与框架同口径。
- `_filter_menu_by_permission(menu)`：渲染前逐条过滤；空分组 / 空模块一并收起；统计 `hidden_items` 供调试。
- `get_context` 顺序：先 `_rewrite_crm_links`（保留 Lead/Customer 的 `desk_url`），再 `_filter_menu_by_permission`，输出 `menu_json`。
- `cn_portal.html` 顶栏「原生 Desk」由写死的 `/desk/home` 改为 `/desk`（避免非管理员直接进入 workspace 首页触发 403）；保留 PORTAL-LOGOUT 已加的「退出」按钮。

## 3. 内页 403 友好兜底（cn_portal.html）

菜单过滤覆盖了绝大多数「能看不能点」的情况，但仍有少量**运行时 403 无法在渲染前预判**——最典型的是**报表 SQL 引用了无权限的单据**。例：采购角色 chengong 点「应付账龄」（标准报表 Accounts Payable），其 SQL 引用 Journal Entry，而采购角色无 Journal Entry 读权限 → 运行时 403。

处理：iframe 加载后 `guardIframe()` 识别 Frappe 报错页 / 报错卡片 / 错误 Toast（`PermissionError` / `未授权用户` / `权限不足` / `Not Permitted` / `403` 等），用友好的「当前账号暂无权限查看此内容」覆盖层替换刺眼的原始报错，并提供「返回首页」。分 300 / 1200 / 3200ms 三次轮询，以覆盖 SPA 延迟渲染的 Toast。

## 4. 验证

本地（`erpnext-poc.localhost`，`http://127.0.0.1:18000`）与线上（`d.urlxl.cn`）一致，脚本 `portal_menu_check.py` 逐账号抓 `/cn_portal` 菜单 JSON 并对每个菜单项实际 URL 校验可达性（DocType 用 get_list，Single 单据回退 Desk 路由；Report 直接跑 `query_report.run` 以暴露运行时 403；URL 直接 GET）：

| 账号 | 修复前菜单项 | 修复后菜单项 | 不可达 |
|---|---|---|---|
| liugong（设计生产） | 42（16 不可达） | **24（0 不可达）** | 0 |
| chengong（采购） | — | 21 | 1（应付账龄，见 §3 兜底） |
| wangming / xiaoshou-b / zhanggong / ligong / zhoukaiji / chejian-b | — | 18~26（角色预期） | 0 |
| Administrator | — | 96 | 0 |

- liugong：`/desk` 与 `/desk/home` 均 200；菜单 0 不可达；原 16 条被拒菜单已不再出现在门户。
- 线上回归 `uat97r_http_check.py --base https://d.urlxl.cn --creds uat97r_credentials.online.json`：**100/100，0 失败**（未破坏任何既有流程；该回归脚本当前口径 100 项，原 UAT-97R 基线 118/118 仍成立）。
- **已知边角**：chengong「应付账龄」因报表内部引用 Journal Entry 仍会运行时 403，已由 §3 友好兜底覆盖；若要彻底从菜单隐藏，需在 Workspace 配置移除该报表对采购角色的可见性，或授予 Journal Entry 读权限（超出本次缺陷修复范围，登记 BACKLOG）。

## 5. 部署

- 纯模板/视图改动，**无 migrate**。
- 备份：`/app/backup/portal-perm-fix/20261109-144819`（应用整目录 `cn_mfg_poc` + 数据库 dump `brj_erp` 14M）。
- 解包仅覆盖 `cn_mfg_poc/cn_mfg_poc/www/cn_portal.py` 与 `cn_portal.html`；校验 `guardIframe` / `perm-block` / `is_permitted` / report 级校验 / 菜单过滤 均在位。
- 重启 web / worker / socketio / schedule 四服务 + redis 均 active；`https://d.urlxl.cn/api/method/ping` = 200。
- 本地容器 `poc-frappe` 同步同样两份文件并 `bench clear-cache`，与线上逻辑一致。

## 6. 结论

门户菜单现在与当前用户真实权限对齐，liugong「能看设计菜单却 403」的问题已消除；残余运行时 403（报表引用无权限单据）由内页友好兜底覆盖。无数据变更、无业务影响、不影响 H5 / 机器人接口。

Git SHA：a1e7ab17（commit 见 git log）
