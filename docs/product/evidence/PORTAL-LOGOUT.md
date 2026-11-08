# PORTAL-LOGOUT — `/cn_portal` 缺少退出登录入口（修复记录）

- 日期：2026-11-09
- 触发：用户人工测试时发现「/cn_portal 好像没有退出登录按钮入口」
- 结论：**属实，是遗漏而非实现错误。** 门户自建立以来从未渲染过登出入口，`/role_profiles` 页面还在文案里要求「切换账号前请先退出登录」却同样没有按钮。本轮补两处入口，纯模板改动，未改服务端、未改数据。

## 一、根因（为什么一直没有）

| # | 事实 | 影响 |
|---|---|---|
| 1 | `/cn_portal` 定位是「零侵入统一导航原型」，退出动作默认交给原生 `/desk` 右上角 Logout | 门户本身从设计上就没有承担登出职责 |
| 2 | 顶栏 `.tools` 只有「原生 Desk / 企微 H5 / 全屏 / 头像」，头像是不带事件的 `<div class="avatar">` | 没有任何可点的退出元素 |
| 3 | 侧栏底部 `.side-foot` 只输出身份文字，且 CSS 限高 `max-height:80px; overflow:hidden` | 即使往这里塞链接也会被裁掉 |
| 4 | `cn_portal.get_context` 早已注入 `context.csrf_token`，但模板从未引用 | 说明当初预留了位置，做到一半没有落地（遗漏的直接证据） |

`/role_profiles` 是 UAT-97R 新增页面，文案写明「切换账号前请先退出登录」，但页面只有 `/desk/role`、`/desk/role-profile` 两个技术角色链接，没有返回门户、也没有退出，属于同一处遗漏。

## 二、修复内容

### 1. `/cn_portal` 顶栏（`www/cn_portal.html`）

- `.tools` 内新增 `<button id="btn-logout" class="logout" title="退出登录（当前账号：…）">退出</button>`，位于头像左侧。
- 样式：默认描边透明底，hover 变红底白字（提示这是会中断会话的动作）；窄屏 `@media(max-width:900px)` 隐藏的是 `a.lbl`，退出按钮保留。
- 逻辑：

```js
const CSRF_TOKEN = "{{ csrf_token | e }}";   // 由 get_context 注入
$('#btn-logout').onclick = async ()=>{ ... fetch('/api/method/logout', {method:'POST',
  headers:{'X-Frappe-CSRF-Token': CSRF_TOKEN, ...}}) ... location.replace('/login'); };
```

按钮点击后立刻置灰、文案改「退出中…」，无论请求成功或网络异常都跳 `/login`，避免用户卡在已失效的会话里。

### 2. `/role_profiles` 顶部（`www/role_profiles.html`）

- 标题区改为 `.head` 两栏，右侧 `.acts` 放「返回门户」+「退出登录」（红色描边，hover 红底）。
- 底部加同一套登出脚本，令牌来自 `role_profiles.get_context` 已注入的 `csrf_token`。

### 3. 接口路径为什么是 `/api/method/logout`

实测三个候选（本地站点，真实会话）：

| 路径 | 带正确 CSRF | 结果 |
|---|---|---|
| `/api/method/logout` | 200 → `full_name: Guest` | ✅ 可用（v16 映射到 `frappe.handler.logout`，`allow_guest=True, methods=["POST"]`） |
| `/api/method/frappe.handler.logout` | 200 | ✅ 可用 |
| `/api/method/frappe.auth.logout` | 417 `ValidationError: 无法获取命令` | ❌ 不存在该 whitelisted 方法 |

**结论：只能用 `/api/method/logout`。** 第一版代码误写 `frappe.auth.logout`，实测 417 后已改。部署脚本的 `grep frappe.auth.logout` 会命中模板里的说明性注释，属脚本检查的误报，实际 `fetch` 只有 `/api/method/logout` 一处。

## 三、附带查清的 Frappe 行为：CSRF 是「惰性校验」

探测结果（同一个业务账号，四种会话状态）：

| 场景 | 结果 |
|---|---|
| A. login 后立刻 POST logout（不带任何令牌） | **200，登出成功** |
| B. login → GET `/cn_portal` → POST logout（不带令牌） | 400 `CSRFTokenError: 无效请求` |
| C. login → GET `/cn_portal` → 带错误令牌 | 400，会话仍有效 |
| D. login 后立刻带错误令牌 | 200，登出成功 |
| E. 完全未登录直接 POST logout | 200 |

即：**Frappe 只在会话里已经存在 `csrf_token` 时才校验**；令牌尚未下发时任何 POST 都放行。因此「无 CSRF 也能登出」不是我们的实现放宽了限制，而是框架本身的行为。

对实现的影响：浏览器里用户一定是先打开过页面（token 已下发）才点按钮，所以必须带令牌——这已被用例 B/C 覆盖。本轮**没有**修改任何 CSRF 配置，也没有加 `ignore_csrf`。

## 四、验证

### 本地（`http://127.0.0.1:18000`，真实账号 + 真实浏览器）

`crm100_logout_check.py`（Playwright，sales-A 与经营管理-A 各一套）：

```
PASS  门户 cn_portal 渲染退出按钮
PASS  门户 cn_portal 按钮文案可读            text='退出'
PASS  门户 cn_portal 点击后离开受保护页       url=http://127.0.0.1:18000/login
PASS  门户 cn_portal 会话已失效（再访问跳登录） url=.../login?redirect-to=%2Fcn_portal
PASS  岗位与账号 role_profiles 渲染退出按钮
PASS  岗位与账号 role_profiles 按钮文案可读    text='退出登录'
PASS  岗位与账号 role_profiles 点击后离开受保护页
PASS  岗位与账号 role_profiles 会话已失效
PASS  错误 CSRF 令牌的登出被拒              status=400
PASS  被拒后会话仍有效                      user=wangming@erpnext-poc.localhost
PASS  带正确 CSRF 的登出成功                status=200
合计 PASS 11 / FAIL 0
```

### 线上（`https://d.urlxl.cn`，同上脚本换地址与凭据）

`合计 PASS 11 / FAIL 0`，其中：
- 门户点击退出 → `https://d.urlxl.cn/login`
- 再访问 `/cn_portal` → `https://d.urlxl.cn/login?redirect-to=%2Fcn_portal`（会话确实已失效）
- 错误令牌 400 且 `user=wangming@erpnext-poc.localhost` 保持不变

### 回归

| 项目 | 结果 |
|---|---|
| 本地 UAT-97R 角色/接口矩阵 | **118 / 118** |
| 线上 UAT-97R 角色/接口矩阵 | **118 / 118** |

只加了按钮和脚本，菜单数据、角色过滤、权限判定均未改动。

### 浏览器截图

- `D:\ERP\poc\deploy\crm100_shots\local_logout_portal.png` / `online_logout_portal.png`
- `D:\ERP\poc\deploy\crm100_shots\local_logout_role_profiles.png` / `online_logout_role_profiles.png`

## 五、部署与回滚

| 项 | 值 |
|---|---|
| 备份 | `/app/backup/portal-logout/20261109-022236`（首版）与 `/app/backup/portal-logout/20261109-022414`（注释措辞修正后重发）；各含 `cn_mfg_poc` 整目录 + `brj_erp.sql` 14M（`-- Dump completed on 2026-11-09 2:22:45` / 第二次同类输出） |
| 部署方式 | 打包 `cn_portal_logout.tar.gz` → 解包 → 清缓存 → 重启 4 服务；**未执行 migrate**（无 schema 变更） |
| 服务 | web / worker / socketio / schedule / redis 全部 `active`，`ping=200` |
| 文件指纹 | `cn_portal.html 86485aeb3d`、`role_profiles.html dfebc3d7c8`（本地与线上一致） |
| 回滚 | `cp -a /app/backup/portal-logout/20261109-022236/cn_mfg_poc /app/erpnext-v1/apps/` 后 clear-cache + 重启 |

## 六、未覆盖 / 边界

- 其他中文页面（`/customer_center`、`/customer_detail`、`/lead_detail`）**没有单独放退出按钮**，但都有「返回门户 / 返回客户中心」链路，可从门户退出。是否需要统一加，等用户体验后再定。
- 企微 H5（`/wecom_h5`）在企微客户端内，退出应由企微 OAuth 侧处理，未改动。
- 退出只清当前 sid 与 cookie，不影响其他设备/浏览器已登录的会话（Frappe 原生语义）；本轮没有做「退出所有设备」。
- `desk` 原生退出行为未变。
