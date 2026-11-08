# BUILD-94 轻制造分角色联合验收与交接

- 日期：2026-11-08
- 分支：`product/erpnext-wecom-ai-v1-20261029`
- 范围：一笔**新订单**走完整链路，每步由对应岗位操作；两名生产人员完成九阶段任务；
  验证「任务完成 ≠ 库存入库」、四类订单不回退、越权与重复写入被拒、PC/H5/Bot 同一数据。
- 关联文件：`docs/product/UAT_BUILD94.md`（一页角色 UAT）、`build94-execute.json`、
  `build94-verify.json`、`build94-stock-trace.json`。

## 1. 结论

一笔整机订单在 6 个岗位接力下走完「销售→工艺→采购→仓库→生产→入库→发货→财务」，
库存变动全部由 ERPNext 原生单据产生：

> 85（BUILD-93 结束）→ 86（采购入库）→ 92（领料 6 条）→ **92（9 项任务全部完成，不动库存）**
> → 96（Manufacture 完工入库 4 条）→ 97（一次发货 1 条）

九项固定任务由**两名**生产人员（李工 H5、刘工 PC）全部完成后，成品仓仍为 0、`Stock Ledger Entry`
仍是 92 条；成品仓 +1 只发生在仓库提交原生 `MAT-STE-2026-00013` 的那一刻。这是本轮最关键的验收点。

## 2. 真实单据链（UAT 订单 `SAL-ORD-2026-00008`）

| 环节 | 岗位 | 单据 | 关键事实 |
| --- | --- | --- | --- |
| 销售下单 | 销售 王明 | `SAL-ORD-2026-00008` | 生产类，ASSY-X1 ×1，¥5000，交期 2026-11-22，`per_delivered=100%`、`per_billed=100%`、`Completed` |
| 订单专属 BOM | 工艺 刘工 | `BOM-ASSY-X1-004` | 复制自无工序版本，`is_default=0`，标准 `BOM-ASSY-X1-001` 未改 |
| 生产项目 | 生产 刘工 | `PROJ-0005` | 九阶段模板，9 个 Task |
| 任务分派 | 生产 刘工 | `TASK-2026-00046~00054` | 00046/47/48 → 李工；00049~00054 → 刘工 |
| 采购申请 | 采购 成工 | `MAT-MR-2026-00003` | RACK 缺 2 |
| 采购订单 | 采购 成工 | `PUR-ORD-2026-00003` | 昆山精工零部件 |
| 采购入库 | 仓库 张工 | `MAT-PRE-2026-00017` | RACK +2（1 条 SLE） |
| 工单 | 生产 刘工 | `MFG-WO-2026-00005` | `skip_transfer=0`，Job Card 0 张 |
| 领料 | 仓库 张工 | `MAT-STE-2026-00012` | 原材料仓 → 生产在制仓，6 条 SLE |
| 完工入库 | 仓库 张工 | `MAT-STE-2026-00013` | 3 条耗料 + 1 条成品，成品仓 0→1 |
| 发货 | 销售 王明 | `MAT-DN-2026-00006` | 单张 DN，成品仓 1→0 |
| 开票 / 收款 | 财务 周会计 | `ACC-SINV-2026-00007` / `ACC-PAY-2026-00007` | 应收清零 |

库存流水核对（`build94-stock-trace.json`）：本单共 **12 条** SLE，全部来自上表 4 张库存单据；
全站 SLE 总数 97，Bin 与 SLE 汇总一致（成品仓 0）。

## 3. 验收结果

| 套件 | 结果 | 证据 |
| --- | --- | --- |
| 分角色全链路执行 | **12/12** | `build94-execute.json` |
| 联合验收断言（含 HTTP / Bot / 负例） | **27/27** | `build94-verify.json` |
| 库存流水回溯 | 本单 12 条，全部有原生凭证 | `build94-stock-trace.json` |
| 回归 BUILD-90 | 7/7 | 重跑（脚本已改为凭证判定） |
| 回归 BUILD-91 服务端 / HTTP | 27/27 / 24/24 | 重跑 |
| 回归 BUILD-92 执行 / 服务端 / HTTP | 15/15 / 26/26 / 44/44 | 重跑（BOM 取订单自身 `bom_no`） |
| 回归 BUILD-93 服务端 / HTTP | 27/27 / 18/18 | 重跑 |
| 幂等复跑 BUILD-94 | 12/12（SLE 97→97、Bin 不变） | 重跑 |

### 3.1 关键断言

1. **任务与库存解耦**：9 项 `production_status=已完成`、`completed_on/completed_by` 齐全，
   成品仓 0，SLE 92→92；`Manufacture` 后成品仓 0→1、SLE 92→96。
2. **两名生产人员**：李工（`ligong@`）与刘工（`liugong@`）分别完成 3 项 / 6 项，互不代改。
3. **四类订单不回退**：生产 5 / 耗材 1 / 零部件 1 / 服务 1 张已提交；服务单 0 工单、0 库存事务；
   耗材/零部件 0 工单、0 项目。
4. **越权拒绝**：改他人任务、销售建项目、销售读全局缺料、仓库读车间任务（只返回本人 0 项）。
5. **重复写入不重复过账**：完工入库单与发货单二次 `submit` 后 SLE 均为 97→97、成品仓仍 0；
   重复生成项目 `replayed=true` 且任务仍 9 个；同一任务重复完成不新增流水。
6. **三入口一致**：刘工 PC 与 Bot 都看到同一批 37 项任务、本单 9 项已完成；
   H5 通过真实 HTTP POST 写备注后，PC 与 Bot 立即读到同一条备注；
   Bot 订单进度与 PC 概览的 `total/completed/produced_qty/once_delivery` 全部相等。
7. **Bin 与 SLE 对账**：成品仓 Bin 0 = SLE 汇总 0。

## 4. 本次代码改动

| 文件 | 改动 |
| --- | --- |
| `product/scripts/build94_execute.py` | 新增：分角色全链路执行（新订单、九阶段、双人完成、Gate、入库、发货、财务），幂等 |
| `product/scripts/build94_verify.py` | 新增：27 项联合验收（单据链、Gate、四类订单、负例、重复写入、三入口一致、对账） |
| `product/scripts/build94_stock_trace.py` | 新增：按单据回溯库存流水，区分「首跑增量」与「幂等复跑」 |
| `product/scripts/build90_native_verify.py` | 回归口径改为凭证判定（原为一次性增量断言，重跑会误判回退） |
| `product/scripts/build92_execute.py` | 重跑时改用订单自身 `bom_no`，避免选到后续订单新建的 BOM |
| `docs/product/UAT_BUILD94.md` | 新增一页角色 UAT |

不改动任何历史 PASS 证据；BUILD-90/92 的原始证据保持原样，本次只让脚本可重复执行。

## 5. 交接：谁在哪儿做什么

| 岗位 | 账号 | 入口 | 日常动作 |
| --- | --- | --- | --- |
| 销售 | `wangming@` | `/cn_portal` → 客户与销售 | 四类订单下单、看订单执行概览、发起发货 |
| 工艺/生产经理 | `liugong@` | `/cn_portal` → 设计与生产 → 我的任务 / 订单生产进度 | 建生产项目、分派任务、改目标日、异常转「异常」 |
| 车间工人 | `ligong@` | `/wecom_h5` → 我的任务；或机器人 | 只更新本人任务状态/备注/目标日 |
| 采购 | `chengong@` | `/cn_portal` → 采购 | 缺料 → 采购申请 → 采购订单 |
| 仓库 | `zhanggong@` | `/cn_portal` → 库存 | 采购入库、领料、Manufacture 完工入库、发货 |
| 财务 | `zhoukaiji@` | `/cn_portal` → 财务 | 开票、收款、应收核对 |

## 6. 未完成与阻断（交接必须讲清）

1. **真实企业微信 UAT 仍阻断**：`REAL_WECOM_BLOCKED`。需要客户提供 `CorpID`、`AgentID + Secret`、
   可信 HTTPS 回调域名、通讯录授权、机器人消息与文件权限。本地 H5/机器人走 Mock 与 Token 会话，
   不能替代真人企微验收。
2. **企微成员与生产负责人绑定**是前置条件：`ligong` → 李工、`liugong` → 刘工。绑错或没绑，
   员工在 H5/机器人里就会「看不到任务」（`LM93-01`）。
3. **生产在制仓历史余料** `RACK 2 / SENSOR 1 / FASTENER 4`（BUILD-90 两段式流转遗留），
   本轮未清理，需客户确认是否做期初调整（`LM93-04`、`LM94-03`）。
4. **附件上传**（`production_attachment`）未接通 H5/机器人文件通道（`LM93-02`）。
5. **缺料只算单层 BOM**，多层/替代料/合单采购归 `BOM-01`（`LM93-03`）。
6. **通知邮件**：站点未配置默认发件邮箱时，ERPNext 原生 Notification 会抛
   `OutgoingEmailError`（本轮创建采购申请时在 Error Log 出现），不影响单据落库，但上线前需配置（`LM94-02`）。
7. **线上环境未同步本次增量**：`https://d.urlxl.cn` 仍是 BUILD-80 基线；本次 BUILD-90~94 的代码与
   DocType/自定义字段需按部署文档重放（`bench migrate` 前须先处理表名大小写补丁），见 `LM94-01`。

## 7. 复现

```bash
docker exec poc-frappe sh -c 'cd /workspace/development/frappe-bench/sites && \
  exec /workspace/development/frappe-bench/env/bin/python /hostshare/build94_execute.py'
docker exec poc-frappe sh -c 'cd /workspace/development/frappe-bench/sites && \
  exec /workspace/development/frappe-bench/env/bin/python /hostshare/build94_verify.py'
docker exec poc-frappe sh -c 'cd /workspace/development/frappe-bench/sites && \
  exec /workspace/development/frappe-bench/env/bin/python /hostshare/build94_stock_trace.py'
```
