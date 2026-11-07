# BUILD-80 四类订单类型化（2026-11-07）

状态：**PASS(LOCAL)**。真实企微真人 UAT 仍为 BLOCKED，不影响本项 PC / API / Bot 本地验证结论。

## 需求与范围

用户确认 `/cn_portal` 统一导航布局可用，要求按客户原始需求继续配置「四种订单、BOM 拆分」。
两项选择结果：先做四类订单类型化；**「BOM 拆分」用户明确要求先等口径确认**，故本轮不改动任何 BOM / 工单逻辑，
已登记 BACKLOG `BOM-01`。

## 复用与增量（不重造 POC-04）

POC-04 已建 `Sales Order.business_type`（生产/耗材/零部件/服务）与 5 张样本订单。本轮只补产品化缺口：

| 项 | 之前 | 现在 |
|---|---|---|
| 字段标签 | 业务类型 | **订单类型** |
| 列表 / 筛选 | 不可见 | `in_list_view=1`、`in_standard_filter=1`，列表可见「订单类型」列 |
| 默认值 | Select 首项「生产」，新单易误判 | 首项留空，**强制四选一** |
| 分类入口 | 只有「销售订单」 | `/cn_portal`「客户与销售」新增「四类订单」分组，4 个带筛选入口 |
| 流程约束 | 无 | 服务端 `validate`：类型必填、服务类禁库存物料、耗材/零部件类禁服务项 |
| 三入口 | 仅订单详情含类型 | `my_orders` 列表 / H5 / Bot 均返回订单类型 |

## 实现文件

- `product/scripts/build80_order_types.py` — 幂等配置（字段）
- `product/scripts/build80_verify.py` — 数据 + 约束 + 三入口契约验证
- `product/scripts/build80_http_verify.py` — 真实 HTTP 负例
- `poc/apps/cn_mfg_poc/cn_mfg_poc/order_rules.py` — 服务端四类订单约束
- `hooks.py`（doc_events）、`api.py`（my_orders）、`www/wecom_h5.html`（列表显示类型）、`www/cn_portal.py`（四类菜单注入）

## 关键约束与决策

- Frappe v16 `Workspace Link.link_type` 只有 `DocType / Page / Report`；写 `URL` 会在
  `_validate_links` 报 `DocType URL not found`。因此分类入口改在 `/cn_portal` 的
  `_inject_order_types()` 虚拟注入，不改 Workspace 数据。实测
  `/desk/sales-order?business_type=生产` 会被 Frappe 列表应用为筛选条件。
- 校验挂 `doc_events.validate` 而非 Client Script，PC / H5 / Bot / REST 任一入口统一生效；
  从报价单生成的销售订单也必须显式选择订单类型。
- **生产类暂不做 BOM / 工单强校验**，避免与待确认的 BOM 口径冲突；订单行混合类型保持允许（客户已知差异）。

## 实测结果

- `build80_verify.py`：**16/16 PASS** —— 字段属性、5 张订单覆盖四类、hooks 已加载、
  3 个负例拦截（未选类型 / 服务类混入库存物料 / 耗材类混入服务项）、2 个正例可保存（生产类、服务类）、
  H5/PC 与 Bot 订单列表均返回 `business_type`。
- HTTP 负例：`frappe.client.insert` 返回 **417 ValidationError「请先选择订单类型：生产 / 耗材 / 零部件 / 服务」**，
  `_exc_source = cn_mfg_poc (app)`，证明运行中的 web 进程已加载新 hook。
- 浏览器：菜单 14 项含「四类订单」分组 4 入口；生产类列表只含 `SAL-ORD-2026-00001 / 00005`
  （「订单类型」列=生产），服务类只含 `00004`；表单显示中文标签与值；内页保持铺满。
- 样本订单分布：生产 2（00001 / 00005）、耗材 1（00002）、零部件 1（00003）、服务 1（00004）。
- 所有负例均被拦截或事务回滚，**无新增业务单据、无库存/账务变动**。

## 截图

- `cn-portal-orders-production.png`、`cn-portal-orders-service.png`、`cn-portal-orders-form.png`
