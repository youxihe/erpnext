# POC-00 — 本机审计与版本锁定

## 目标
明确真实可运行环境，避免基于 fork 默认 develop(v17 开发分支)安装失败；不破坏 D:\ERP 下 JSH ERP/ai-erp/OpenClaw。

## 执行
1. 在 Windows/Workbuddy 检查 git status、git remote、工作目录 D:\ERP\erpnext 的 HEAD/分支、本地未提交修改，记录。不要 reset/丢弃现有改动；先妥善备份或 stash 且留说明。fetch origin，切换至 poc/erpnext-cn-manufacturing-20261026；不存在则报告而不是创建不一致的新基线。确认 pyproject.toml 与 Frappe 兼容约束。
2. 检查 Windows 版本、WSL2 distro、Docker Desktop/Compose、内存/磁盘、是否已有 Frappe Bench/容器、当前监听端口和网络代理。Docker 端口/volume 不与 JSH ERP、OpenClaw 冲突。
3. 指定隔离 POC 开发目录、持久化 volume、site 名称（建议 erpnext-poc.localhost，须验证本机解析）、对外仅 localhost 的浏览器端口。保留 D:\ERP\erpnext 作为 fork 源码；如果容器内部另有 apps/erpnext 检出，必须证明源于 POC branch 并记映射关系。
4. 从官方 frappe_docker 文档选择**可安装自定义应用**的开发方案；明确不能用 pwd.yml 代替。验证 Python 要求 >=3.14，ERPNext 与 Frappe 都属 version-16 兼容范围且 Frappe 满足 >=16.50.0,<17.0.0；编写简洁实施记录。
5. 保存 docs/poc/evidence/POC-00-environment.md，包括版本、占用、部署方案、源目录映射、回滚手段、风险和是否可开工；不提交密钥/私密文件。

## DoD / Gate
- 源码正确处于 POC branch；版本与兼容关系有实际输出。
- 安装路径/容器/端口/DB隔离有明确计划且无破坏性操作。
- Workbuddy 有可执行安装路径，00=PASS，才允许 01 开始。
