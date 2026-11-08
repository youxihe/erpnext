# BUILD-93 三入口接力：H5 / 机器人接通 Project Task 与订单汇总

- 日期：2026-11-08
- 分支：`product/erpnext-wecom-ai-v1-20261029`
- 范围：不新增业务权威数据、不改 ERPNext 核心；PC `/cn_portal`、H5 `/wecom_h5`、机器人 HMAC 通道
  三处共用同一套受控 API 与同一份 ERPNext 真实单据。
- 环境：本地 POC Site `erpnext-poc.localhost`（ERPNext 16.52.1 / Frappe 16.53.0 / Python 3.14.9），
  容器 `poc-frappe`，宿主机 `http://127.0.0.1:18000`。

## 1. 一句话结论

九阶段生产任务、订单执行概览、BOM 缺料三个能力已做成**同一组服务端契约**，PC / H5 / 机器人调用的是同一函数、
同一权限判断、同一批 ERPNext 记录。李工（企微 `ligong`）在 H5 与机器人里看到的任务数、目标日期、逾期状态、
实物完工数量与 PC 完全一致；他更新任务后 PC 立即可见，且库存分文未动。

## 2. 轻量契约（唯一入口）

| 契约名 | 真实端点 | 方法 | 作用 | 授权 |
| --- | --- | --- | --- | --- |
| `orders.summary` | `cn_mfg_poc.api.orders_summary` | GET | 无单号→可见生产订单列表；带单号→订单执行概览 | 单据读权限 / 主管角色 / 该单任务负责人 |
| `production.tasks.mine` | `cn_mfg_poc.api.production_tasks_mine` | GET | 本人 Project Task + 临期/逾期只读判定 | Employee / Manufacturing User 及以上 |
| `production.tasks.update` | `cn_mfg_poc.api.production_tasks_update` | POST | 本人写状态 / 备注 / 附件 / 目标日期 | 必须是该任务 `production_owner` |
| `materials.shortage` | `cn_mfg_poc.api.materials_shortage` | GET | 未完成生产订单的 BOM 缺料 | 生产/仓库/采购/系统；普通生产人员仅限本人订单 |

自检端点：`cn_mfg_poc.api.contracts`（返回契约名到真实端点的映射 + 当前用户），便于 H5/机器人启动时对齐版本。

### 不变量（写进代码与话术）

- `Task.status` / `production_status` 只表示过程，**不写库存、不生成 Stock Entry**。
- 实物完工量只取 `Work Order.produced_qty` 与原生 `Stock Entry`，绝不从任务完成数推算。
- 非财务角色拿到的 `order.grand_total` 与单据行金额一律为 `null`。
- 机器人话术末尾固定附「任务状态只反映过程；完工入库与发货以原生 Stock Entry / Delivery Note 为唯一凭据」。

## 3. 本次落地的真实数据

为验证「真实缺料 + 真实任务」，新建一张**尚未采购**的生产订单（历史单据不改动）：

| 项目 | 单号 | 说明 |
| --- | --- | --- |
| 销售订单 | `SAL-ORD-2026-00007` | 生产类，ASSY-X1 ×1，¥5000，客户苏州华新装备，交期 2026-11-22，`po_no=BUILD93-DEMO` |
| 订单专属 BOM | `BOM-ASSY-X1-003` | 由 `BOM-ASSY-X1-002` 复制，无工序、`is_default=0`，标准 BOM-ASSY-X1-001 未改 |
| 生产项目 | `PROJ-0004` | `Project.sales_order` 原生回写，九阶段模板生成 |
| 生产任务 | `TASK-2026-00037` ~ `TASK-2026-00045` | 9 个固定阶段 |
| 分派 | 李工 `ligong@`：00038 机加工件加工 / 00039 内钣金焊接 / 00040 电控板组装；其余 6 项留在刘工（生产经理） | 企微 `ligong` 绑定 `ligong@` |
| 真实缺料 | `RACK` 需求 2 / 原材料仓 0 / 缺 2 | 未建采购申请与采购单，差额即全部需求 |
| 已完成对照单 | `SAL-ORD-2026-00006` | BUILD-92 全链路：1 张 DN、`per_delivered=100%`、`produced_qty=1`、Job Card 0 张 |

库存快照：`tabStock Ledger Entry` 共 **85** 条，与 BUILD-92 结束时一致；本次所有任务更新**未新增任何 SLE**。

## 4. 验收结果

| 套件 | 结果 | 证据 |
| --- | --- | --- |
| 服务端契约与权限 | **27/27** | `build93-verify.json` |
| HTTP / 页面 / 三入口 | **18/18** | `build93-http.json` |
| 机器人适配器离线（真实返回样本） | **8/8** | `build93-adapter.json`、`bot93-samples.json` |
| 回归 BUILD-91 服务端 / HTTP | 27/27 / 24/24 | 重跑原脚本 |
| 回归 BUILD-92 服务端 / HTTP | 26/26 / 44/44 | 重跑原脚本 |
| 机器人适配器工具总数 | 13（新增 3） | `node --check` + 注册断言 |

### 4.1 关键断言（全部实测，非推断）

1. 李工 7 项任务（00006 单 3 项 + 00007 单 3 项 + 00006 单已完成 1 项），`all(production_owner == 本人)`；
   机器人 `my_production_tasks` 返回同样 7 项。
2. 李工按单看 `SAL-ORD-2026-00006`：任务 9 项 / 已完成 1 / 逾期 0，`produced_qty=1`、`job_cards=0`、
   `once_delivery=true`；机器人同一订单返回同值。
3. 更新任务 `TASK-2026-00029` 为「进行中」：原生 `Task.status=Working`，`tabBin` 4 个仓快照前后完全一致。
4. 越权负例：销售读任务 403、销售代改他人任务 403、非法状态 `ValidationError`、销售读全局缺料 403、
   机器人未绑定成员 `NOT_BOUND`、机器人销售身份查任务 `PERMISSION_DENIED`。
5. 缺料真实性：`RACK` `required_qty=2 / available_now=0 / shortage=2`，与「未采购」事实一致。
6. H5 页面按角色渲染：生产人员默认 `jobs` 且有「我的生产任务」；销售无该页签、默认 `orders`。

### 4.2 三入口对应地址

| 入口 | 地址 | 说明 |
| --- | --- | --- |
| PC 统一导航 | `/cn_portal` | 「设计与生产 → 固定生产进度 → 我的任务 / 订单生产进度」 |
| PC 生产任务板 | `/production_board?view=mine` | BUILD-91 |
| PC 订单执行概览 | `/order_execution?order=SAL-ORD-2026-00007` | BUILD-92 |
| 企微 H5 | `/wecom_h5` | 「我的订单 → 看进度」「我的任务 → 状态/目标日/备注保存」 |
| 机器人 | `cn_mfg_poc.bot.order_execution` / `my_production_tasks` / `materials_shortage` | HMAC 签名 + 企微 UserID 换 ERP 身份 |

## 5. 本次代码改动

| 文件 | 改动 |
| --- | --- |
| `poc/apps/cn_mfg_poc/cn_mfg_poc/api.py` | 新增 `CONTRACTS`、`contracts()`、`orders_summary()`、`production_tasks_mine()`、`production_tasks_update()`、`materials_shortage()` |
| `poc/apps/cn_mfg_poc/cn_mfg_poc/bot.py` | 新增 `order_execution` / `my_production_tasks` / `materials_shortage` 三个白名单端点与格式化数据、`AUTHORITY_NOTE` |
| `poc/apps/cn_mfg_poc/cn_mfg_poc/order_execution.py` | 新增 `SHORTAGE_ROLES` / `SENIOR_ROLES` / `_is_order_worker()`；生产任务负责人可按单看进度；缺料按职能授权并限制可见订单 |
| `poc/apps/cn_mfg_poc/cn_mfg_poc/www/wecom_h5.html` | 「我的任务」改为 Project Task 卡片（状态下拉 + 目标日期 + 备注 + 保存）；「我的订单」增加「看进度」展开原生单据链；旧 Job Card 报工降级为可选卡片 |
| `poc/apps/cn_mfg_poc/cn_mfg_poc/www/wecom_h5.py` | 按角色计算 `can_production` / `default_tab`，非生产角色不渲染任务页签 |
| `product/adapter/erpnext-bot-tools/index.js` | 新增 3 个工具定义与 3 个话术模板，任务与实物入库分列展示 |
| `product/scripts/build93_setup.py` | 幂等准备：演示订单 + 订单专属 BOM + 九阶段项目 + 前三个工序分派李工 |
| `product/scripts/build93_verify.py` | 27 项服务端契约/权限/库存解耦/机器人一致性 |
| `product/scripts/build93_http_verify.py` | 18 项 HTTP 页面与接口权限 |
| `product/adapter/erpnext-bot-tools/build93_check.mjs` | 8 项适配器离线校验（真实返回样本驱动） |
| `product/scripts/build91_verify.py` | 回归口径修正：本人任务数由 `==1` 改为 `>=1`，允许李工同时持有其他订单任务 |

## 6. 边界与未完成

- **真实企业微信真人 UAT 仍阻断**：`REAL_WECOM_BLOCKED`。本次机器人与 H5 的身份链路走本地 Mock 与会话 Token，
  未在真实企微租户内验证 OAuth 免登、应用可见范围、消息卡片。需要客户提供 `CorpID`、`AgentID+Secret`、
  可信 HTTPS 回调域名、通讯录与文件权限。
- **附件上传未接通**：`production_attachment` 字段与接口参数已留，H5/机器人文件上传依赖企微文件权限，
  见 `LM91-03`、新增 `LM93-02`。
- **缺料只算单层 BOM**：多层、替代料、批量合单仍归 `BOM-01`。
- 生产在制仓尚有 2 件历史 `RACK` 余料（BUILD-90 两段式流转遗留，非本次重复过账），
  见 `LM93-04`，留待 BUILD-94 盘点口径确认。

## 7. 复现方式

```bash
# 1) 准备真实任务与缺料订单（幂等）
docker exec poc-frappe sh -c 'cd /workspace/development/frappe-bench/sites && \
  exec /workspace/development/frappe-bench/env/bin/python /hostshare/build93_setup.py'

# 2) 服务端 27 项
docker exec poc-frappe sh -c 'cd /workspace/development/frappe-bench/sites && \
  exec /workspace/development/frappe-bench/env/bin/python /hostshare/build93_verify.py'

# 3) HTTP 18 项
docker exec poc-frappe sh -c 'cd /workspace/development/frappe-bench/sites && \
  exec /workspace/development/frappe-bench/env/bin/python /hostshare/build93_http_verify.py'

# 4) 适配器 8 项（在 product/adapter/erpnext-bot-tools 下）
BUILD93_SAMPLES=.../bot93-samples.json BUILD93_OUT=.../build93-adapter.json node build93_check.mjs
```
