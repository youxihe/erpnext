# PAGE-PERM-102 原生 Desk 首页 403「未授权访问页面」修复（2026-11-18）

状态：**ONLINE_PASS**（线上 `d.urlxl.cn` 实测；纯权限配置变更，无代码 / 无 schema / 无业务数据改动）。

## 0. 用户反馈

用户重新登录后访问 `https://d.urlxl.cn/desk/home`，仍弹出：

> 没有权限 · 角色权限管理中未授权用户 liugong@erpnext-poc.localhost 访问 页面 · 无权限操作页面

**先确认上次发布是否生效**：线上 `cn_portal.py` md5 `c67cf978…`、`cn_portal.html` md5 `f280755b…`，`guardIframe`=2、`_filter_menu_by_permission`=2 —— PORTAL-PERM-101 代码确实已上线。**这次是另一条路径**。

## 1. 根因（与 PORTAL-PERM-101 完全不同）

- 上次 PORTAL-PERM-101 修的是 **`/cn_portal` 中文门户的菜单过滤**，让 liugong 看不到点不开的菜单项。
- 但用户登录响应是 `home_page:"desk"` → **Frappe 登录后默认跳原生 Desk（`/desk`）**，SPA 打开 "Home" Workspace 时调用 `POST /api/method/frappe.desk.desk_page.getpage(name=home)`。
- `getpage → get() → frappe.get_doc("Page", name)` 内部按 DocType 级 `Page.read` 校验；失败即抛「角色权限管理中未授权用户…访问页面」。
- 线上 `tabDocPerm parent=Page` 只有 `System Manager` / `Administrator` 两行 read=1；业务角色拿不到 `Page.read`。
  - 实测（修复前）：liugong / wangming 的 `Page.read=False`；zhaojingli 因带 System Manager 才为 True——与「只有管理员能进原生 Desk」的现象完全吻合。

## 2. 修复

给 **Desk User** 角色补上 `Page.read`（permlevel 0，只读）：

- 通过 Frappe 原生 `frappe.permissions.add_permission("Page", "Desk User", 0)` 写入 **`Custom DocPerm`** 表；
- 落库记录：`name=angm7a27g6, parent=Page, role=Desk User, read=1, write=0, permlevel=0`。
- 这是标准且可审计的做法（Frappe 不允许在非 Developer Mode 下直接改标准 DocType 的 `tabDocPerm`；自定义权限必须走 `Custom DocPerm`）。
- 业务账号均通过 Role Profile 持有 `Desk User`，因此一次性覆盖全部 9 个测试账号。
- **不放开任何业务数据**：`Page.read` 只是允许打开 Desk 页面框架；单据级权限仍由各 DocType 的 DocPerm、Workspace.roles、以及 PORTAL-PERM-101 的门户菜单过滤控制。

## 3. 验证

- 备份：`/app/backup/page-perm-fix/20261118-223235`（数据库 dump，13M）。
- 修复前：`getpage(name=home)` → **403 + PermissionError +「未授权…访问页面」**。
- 修复后：9 个业务账号逐一「登录 → 打开 /desk → getpage(home)」复测，**全部无 403 / 无「未授权」**（返回 404 `DoesNotExistError` 仅因 v16 无字面名为 home 的 Page 文档，与权限无关）。
- **持久化验证**：清缓存 + 重启 web/worker/socketio/schedule 四服务后，全新进程查 `Custom DocPerm` 行仍在、`Page.read=True`、HTTP 仍无 403 —— 证明不是缓存副作用。
- 回归：UAT-97R `uat97r_http_check.py` **100/100，0 失败**；门户菜单 `portal_menu_check.py` 结果与修复前一致（仅 chengong「应付账龄」运行时 403 的边角，已由 PORTAL-PERM-101 的内页友好兜底覆盖）。
- `ping=200`。

## 4. 结论

原生 Desk 首页的「未授权访问页面」已消除。两个历史问题各自归位：

| 问题 | 路径 | 修复 |
| --- | --- | --- |
| PORTAL-PERM-101 | `/cn_portal` 门户菜单「能看点不开」 | 渲染前按真实权限逐条过滤 + 内页 403 友好兜底 |
| PAGE-PERM-102（本项） | 登录后默认 `/desk` 首页 403 | `Custom DocPerm` 授予 Desk User 角色 `Page.read` |

无代码改动、无 schema 改动、无业务数据改动、不影响 H5 / 机器人接口。
