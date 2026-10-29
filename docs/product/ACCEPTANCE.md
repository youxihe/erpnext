# PC + 企微自建 H5 + 企微 AI Bot：联合验收记录

**状态：本地三入口联合验收已全部通过（LOCAL_PASS）；真实企业微信真人 UAT 尚未进行（REAL_WECOM_BLOCKED）。**
这份表是 V1 正式成功标准，不得用 10 月 26 日 ERP 单机 POC 的 PASS 代替。
本轮（2026-10-29，BUILD-70）结果见 `docs/product/evidence/BUILD-70.md`。

## 测试环境（已填写）

- ERPNext Site / URL / 源码 HEAD：`erpnext-poc.localhost` · http://erpnext-poc.localhost:18000（或 http://127.0.0.1:18000）· 分支 `product/erpnext-wecom-ai-v1-20261029`
- 中文 PC 入口 / 测试角色：ERPNext v16.52.1 / Frappe v16.53.0 中文界面；赵经理(系统管理)、王明(销售)、李工(生产)、刘工(生产主管)、张工(仓库)、周会计(财务)
- 企业微信 CorpID / 自建应用入口 / HTTPS 域名：**未提供（BLOCKED）**，当前为 Mock 模式（`WeCom Settings.mock_mode=1`）
- 企业微信 H5 URL / build：`/wecom_h5`（`cn_mfg_poc/www/wecom_h5.html|py`），四入口：客户报备/我的订单/我的任务/库存查询
- OpenClaw ERPNext 适配器 / API 机器人连接状态：`product/adapter/erpnext-bot-tools`（独立插件，HMAC 签名通道），本地联调连通；真实 Bot API 待授权
- ERPNext User 与 WeCom UserID 的身份映射：`WeCom User Binding`：ligong→李工、wangming-wx→王明、zhangsan→张工、zhaojingli→赵经理
- 站点与数据库、备份/重启命令：Docker（poc-frappe / poc-mariadb / poc-redis-*）；重启 `docker restart poc-frappe` 后 `bash /workspace/scripts/poc-start.sh`；已验证重启前后单据/库存/绑定完全一致（9/9）
- 真实客户端验收用户与时间：**未进行**（待企微授权）
- 未具备的外部权限或资源：CorpID、AgentID+Secret、可信 HTTPS 域名、通讯录与机器人消息/文件权限

## 联合场景

| 场景 | ERP PC | 企业微信 H5 | 企业微信 AI Bot | 实际单号/数值及身份验证 | 状态 |
|---|---|---|---|---|---|
| 角色与身份一致 | 管理员查 ERP User 和角色 | 同一成员免登 | 同一成员发送消息 | 三入口均为 `ligong@erpnext-poc.localhost`；角色集合 PC==Bot（J1/J2） | LOCAL_PASS |
| 客户报备 | 客户信息可见 | 创建客户报备 | 查客户或发起报备 | Bot 报备 BD-00028→确认→**CRM-LEAD-2026-00009**（owner=王明）；H5 报备同名被查重回带同一单号（J3–J5） | LOCAL_PASS |
| 销售订单 | 4 类订单和交付进度 | 我的订单/状态 | 查指定订单进展 | SAL-ORD-2026-00005 · To Deliver and Bill · 1800.0 三入口一致；李工查王明订单 PC/H5/Bot 均拒（J6–J9） | LOCAL_PASS |
| 车间生产任务 | Job Card 可分派/查看 | 本人任务反馈完成 | 查我的任务 | H5 报工 PO-JOB00004 → 0.5/1.0 Work In Progress；PC/Bot 同步 0.5（J10–J12） | LOCAL_PASS |
| 仓库存量 | 按仓查看物料数量 | 授权库存查询 | 查同一物料余量 | SENSOR：原材料仓 35 / 在制仓 1，三入口同值；销售角色查库存 Bot/H5 均拒（J13–J16） | LOCAL_PASS |
| Excel 采购入库 | 查看正式采购/收货单和库存 | 查看结果 | Excel 预览→本人确认 | PID-00029→预览零变化→确认→**MAT-PRE-2026-00015**，SENSOR 36→41（+5=单据量）；重复确认不再变；H5 读 41（J17–J22） | LOCAL_PASS |
| 账号停用撤权 | 禁用某普通成员 ERP 账户 | 原有 H5 登录不可继续操作 | 机器人旧身份不可查询/写入 | 停用李工：H5 旧会话 401、重新免登 403、Bot USER_DISABLED；恢复后两者均恢复（J23–J27） | LOCAL_PASS |
| 部署与恢复 | 重启后订单仍在 | 恢复可访问 | 机器人恢复连接 | `docker restart poc-frappe` 后：单据/库存/Job Card/绑定快照 9/9 一致；复测 24/24；机器人 whoami 正常 | LOCAL_PASS |

**合计**：本地三入口联合验收 31/31；重启复测 24/24；快照比对 9/9。
**未达标项**：真实企业微信真人 UAT（0/8 场景），原因为外部授权缺失 → REAL_WECOM_BLOCKED。

## 状态语义

- TODO：尚未操作。
- LOCAL_PASS：本地站点/Mock/测试通道已测通，但不是企业微信真人 UAT。
- REAL_WECOM_PASS：真人在企业微信自建应用或真实 API Bot 操作，对账 ERP 同一数据并留下证据。
- FAIL：实测未达到标准。
- BLOCKED：缺少企业微信授权、合法可信域名、Bot 权限或其他无法由 Workbuddy 解决的资源。

## 最终必须交付给用户的体验入口

详见 `docs/product/HANDOVER.md`：

1. 中文 PC 地址 http://erpnext-poc.localhost:18000；账号与密码交接方式见本机 `D:\ERP\poc\CREDENTIALS.local.md`（**密码只在本机安全文件，不进 Git**）。
2. 企微自建 H5 `/wecom_h5` 的四个入口、体验账号角色与操作步骤（Mock 模式可直接选成员）。
3. 企业微信 AI 机器人入口、可复制的测试对话指令与 Excel 模板（`docs/product/samples/采购入库模板.xlsx`）。
4. 四类销售订单、生产工单、Job Card、采购入库等真实测试单号及追溯路径（SAL-ORD-2026-00001~00005、MFG-WO-2026-00001/00002、PO-JOB00001~00004、MAT-PRE-2026-00001~00015、CRM-LEAD-2026-00001~00009）。
5. 每个角色与渠道的允许/拒绝用例，库存变动前后数量（36→41，一次）。
6. 未实现/不做/待用户排序的 Backlog：`docs/product/BACKLOG.md`。

**最终只有全部核心联合场景在真实企业微信通道下通过，才能标记 V1 三入口交付完成。**
局部模块已独立标记 LOCAL_PASS（BUILD-10/20/30/40/50/60/70），不必等待所有外部资源才开发。
