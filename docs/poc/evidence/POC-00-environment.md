# POC-00 — 本机审计与版本锁定（证据记录）

执行日期：2026-10-26
执行者：Workbuddy（单 Agent 串行）
状态：**PASS**

---

## 1. 源码与 Git 状态

| 项 | 实际值 |
|---|---|
| Windows 源码目录 | `D:\ERP\erpnext`（本轮新建克隆，此前该目录不存在） |
| 当前分支 | `poc/erpnext-cn-manufacturing-20261026` |
| HEAD | `ea9d3ceb43c76039c39354f704a63b860d1423d9` |
| HEAD 提交标题 | `docs(poc): add sequential Workbuddy ERPNext v16 Chinese manufacturing evaluation plan` |
| 父提交 | `ade850bbd6a7412e9994a9637d2c5c713771632a` = `chore(release): Bumped to Version 16.52.1` |
| 远程 fetch | `https://github.com/youxihe/erpnext.git` |
| 远程 push | `git@github.com:youxihe/erpnext.git`（已改为 SSH，已验证 `ssh -T git@github.com` 通过） |
| upstream | `origin/poc/erpnext-cn-manufacturing-20261026` |
| 未提交修改 | **0**（`git status --porcelain` 输出为空） |
| 克隆方式 | `--depth 100 --single-branch`（浅克隆；GitHub git 协议在本机约 100KB/s，HTTPS codeload 约 4.5MB/s） |

### 版本来源证明（明确不是 develop / v17）

```
$ git ls-remote --heads git@github.com:youxihe/erpnext.git refs/heads/version-16
ade850bbd6a7412e9994a9637d2c5c713771632a   refs/heads/version-16
```

- `origin/version-16` 的 SHA 与 AGENTS.md 声明的基线 `ade850bb…`（16.52.1）**完全一致**；
- POC 分支 HEAD 的**父提交就是** `ade850bb…`，因此 POC 分支是从 version-16 派生，不是 fork 默认的 develop(v17) 线；
- 本轮未做任何 reset / 丢弃操作；目录为空目录新建，不存在被覆盖的既有改动。

### 版本兼容矩阵（来自源码实际输出，非推测）

`erpnext/pyproject.toml`：

```toml
requires-python = ">=3.14"

[tool.bench.frappe-dependencies]
frappe = ">=16.50.0,<17.0.0"
```

`erpnext/__init__.py`：`__version__ = "16.52.1"`

| 组件 | 要求 | 本轮满足方式 |
|---|---|---|
| ERPNext | 16.52.1 | POC 分支源码本身 |
| Frappe | >=16.50.0,<17.0.0 | `bench init --frappe-branch version-16` |
| Python | >=3.14 | `frappe/bench:latest` 镜像内置 pyenv 3.14（另有 3.12） |
| Node | v16 当前线 | `frappe/bench:latest` 镜像内置 nvm Node 24（另有 22） |

`frappe/bench:latest` Dockerfile（`frappe_docker/images/bench/Dockerfile`）实测声明：
`PYTHON_VERSION_PREV=3.12`、`PYTHON_VERSION=3.14`、`NODE_VERSION_PREV=22`、`NODE_VERSION=24`。

---

## 2. 本机环境审计

| 项 | 实测 |
|---|---|
| 操作系统 | Windows 11 专业版，build 26200 |
| CPU | Intel Core i5-14400F，16 逻辑处理器 |
| 内存 | 15.82 GB，**空闲约 2.08 GB**（风险点，见下） |
| 磁盘 | C: 剩 22.4 GB（Docker Desktop 数据盘所在）、D: 剩 82.8 GB、E: 剩 675.1 GB |
| Docker | Docker Desktop 28.3.3，Compose v2.39.2，存储驱动 overlayfs |
| Registry 镜像源 | `https://hub-mirror.c.163.com/` |
| WSL2 | Windows 功能「适用于 Linux 的 Windows 子系统」= Enabled、VirtualMachinePlatform = Enabled |
| **wsl.exe CLI** | **被 Workbuddy 沙箱安全策略列入程序黑名单拦截**，不能直接开 Linux distro shell |

> 说明：`wsl.exe` 被拦截只影响「手工开一个 Linux 发行版终端」。Docker Desktop 自带并管理其 WSL2 后端，本轮验证 `docker run / docker compose / docker exec` 全部可用，因此 **WSL2 + Docker Desktop 的技术前提成立**，只是操作入口走 Docker CLI 而非 `wsl` 命令。

### 已占用端口（不得冲突）

已监听：`135 139 445 3001 3389 5040 5283 5357 7680 9999 10232 13306 14013~14023 16379 18488 18789 35421 39099 49664~49681 53140 53306 54530 54533 55113 55119 55150 55177 59337 59338 60012 63957`

其中属于**其他项目**的运行容器（严禁动）：

| 容器 | 镜像 | 端口 |
|---|---|---|
| `aierp-boot` | deploy-aierp-boot | 127.0.0.1:9999 |
| `aierp-mysql` | mysql:8.0.36 | 127.0.0.1:13306 |
| `aierp-redis` | redis:6.2.14-alpine | 127.0.0.1:16379 |

Docker 现有镜像 23 个（26.01 GB）、卷 11 个，全部属于 ai-erp / openclaw 等既有项目。
**本轮不会执行 `docker system prune`、不会删除任何既有 volume / 镜像 / 数据库。**

---

## 3. 隔离方案（POC 专用，与其它项目零重叠）

| 资源 | POC 取值 | 隔离措施 |
|---|---|---|
| 编排目录 | `D:\ERP\poc\frappe_docker\docker-compose.yml` | 独立目录，不复用 frappe_docker 默认路径 |
| 容器名 | `poc-mariadb` / `poc-redis-cache` / `poc-redis-queue` / `poc-frappe` | `poc-` 前缀，与 `aierp-*` 无交集 |
| Docker 卷 | `poc-mariadb-data`、`poc-workspace` | 新建卷，不挂载任何既有卷 |
| MariaDB | `mariadb:11.8`，root 口令 `123`（仅容器内，不进 Git） | 独立实例，未对外发布端口 |
| Redis | 2 个独立实例（cache / queue） | 未对外发布端口 |
| Web 端口 | `127.0.0.1:18000-18005` → 容器 `8000-8005` | **仅绑定回环地址**，外部不可达 |
| SocketIO 端口 | `127.0.0.1:19000-19005` → 容器 `9000-9005` | 同上 |
| 站点名 | `erpnext-poc.localhost` | 需 hosts 解析（见下） |
| 宿主机交换目录 | `D:\ERP\poc\share`（备份/证据/自定义 app 导出） | 已实测可读写挂载 |
| 备份目录 | `D:\ERP\poc\backup` | 仅 POC 使用 |

### 域名解析
Windows 不会自动解析 `*.localhost`（实测 `ping zzz-test-poc.localhost` 失败）。
本机具备管理员权限且 hosts 文件可写（实测写测试文件成功），
POC-01 阶段将追加一行 `127.0.0.1  erpnext-poc.localhost`。

### Bench 工作目录存放位置的决定
`frappe_docker` devcontainer 默认把仓库父目录整盘 bind mount 到 `/workspace`。
Windows bind mount 下 bench 的数万次小文件读写 + Node 构建会极慢，因此本轮改为：

- `/workspace` → **Docker 命名卷 `poc-workspace`**（容器原生 ext4，速度快）；
- Windows 侧 `D:\ERP\erpnext` 保留为 fork 源码与文档/脚本的唯一提交点；
- 容器内 `apps/erpnext` 以 `git clone --depth 1 -b poc/erpnext-cn-manufacturing-20261026` 取得，
  并在 POC-01 记录其 HEAD SHA 与 Windows 侧 `D:\ERP\erpnext` 的对应关系，满足 AGENTS.md
  「容器内部另有 apps/erpnext 检出时须证明源于 POC branch 并记映射关系」的要求；
- 需要双向搬运文件时使用 `docker cp` 与 `D:\ERP\poc\share` 挂载目录。

### 不用 pwd.yml 的理由
`frappe_docker` README 原文：「This setup is intended for short-lived evaluation only.
**You will not be able to install custom apps to this setup.**」
与 POC-01「可安装自定义 App 的开发环境」要求直接冲突，故采用
`devcontainer-example` + `docs/05-development/04-alternate-setup.md` 的 CLI 开发方案。

---

## 4. 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| 物理内存空闲仅约 2 GB | bench 多进程（web/socketio/watch/schedule/worker×2）+ MariaDB 可能吃紧 | ① MariaDB `innodb-buffer-pool-size=256M`；② Redis 限 128MB；③ POC-01 只起必需进程（web + worker + schedule），不起 Node `watch`；④ 必要时改用 E: 盘或增加页面文件 |
| C 盘仅剩 22.4 GB，Docker 数据盘在 C | frappe/bench 镜像 + 构建缓存可能挤压 C 盘 | 不构建多余镜像；构建缓存只为自己产生；如吃紧优先把本机页面文件/临时目录迁到 D/E，或经用户同意后调整 Docker 数据盘位置（需重启 Docker Desktop，会影响其他项目容器，未获同意前不执行） |
| GitHub git 协议慢（~100KB/s） | 容器内 `bench init` 拉取 frappe 可能超时 | 已预先通过 codeload（4.5–5.9 MB/s）取到 `frappe` version-16 与 erpnext POC 分支源码包作备选；必要时用 `--frappe-path` 本地路径初始化 |
| wsl.exe 被安全策略拦截 | 无法手工进入 Linux 发行版 | 全部改用 `docker exec`；已验证可行 |

---

## 5. 回滚手段

- 源码：本目录为新建克隆，最坏情况删除 `D:\ERP\erpnext` 重新克隆即可，无既有改动可丢。
- 容器/数据：`docker compose -f D:\ERP\poc\frappe_docker\docker-compose.yml down`
  再 `docker volume rm poc-workspace poc-mariadb-data` 即可完全清除 POC 痕迹，
  不影响 `aierp-*` 容器、镜像与卷。
- hosts：删除新增的 `erpnext-poc.localhost` 一行即可还原。

## 6. POC-00 结论

- 源码正确处于 POC 分支，且已用 `git ls-remote` + 父提交双重证明源自 version-16 16.52.1；
- 版本与兼容关系有实际源码输出（Python >=3.14、Frappe >=16.50.0,<17.0.0）并与 bench 镜像能力对齐；
- 安装路径、容器、端口、数据库隔离方案已确定且全部为新增资源，无破坏性操作；
- **00 = PASS**，可执行 POC-01。
