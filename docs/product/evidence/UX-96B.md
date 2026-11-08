# UX-96B BOM 与销售订单：显式确认 + 双向引用

- 日期：2026-11-08
- 分支：`product/erpnext-wecom-ai-v1-20261029`
- 站点：本地 `erpnext-poc.localhost`（Docker `poc-frappe`）→ 线上 `https://d.urlxl.cn`
- 关联任务：`docs/product/tasks/UX-96B.md`
- 关联文件：`cn_mfg_poc/bom_link.py`、`cn_mfg_poc/order_execution.py`、
  `cn_mfg_poc/public/js/sales_order_bom.js`、`cn_mfg_poc/public/js/bom_references.js`、
  `cn_mfg_poc/www/order_execution.html`、`cn_mfg_poc/patches/v0_0_4/setup_bom_ux.py`、
  `cn_mfg_poc/patches/v0_0_5/setup_bom_confirm_field.py`

## 1. 结论

BOM 从「订单行里藏着一个英文 BOM No 字段」变成**可显式确认、可反向追溯**的两个方向：

- 正向：销售订单草稿行点「选择本单 BOM」→ 只列同产品/已提交/有效 BOM → 写入
  `Sales Order Item.bom_no`；错配、未提交、已停用过期 BOM 一律服务端拒绝。
- 展示：订单执行概览严格区分**产品编码 / 本单已确认 BOM / 产品默认建议 BOM**；
  默认 BOM 只在「建议」列出现，不再冒充已确认。
- 反向：BOM 表单「引用关系」按查看者真实权限列出显式引用本 BOM 的销售订单行与生产工单。

线上真实角色实测后端 **38/38**、浏览器 **29/29**、本地回归 **42/42**，0 error；
BOM 选用与反查全过程 `sle=52 / bin_qty=135 / bin_rows=7` 前后一致（无库存过账）。

## 2. 三态模型（本轮新增的关键设计）

验收中发现一个**产品级隐患**：ERPNext 原生 `get_item_details()` 会把
`Item.default_bom` 自动写进新订单行的 `Sales Order Item.bom_no`
（本地/线上实测：新建 ASSY-X1 草稿行插入后 `bom_no=BOM-ASSY-X1-001`，用户什么都没选）。
如果按「`bom_no` 有值 = 本单已确认」判定，就等于**用默认 BOM 冒充已确认**，正是本任务
明令禁止的行为。

因此新增隐藏字段 `Sales Order Item.custom_bom_confirmed`（Check，`hidden=1`、`read_only=1`），
由 `bom_link.validate_sales_order_bom` 在草稿阶段落标记：

| 判定顺序 | 条件 | 结果 |
| --- | --- | --- |
| 1 | 订单已提交（`docstatus=1`） | `explicit` —— 提交即锁定，生产已按它排程 |
| 2 | 人工确认标记 = 1（界面选择 / 手工改 `bom_no` / API 改值） | `explicit` |
| 3 | 产品无默认 BOM，或 `bom_no` 与默认不同（默认值不可能被自动带入成非默认） | `explicit` |
| 4 | 否则 `bom_no` 只是系统带入的默认值 | `default_suggested`（未确认，`bom_no` 对外置空，原值进 `bom_carried`） |
| 5 | 行内无 BOM 且产品无默认 | `none` |

概览侧对应字段：`item_code`（产品编码）、`bom_no`（**只暴露已确认**）、`default_bom`
（默认建议）、`bom_carried`（系统带入值，仅供排查）、`bom_state`、`bom_confirmed`；
`bom_summary` 额外返回 `unconfirmed_items`、`carried_items`、`all_confirmed`。

反查也按同一规则过滤：`bom_references()` 只统计 `state == explicit` 的行，
默认带入值与草稿未确认值都不算引用，避免「一个默认 BOM 被算成全公司在用」。

## 3. 线上验收（https://d.urlxl.cn）

脚本 `poc/deploy/online_verify96.py`，结果 `poc/deploy/online-ux96-verify.json`（38/38 PASS）。

| 用例 | 实测 |
| --- | --- |
| B1 草稿行可选 BOM | `ASSY-X1` 返回 `BOM-ASSY-X1-001 / BOM-ASSY-X1-002`，`default_bom=001` |
| B2 错配拒绝 | `FLANGE-ASSY` 行选 `BOM-ASSY-X1-001` → `ValidationError: 第 1 行物料 FLANGE-ASSY 与所选 BOM BOM-ASSY-X1-001 的产品 ASSY-X1 不一致` |
| B3 草稿显式选用 | `SAL-ORD-2026-00008` → `bom_no=BOM-ASSY-X1-002` 保存成功 |
| B4 未提交/停用拒绝 | 选草稿态 `BOM-FLANGE-ASSY-001` → `ValidationError: 未提交或已停用，不能选用` |
| B5 已确认订单 | `SAL-ORD-2026-00006`：`bom_state=explicit`、`bom_no=001` |
| B6 仅默认 BOM | `SAL-ORD-2026-00001`：`bom_state=default_suggested`、`bom_no=None`、`unconfirmed_items=['ASSY-X1']` |
| B8b/B8c 自动带入 | 草稿 `SAL-ORD-2026-00010` 行 `bom_no=001` 且 `custom_bom_confirmed=0` → 概览 `bom_state=default_suggested`、`bom_carried=001`、`bom_no=None` |
| B8d 反查排除带入值 | `BOM-ASSY-X1-001` 反查**不出现** `00010`（只出现已提交的 `00006`） |
| B9 受控变更 | 直接调用校验：`Sales Order SAL-ORD-2026-00006 已提交，不能直接把第 1 行 BOM 从 BOM-ASSY-X1-001 改为 BOM-ASSY-X1-002；请走受控变更…` |
| B10 保存兜底 | 提交后改 `bom_no` 走 `save()` → 原生 `UpdateAfterSubmitError` 拦截 |
| B11/B12 反查 | `BOM-ASSY-X1-001` → 销售订单 `SAL-ORD-2026-00006`；生产工单 `MFG-WO-2026-00001/00002/00003` |
| B14 权限过滤 | 李工（Manufacturing User，无销售订单读权限）反查：`sales_orders=[]`、`work_orders=3` |
| B15 新选用可反查 | `BOM-ASSY-X1-002` → `SAL-ORD-2026-00008` |

线上样本单据：`BOM-ASSY-X1-001`（标准）、`BOM-ASSY-X1-002`（本轮为「多选项/受控变更」
验收新建的替代版本，已提交、`is_default=0`）、`BOM-FLANGE-ASSY-001`（草稿，用于负例）、
`SAL-ORD-2026-00006`（已确认）、`SAL-ORD-2026-00001`（仅默认建议）、
`SAL-ORD-2026-00008`（选 002）、`SAL-ORD-2026-00010`（UI 验收草稿）。

## 4. 浏览器点击路径（截图证据，本机留档）

1. 王明（销售经理）打开 `SAL-ORD-2026-00010` 草稿：物料表出现「本单 BOM」列，
   顶部黄条「有 1 行尚未确认本单 BOM…请点「选择本单 BOM」」。
   → `poc/deploy/online_shots/ux96b_04_so_before.png`
2. 物料清单 → 选择本单 BOM：弹窗列出 `BOM-ASSY-X1-001 / 002`。→ `ux96b_05_choose_dialog.png`
3. 确认选用 → 顶部转蓝「全部物料行已选用本单 BOM」；`Ctrl+S` 保存并刷新后仍为已确认，
   表格显示所选 BOM。→ `ux96b_06_so_after.png`
4. 赵经理打开 `/order_execution`：
   `SAL-ORD-2026-00001` → 黄条「本单尚未确认 BOM：ASSY-X1 未在订单行确认 BOM…
   不代表本单已确认」→ `ux96b_07_summary_unconfirmed.png`；
   `SAL-ORD-2026-00006` → 蓝条「本单 BOM 已确认：BOM-ASSY-X1-001」→ `ux96b_08_summary_confirmed.png`
5. BOM `BOM-ASSY-X1-001` → 「引用关系」：销售订单行 2 条（`00010` 草稿、`00006` 已完成）、
   生产工单 3 条（`MFG-WO-2026-00003/00002/00001`），底部注明「仅显示当前账号有权限查看的订单与工单」。
   → `ux96b_09_bom_refs.png`

## 5. 本地回归

`scripts/release96_verify.py` **42/42 PASS**，其中 UX-96B 覆盖：
可选 BOM 列表、**自动带入默认 BOM 不算已确认**（新增）、人工确认后转 `explicit`（新增）、
错配拒绝、两单共用同一 BOM、已确认/未确认三态、受控变更规则文案、反查只算显式、
非标订单引用独立 BOM 不影响默认、权限过滤、服务类订单不受影响、库存不变。

## 6. 本轮发现并修复的缺陷

1. **受控变更规则从未生效**：`bom_link.validate_sales_order_bom` 里误写
   `if str(bom_no) in old_values`（用 BOM 名去匹配「行名 → BOM」字典的键），条件恒假；
   线上实测 B9「未拦截」后修正为 `if row.name in old_values`，本地/线上复测均命中
   「请走受控变更」文案。此前本地用例 PASS 是因为原生 `UpdateAfterSubmitError` 兜底，
   属**假通过**，已补一条只校验规则本身的断言。
2. **默认 BOM 冒充已确认**（见 §2）：新增 `custom_bom_confirmed` 字段 + 三态判定，
   并把「系统带入值」显式展示为「未确认 / 默认带入 X」。
3. **BOM 反查虚高**：改为只统计 `explicit` 行，默认带入与草稿未确认值不再计入。

## 7. 未覆盖 / 风险

- 之前已存在的草稿订单（如 `SAL-ORD-2026-00008`、`00010`）是本轮上线**前**创建的，
  其 `custom_bom_confirmed` 默认 0；已提交历史订单不受影响（按 `docstatus` 判 `explicit`）。
  需要时可点一次「选择本单 BOM」补确认。
- 物料表「本单 BOM」列仍显示系统带入的默认值（列宽截断），靠顶部黄条与概览页
  「未确认 / 默认带入」标签区分；若要求列内即显示「未确认」，需加 grid formatter，登记 BACKLOG。
- 一个 BOM 被多张订单共用时反查只列订单与行号，未做汇总统计（当前需求未要求）。

## 8. 证据清单

- 脚本：`poc/deploy/online_verify96.py`、`poc/deploy/online_ui96.py`、
  `poc/deploy/mk_ui_draft.py`、`poc/deploy/reset_ui_draft.py`
- JSON/日志：`poc/deploy/online-ux96-verify.json`、`poc/deploy/online-final2.txt`
- 截图：`poc/deploy/online_shots/ux96b_04_so_before.png`、`ux96b_05_choose_dialog.png`、
  `ux96b_06_so_after.png`、`ux96b_07_summary_unconfirmed.png`、
  `ux96b_08_summary_confirmed.png`、`ux96b_09_bom_refs.png`
- 线上发布：`/app/backup/ux96/20261108-220817`（DB+应用）、`/app/backup/ux96/fix2-20261108-222158`；
  补丁输出 `BOM_UX_PROPERTY_SETTERS_CREATED: ['Sales Order Item-bom_no-label', '-in_list_view', '-columns']`、
  `BOM_CONFIRM_FIELD_CREATED custom_bom_confirmed`
