# POC-01 — 安装 ERPNext 并初始化隔离 Site（证据记录）

执行日期：2026-10-26
状态：**PASS**

---

## 1. 部署方案（可安装自定义 App 的开发环境）

采用 **frappe_docker 官方 `devcontainer-example` + `docs/05-development/04-alternate-setup.md`（CLI-only）** 方案，
**没有使用 pwd.yml**（官方 README 明确说明 pwd.yml 不能安装自定义 App，与 POC 要求冲突）。

### 资源清单（全部为新增，与其他项目零重叠）

| 项 | 值 |
|---|---|
| 编排文件（运行时） | `D:\ERP\poc\frappe_docker\docker-compose.yml` |
| 编排文件（仓库副本） | `D:\ERP\erpnext\poc\env\docker-compose.yml` |
| 容器 | `poc-frappe` / `poc-mariadb` / `poc-redis-cache` / `poc-redis-queue` |
| Docker 卷 | `poc-workspace`（bench 与站点数据）、`poc-mariadb-data`（数据库） |
| 宿主交换目录 | `D:\ERP\poc\share`（挂载到容器 `/hostshare`） |
| Web 端口 | `127.0.0.1:18000-18005` → 容器 `8000-8005` |
| SocketIO 端口 | `127.0.0.1:19000-19005` → 容器 `19000-19005` |
| MariaDB / Redis | 未向宿主发布端口，仅容器网络内可达 |
| 站点名 | `erpnext-poc.localhost` |
| hosts 记录 | `127.0.0.1 erpnext-poc.localhost`（已加入 `C:\Windows\System32\drivers\etc\hosts`） |

### Bench 目录与源码映射

```
容器内 /workspace（Docker 卷 poc-workspace）
├── development/frappe-bench/          ← Bench
│   ├── apps/frappe                    ← Frappe version-16（git clone，HEAD e8d41dd）
│   ├── apps/erpnext                   ← **POC 分支**（git clone，HEAD ea9d3ce）
│   ├── apps/cn_mfg_poc                ← 本轮新建自定义 App
│   ├── env/                           ← Python 3.14.9 virtualenv
│   └── sites/erpnext-poc.localhost/   ← 隔离站点
├── scripts/  poc-start.sh / poc-stop.sh / setup_site.sh
├── tools/    puppeteer-core 截图工具
└── src/      frappe-v16 / erpnext-poc（拉取源码缓存）

Windows 侧 D:\ERP\erpnext = fork 源码与文档/脚本的唯一提交点
```

**apps/erpnext 来源证明（容器内实测）：**

```
$ cd apps/erpnext && git rev-parse HEAD && git branch --show-current && git remote -v
ea9d3ceb43c76039c39354f704a63b860d1423d9
poc/erpnext-cn-manufacturing-20261026
origin  https://github.com/youxihe/erpnext.git (fetch)
```

与 Windows 侧 `D:\ERP\erpnext` 的 HEAD 完全一致（均为 `ea9d3ce`）。

---

## 2. 实际版本（容器内实测输出）

```
$ bench --site erpnext-poc.localhost list-apps
frappe      16.53.0  version-16
erpnext     16.52.1  poc/erpnext-cn-manufacturing-20261026
cn_mfg_poc  0.0.1    version-16

$ bench version
erpnext 16.52.1 poc/erpnext-cn-manufacturing-20261026 (ea9d3ce)
frappe  16.53.0 version-16 (e8d41dd)
```

| 组件 | 版本 |
|---|---|
| ERPNext | 16.52.1（POC 分支，commit `ea9d3ce`） |
| Frappe | 16.53.0（version-16 分支，commit `e8d41dd`）——满足 pyproject 要求 `>=16.50.0,<17.0.0` |
| Python | 3.14.9（满足 `requires-python >=3.14`） |
| Node | v24.22.1（容器内置 nvm） |
| bench | 5.31.1 |
| MariaDB | 11.8（镜像 `mariadb:11.8`） |
| Redis | alpine（两个独立实例） |

### Setup Wizard 初始化结果（`bench execute` 官方入口）

```
Company           : 昆山启程智能设备有限公司（abbr QC）
System Settings   : language=zh, country=China, time_zone=Asia/Shanghai,
                    currency=CNY, date_format=yyyy-mm-dd, setup_complete=1
Global Defaults   : default_company=昆山启程智能设备有限公司,
                    country=China, default_currency=CNY
Account 数量      : 96（Standard 科目模板自动生成）
```

语言代码确认：Language 表中**只有 `zh`**（language_name=「中文」）与 `zh-TW`，**不存在 `zh-CN`** ——
POC-02 要求的「从实际 Language 表确认」已完成。

---

## 3. 运维命令（实际复测通过）

容器内（已封装为脚本，仓库副本在 `poc/scripts/`）：

```bash
# 启动（幂等，重复执行不会重复起进程）
docker exec poc-frappe bash /workspace/scripts/poc-start.sh
# 停止 bench 进程（容器与数据保留）
docker exec poc-frappe bash /workspace/scripts/poc-stop.sh
```

Windows（仓库脚本 `poc/scripts/poc.ps1`）：

```powershell
D:\ERP\erpnext\poc\scripts\poc.ps1 start     # 起容器 + bench 服务
D:\ERP\erpnext\poc\scripts\poc.ps1 stop      # 停 bench + 停容器（数据保留）
D:\ERP\erpnext\poc\scripts\poc.ps1 status    # 容器状态 + 站点可达性 + 版本
D:\ERP\erpnext\poc\scripts\poc.ps1 logs      # 跟踪日志
D:\ERP\erpnext\poc\scripts\poc.ps1 shell     # 进入容器 bash（bench 目录）
D:\ERP\erpnext\poc\scripts\poc.ps1 bench "version"
D:\ERP\erpnext\poc\scripts\poc.ps1 backup    # 备份到 D:\ERP\poc\backup
```

手工等价命令：

```bash
cd D:\ERP\poc\frappe_docker
docker compose up -d          # 启动容器
docker compose down           # 停止容器（卷保留）
docker compose ps             # 状态
docker exec poc-frappe bash -lc "cd /workspace/development/frappe-bench && bench version"
```

---

## 4. 验收证据

### 4.1 Windows 浏览器侧真实访问（非 HTTP 200 代替）

- 登录 API：`POST /api/method/login` → `{"message":"Logged In","home_page":"desk","full_name":"Administrator"}`
- 工作台 `/app` → HTTP 200，页面标题 **`Desktop`**
- `/app/customer` → HTTP 200，页面标题 **`客户`**

### 4.2 DocType 真实存在且可访问（`/api/resource/<DocType>` 返回 200 与真实数据）

Customer / Item / Sales Order / BOM / Work Order / Job Card / Stock Entry /
Purchase Order / Delivery Note / Sales Invoice / Production Plan / Material Request / Warehouse
全部 200（新建站点数据为空列表，属正常）。

### 4.3 截图（`D:\ERP\poc\share\screenshots\`）

| 文件 | 内容 |
|---|---|
| `poc-01-desk.png` | `/app` 应用入口（搜索栏中文「搜索」，应用 ERPNext / 框架） |
| `poc-01-customer.png` | `/app/customer` 客户列表：**左侧中文工作台导航（主页/数据面板/客户/报价/销售订单/销售出库/销售发票/报表/物料/POS/设置）+ 右侧中文列表区** |

截图由容器内 `chromium-headless-shell`（156.0.8078.47）+ puppeteer-core 生成，脚本在 `poc/scripts/shot.js`。

### 4.4 重启持久化复测

```
docker compose down → docker compose up -d → poc-start.sh
结果：容器全部 Up (healthy)
登录 API 再次成功（{"message":"Logged In"}）
/app → 200
Company 仍为 昆山启程智能设备有限公司；System Settings 仍为 zh/China/Asia-Shanghai/CNY
list-apps 仍为 frappe 16.53.0 / erpnext 16.52.1 / cn_mfg_poc 0.0.1
```

### 4.5 可安装自定义 App（POC 硬性要求）

```
$ bench new-app cn_mfg_poc        # 实际创建成功
$ bench --site erpnext-poc.localhost install-app cn_mfg_poc
Installing cn_mfg_poc...
$ bench --site erpnext-poc.localhost list-apps   # 已出现 cn_mfg_poc 0.0.1
```

apps.txt 顺序固定为 `frappe` → `erpnext` → `cn_mfg_poc`（定制 App 置于最后，便于覆盖）。

---

## 5. 过程中遇到的真实问题与解决（全部留下复现方式）

| # | 问题 | 根因 | 解决 |
|---|---|---|---|
| 1 | `bench init` 卡死 21 分钟 | 容器内 PyPI 直连被限速到 ~372 B/s | 全局配置清华镜像：`~/.config/uv/uv.toml` 与 `/etc/pip.conf` → `https://pypi.tuna.tsinghua.edu.cn/simple`（实测 37 MB/s） |
| 2 | `yarn install` 失败：连不上 `github.com/frappe/air-datepicker` | github.com 主站间歇性不可达（codeload/api 正常） | `git config --global url."https://gitclone.com/github.com/frappe/air-datepicker".insteadOf "https://github.com/frappe/air-datepicker"` |
| 3 | `bench init --ignore-exist` 报错 `uv pip install -e frappe-bench/apps/frappe` | bench 该分支的路径拼接 bug | 删除 frappe-bench 重新 `bench init`（依赖已缓存，仅 37 秒） |
| 4 | `bench build` 失败 `vite: not found` | 首次对 erpnext 用了 `yarn install --ignore-scripts`，跳过了 banking 子包 postinstall | 在 `apps/erpnext` 重新完整 `yarn install` |
| 5 | 访问 `/app/desk` 报「页面 desk未找到」404 | `/app/desk` 是旧版 Page 路由，v16 工作台路由是 `/app` | 使用 `/app`（登录后 home_page 也指向 desk 即工作台） |
| 6 | socket.io 一直连 `http://host:8000/socket.io/` 404 | `DEV_SERVER` 环境变量只有 `bench start` 会设置，手工 `bench serve` 不会 | `poc-start.sh` 中 `export DEV_SERVER=true`，并把 socketio_port 设为 19000（与 compose 映射一致） |
| 7 | 启停脚本误判「已在运行」 | `pgrep -f` 会匹配到包含同样字符串的外层 shell 命令行 | 改用 **pidfile**（`/workspace/run/*.pid`）判定 + `pkill -P` 杀子进程 |
| 8 | 截图中文全是方块（tofu） | 容器是无 CJK 字体的 Debian slim | 从 Windows 复制 `msyh.ttc` 到 `/hostshare/fonts/`，`poc-start.sh` 检测缺失时自动安装并 `fc-cache -f` |

---

## 6. 账号与密码（不进 Git）

Administrator 密码与后续测试账号密码统一保存在本机文件
**`D:\ERP\poc\CREDENTIALS.local.md`**（该文件位于 D:\ERP\poc，不属于 Git 仓库，永不上传）。
仓库内文档只写账号名，不写密码。

---

## 7. 已知限制 / 待后续任务处理

- 中国本地化会计科目模板：ERPNext v16 verified 模板中**没有 China 专属科目表**，
  本次使用 Standard 科目模板（96 个科目）。这是选型评估要记录的真实差距，留到 POC-06 汇总。
- `bench serve` 是开发服务器（Werkzeug），性能不作为验收指标。
- 本机物理内存空闲约 2 GB，因此只启动 web / socketio / worker / schedule 四个进程，
  **未启动 Node `watch`**（前端资源用 `bench build` 一次性构建）。如需热更新前端，可临时手工起 `bench watch`。

## 8. POC-01 结论

- 用户的 Windows 浏览器可访问 `http://erpnext-poc.localhost:18000` 并登录 ✓
- 与既有项目（aierp-* / openclaw）数据、端口、卷完全隔离 ✓
- 启停复测成功、配置与数据持久化 ✓
- 确为 v16 同系列 Frappe 16.53.0 + ERPNext 16.52.1，且可安装自定义 App（cn_mfg_poc）✓
- **POC-01 = PASS**
