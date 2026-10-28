# BUILD-10 — ERP PC 核心模块补齐

日期：2026-10-29 ｜ 分支：`product/erpnext-wecom-ai-v1-20261029`
结论：**PASS**。中文 PC 七角色入口可用，新增「客户报备」闭环与「我的车间任务」，14 项权限探针全部符合预期，四类订单未回退。

## 1. 实现内容（最小改动，全部原生或入自有 App）

| 项 | 实现 | 位置 |
|---|---|---|
| 客户报备 | 复用原生 Lead（销售线索）：菜单改名「客户报备」；报备=建 Lead（客户+联系人+电话+报备人+状态），转客户用原生 `make_customer` | 工作台「客户与销售」fixtures + 业务脚本 |
| 我的任务 | 标准脚本报表「我的车间任务」（CN MFG POC 模块）：服务端按 `Employee.user_id = 当前登录人` 过滤 Job Card Time Log；管理员/系统管理可见全部；角色=Manufacturing User/Manager/System Manager | `poc/apps/cn_mfg_poc/.../report/我的车间任务/`（Git 携带） |
| 工作台入口 | 设计与生产·生产执行卡新增「我的车间任务」报表链接；客户与销售菜单「销售线索」→「客户报备」 | Workspace fixtures（DB+repo 同步） |
| 其余模块 | 全部复用原生入口（见 BUILD-00 表），未新写 | — |

## 2. 真实业务动作与单号（可点击复核）

| 动作 | 单号 | 结果 |
|---|---|---|
| 补料入库（RACK 2 / SENSOR 1） | MAT-STE-2026-00005 / 00006 | 原材料仓 RACK 2、SENSOR 1 |
| 王明报备客户 | **CRM-LEAD-2026-00001** 宁波海天精工股份有限公司（周主管 13800001111，报备人 wangming） | 状态已转化 |
| 报备转正式客户 | Customer **宁波海天精工股份有限公司** | 客户数 1→2 |
| 刘工建工单 | **MFG-WO-2026-00002**（ASSY-X1 ×1） | 自动生成 PO-JOB00003 装配 / PO-JOB00004 检验 |
| 领料 | MAT-STE-2026-00007 | 原材料仓 → 生产在制仓（RACK 2 / SENSOR 1 / FASTENER 4） |
| **李工更新任务进度** | PO-JOB00003 | start_timer → complete 0.5（pending 0.5）→ 状态 **Work In Progress**，0.5/1 台，用时 30 分钟 |

四类订单复查：SAL-ORD-2026-00001～00004 状态、交付/开票百分比与 POC-06 收尾一致，无回退。

## 3. 权限探针（product/scripts/build10_permissions.py，14/14 PASS）

正例 6 项：销售建报备、制造员工写任务单、采购读采购单、仓储建库存过账、财务读总账、制造经理建工单 — 全部放行。
负例 8 项：制造员工建报备/建客户/读总账、销售读工单/读任务单、财务建库存过账、采购开销售发票、仓储建报备 — **全部 `has_permission=False` 拒绝**。
UI 级：李工直链 `/app/客户与销售` → 页面「没有权限」弹窗（build-10-li-no-sales.png）。
报表级：李工查「我的车间任务」只见本人 2 条（PO-JOB00001 完成 2/2、PO-JOB00003 进行中 0.5/1）；王明/周会计等无 Manufacturing 角色访问报表直接 `PermissionError`。

## 4. 操作路径（验收点击）

- 王明：登录 → 客户与销售 → 客户报备 → 新建（客户/联系人/电话/负责人/状态）→ 保存 → 菜单「客户」可见宁波海天精工。
- 李工：登录 → 设计与生产 → 我的车间任务 → 看本人任务与进度 → 打开任务单可继续报工。
- 刘工：设计与生产 → 生产工单 → 新建（选 BOM-ASSY-X1-001）→ 提交自动生成任务单。
- 陈工/张工/周会计/赵经理：各自工作台入口见截图 build-10-chen/zhang/zhou/zhao-ws.png。

## 5. 截图

`docs/product/evidence/`：build-00-home、build-10-li-ws、build-10-li-mytasks、build-10-li-no-sales、build-10-wang-ws、build-10-wang-lead、build-10-wang-customer、build-10-chen-ws、build-10-zhang-ws、build-10-zhou-ws、build-10-zhao-ws。

## 6. 差距与登记（不阻断）

- Job Card 时间表存在 `employee`（指派多选）与 `time_logs`（实际工时）两个同子表字段，报表已按 `parentfield='time_logs'` 过滤；POC 旧数据留下的零值行已核查无影响（OBS-10-01，S2）。
- 报表角色暂不含仓储（张工非车间人员）；如需仓储看任务，加角色即可（S2）。
- 服务订单 To Deliver 展示等既定 BACKLOG 不变。

## 7. 复测方式

```bash
docker cp product/scripts/build10_actions.py poc-frappe:/tmp/  # 幂等重跑，应全 [跳过]
docker exec poc-frappe .../python /tmp/build10_actions.py
docker cp product/scripts/build10_permissions.py poc-frappe:/tmp/ && docker exec ... python /tmp/build10_permissions.py
# UI：http://erpnext-poc.localhost:18000 → 各账号（密码 D:\ERP\poc\CREDENTIALS.local.md）
```
