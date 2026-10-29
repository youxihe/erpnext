# BUILD-70 — 三入口联合验收（证据）

- 日期：2026-10-29
- 分支：`product/erpnext-wecom-ai-v1-20261029`
- 站点：`erpnext-poc.localhost`（宿主机 http://127.0.0.1:18000），公司 昆山启程智能设备有限公司
- 结论：**LOCAL_PASS（三入口 31/31 + 重启复测 24/24 + 快照比对 9/9）／REAL_WECOM_BLOCKED（真实企微待外部授权）**

> 按验收约定：模拟环境通过不算「已上线」。真实企微真人 UAT 未做之前，V1 不标整体完成。

---

## 1. 三个入口是三条真实通道，不是同一个调用换皮

| 入口 | 通道实现 | 本轮如何验证 |
|---|---|---|
| **中文 ERP PC** | 容器内直连同一个 ERPNext Site（等价 PC 界面读写） | 脚本内 `frappe` 读取/写入，同一事务外的真实 DB |
| **企微自建 H5** | 企微 OAuth 免登 → 真实 `sid` 会话 → 取 `/wecom_h5` 页面 CSRF → 调 `/api/method/cn_mfg_poc.api.*` | `h5_login()` 完整走完免登链，并用 `frappe.auth.get_logged_user` 确认不是 Guest |
| **企微 AI 机器人** | HMAC 签名通道（`X-Cn-Bot-*`）→ `wecom_userid` 换 ERP 身份 → `/api/method/cn_mfg_poc.bot*.*` | `bot_call()` 构造签名，与 Node 适配器同一份算法 |

脚本：`product/scripts/build70_cross.py`（容器内 `env/bin/python`）

---

## 2. 联合场景结果：31/31

日志：`docs/product/evidence/build70-cross.log`

| 场景 | 断言 | 结果 | 关键数据 |
|---|---|---|---|
| 准备 | P0 三名成员绑定自举 | PASS | ligong / wangming-wx / zhangsan |
| 准备 | P0 车间任务分配李工 | PASS | PO-JOB00004 employees=[HR-EMP-00001] |
| 身份 | J1 三入口映射到同一 ERP 用户 | PASS | PC=H5=Bot=`ligong@erpnext-poc.localhost` |
| 身份 | J2 PC 与 Bot 角色集合一致 | PASS | All/Desk User/Employee/Guest/Manufacturing User |
| 报备 | J3 Bot 生成待确认报备草稿 | PASS | BD-00028 |
| 报备 | J4 确认后 PC 存在正式单且归属本人 | PASS | **CRM-LEAD-2026-00009**，owner=wangming |
| 报备 | J5 H5 报备同一客户被查重拦截 | PASS | 回带同一单号，三入口共享一套数据 |
| 订单 | J6 Bot 与 PC 订单状态/金额一致 | PASS | SAL-ORD-2026-00005 · To Deliver and Bill · 1800.0 |
| 订单 | J7 H5 与 PC 订单状态/金额一致 | PASS | 同上 |
| 订单 | J8 越权订单：Bot 拒绝 | PASS | PERMISSION_DENIED |
| 订单 | J9 越权订单：H5 拒绝 | PASS | 403 |
| 车间 | J10 H5 本人报工成功 | PASS | PO-JOB00004 → Work In Progress 0.5/1.0 |
| 车间 | J11 Bot 完工数 == PC | PASS | 0.5 == 0.5 |
| 车间 | J12 H5 完工数 == PC | PASS | 0.5 == 0.5 |
| 库存 | J13 Bot 库存 == PC Bin | PASS | 原材料仓 35 / 在制仓 1 |
| 库存 | J14 H5 库存 == PC Bin | PASS | 同上 |
| 库存 | J15 无库存角色（销售）：Bot 拒绝 | PASS | PERMISSION_DENIED |
| 库存 | J16 无库存角色（销售）：H5 拒绝 | PASS | 403 |
| 入库 | J17 Excel 解析生成待确认草稿 | PASS | PID-00029 |
| 入库 | J18 预览阶段库存零变化 | PASS | 36.0 → 36.0 |
| 入库 | J19 确认后生成正式采购入库单 | PASS | **MAT-PRE-2026-00015**，36.0 → 41.0 |
| 入库 | J20 库存增量 == 入库单数量（一次过账） | PASS | Δ库存 5.0 == 单据 5.0 |
| 入库 | J21 重复确认不重复入库 | PASS | 41.0 → 41.0 |
| 入库 | J22 H5 库存 == PC（入库后） | PASS | 41.0 == 41.0 |
| 撤权 | J23 Bot：停用后身份不可用 | PASS | USER_DISABLED |
| 撤权 | J24 H5：停用后旧会话被拒 | PASS | 401 |
| 撤权 | J25 H5：停用后无法重新免登 | PASS | 403（回调被拒） |
| 撤权 | J26 Bot：停用后业务查询被拒 | PASS | USER_DISABLED |
| 撤权 | J27 恢复启用后 Bot 与 H5 均恢复 | PASS | Bot=ligong / H5=ok |

---

## 3. 部署与恢复：容器重启后无丢单、无重复过账

- 命令：`docker restart poc-frappe` → `rm -f run/*.pid` → `bash /workspace/scripts/poc-start.sh`
- 复测：`env/bin/python /workspace/build70_cross.py --after-restart` → **24/24**
  日志 `docs/product/evidence/build70-cross-restart.log`
- 快照比对：`product/scripts/build70_snapshot.py before/after` → **9/9 一致**
  日志 `docs/product/evidence/build70-restart-diff.log`

| 项 | 结果 |
|---|---|
| 销售订单 / 报备单 / 采购入库单 / 生产工单 / 车间任务单 | 全部一致 |
| SENSOR / FASTENER 库存 | 一致 |
| Job Card 完工数 | 一致 |
| 企微身份绑定 | 一致 |
| 机器人通道 | 重启后恢复（whoami 正常） |
| H5 | 重启后仍可查本人任务 |

---

## 4. 本轮真实写入的单据（可到 PC/H5 逐一核对）

| 类型 | 单据号 | 状态 | 说明 |
|---|---|---|---|
| 客户报备单 | CRM-LEAD-2026-00009 | Open | 机器人报备 → 王明确认 → PC/H5 可见 |
| 采购入库单 | MAT-PRE-2026-00015 | 已提交 | 机器人 Excel 入库 → SENSOR 36 → 41（+5，一次） |
| 采购入库草稿 | PID-00029 | Confirmed | 预览阶段零库存变化 |
| 报备草稿 | BD-00028 | Confirmed | 已转正式 Lead |
| 车间任务 | PO-JOB00004 | Work In Progress | H5 报工 0.5/1.0，PC 与 Bot 同步 |

历史可追溯单据（前序任务产生）：SAL-ORD-2026-00001~00005、MFG-WO-2026-00001/00002、
PO-JOB00001~00004、MAT-PRE-2026-00001~00015、CRM-LEAD-2026-00001~00009。

---

## 5. 本轮发现并修复的问题

| # | 问题 | 处理 |
|---|---|---|
| 1 | 机器人网关账号实际只有 `All/Guest` 角色，无法调管理类接口 | 联合验收脚本改用管理员 Token 调通讯录同步；网关保持最小权限（业务接口内部自行换身份） |
| 2 | 脚本内 DB 事务快照读不到 web 进程提交的变更（PC 侧读数滞后） | 增加 `refresh()`：每次 HTTP 写后结束事务再读，PC 侧读数与 H5/Bot 对齐 |
| 3 | 测试脚本把 Frappe 为 Guest 下发的 `sid` Cookie 误判为「免登成功」 | `h5_login()` 增加 `frappe.auth.get_logged_user` 校验，确认会话身份非 Guest（产品侧回调本就返回 403，非产品缺陷） |
| 4 | `frappe.db.get_value` 不支持 `sum()` 字符串字段 | 改用 `frappe.db.sql` |
| 5 | 撤销权限时 ORM 写 `tabUser` 触发 deadlock | 改用 SQL + 重试 |

---

## 6. 状态与阻塞项

- 本地：**LOCAL_PASS**
- 真实企业微信：**REAL_WECOM_BLOCKED**。需用户提供（详见 `docs/product/evidence/BUILD-30.md` 与 BACKLOG）：
  1. 企业微信 CorpID
  2. 自建应用 AgentID + Secret（填 WeCom Settings 的密码字段）
  3. 可信 HTTPS 回调域名
  4. 通讯录授权 + Bot 接收消息/文件权限
