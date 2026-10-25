# POC-01 — 安装 ERPNext 并初始化隔离 Site

## 目标
得到可重复启动、可安装自定义 App、可持久化的 **ERPNext v16** 开发环境，让用户用 Windows 浏览器访问。这里不是要求完成业务配置。

## 执行
1. 根据 POC-00 记录，使用 WSL2/Docker Desktop 官方 frappe_docker **开发模式或官方支持的自定义 App 构建模式**准备 Bench、Frappe 16、MariaDB、Redis、worker、scheduler、web。禁止将 pwd.yml 一次性镜像当作开发环境。
2. 将你 fork 的 ERPNext POC branch 安装到 Bench apps/erpnext，严禁不知不觉加载官方 develop/v17 或官方 Docker 预装的其他 commit。需要时 bench get-app --branch poc/erpnext-cn-manufacturing-20261026 指向 https://github.com/youxihe/erpnext.git；确认实际导入源码与 Git commit 一致。
3. 创建全新隔离 site，安装 erpnext app，执行首次初始化/Setup Wizard（中国、CNY、Asia/Shanghai、演示公司）。业务配置不得复制其他 ERP 的数据库。记录 ERPNext/Frappe/Python/MariaDB 实际版本及 site installed apps。
4. 给出 **开始、停止、重启、查看日志、迁移、备份、恢复** 的实际有效命令；如构建脚本，请放入 docs/poc/scripts 或仓库的 poc/scripts，并实际复测。若服务端口与本机系统冲突，选不冲突端口并留证。密码存私有本机文件，不提交。
5. 用 Windows 浏览器验证登录后至少可打开 Customer、Item、Sales Order、BOM、Work Order、Job Card、Stock Entry 页面；不能以 HTTP 200 或 docker ps 代替业务页真实渲染。确认容器重启后站点及账号/数据仍保留。
6. 证据：docs/poc/evidence/POC-01-install.md 记实际命令、版本、URL、site、屏幕截图路径、失败和解决过程。

## DoD / Gate
- 用户的 Windows 浏览器能够访问并登录 ERPNext。
- 与现有项目数据/网络隔离；启停复测成功；升级或重启不会丢掉配置。
- 使用的确实是 v16 同系列 Frappe/ERPNext，可安装自定义 App。
- 未通过不得声称后续功能可用。
