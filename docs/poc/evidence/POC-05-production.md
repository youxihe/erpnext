# POC-05 生产订单完整业务单据与库存生命周期

- 状态：**PASS**
- 执行日期：2026-10-26
- 环境：Docker 容器 `poc-frappe`，site `erpnext-poc.localhost`（宿主机 http://erpnext-poc.localhost:18000）
- 版本：ERPNext 16.52.1 / Frappe 16.53.0 / Python 3.14.9 / MariaDB 11.8
- 公司：昆山启程智能设备有限公司（币种 CNY）
- 演示客户/供应商：苏州华新装备有限公司 / 昆山精工零部件有限公司

## 1. 验收目标与结论

| 目标 | 要求 | 实测结果 |
|---|---|---|
| BOM 与销售订单关联 | 生产类订单要有 BOM，可按 BOM 展开物料与工艺 | **PASS** `BOM-ASSY-X1-001`（默认 BOM，单台成本 720 元），工单关联 `SAL-ORD-2026-00001` |
| 缺料与采购补货 | 按 BOM 净算缺料并形成采购补货 | **PASS** 净算缺 RACK 3 / SENSOR 2 → `MAT-MR-2026-00001` → `PUR-ORD-2026-00001` → `MAT-PRE-2026-00002` |
| 生产工单 + 两道工序 | 工单 ≥2 道工序，生成对应 Job Card | **PASS** `MFG-WO-2026-00001`（2 台）→ `PO-JOB00001`（装配 60min）/ `PO-JOB00002`（检验 30min） |
| 原料仓 → 在制仓领料 | 领料单真实移动库存 | **PASS** `MAT-STE-2026-00003`：RACK 4 / SENSOR 2 / FASTENER 8 由原材料仓转生产在制仓，金额 1440 |
| 完工成品入库与成本 | 成品入产成品仓，成本可勾稽 | **PASS** `MAT-STE-2026-00004`：耗料 1440 → 成品 2 台 × 720 元 = 1440（与 BOM 标准成本完全一致） |
| 交付 | 销售交货单出库 | **PASS** `MAT-DN-2026-00004`：2 台 × 8800 = 17600，产成品仓 2 → 0 |
| 开票 + 收款 | 发票与收款挂接订单 | **PASS** `ACC-SINV-2026-00002`（17600）→ `ACC-PAY-2026-00002`（现金 17600），应收余额 0，订单状态 Completed（交付 100% / 开票 100%） |

**结论：生产类订单的「接单 → 计划 → 采购补料 → 工单 → 报工 → 领料 → 完工 → 交付 → 开票 → 收款」全链路在本机真实环境跑通，全部为原生单据，无自定义代码介入业务运算。**

## 2. 单据链（可逐张打开核对）

| # | 单据类型 | 单号 | 状态 | 关键数值 |
|---|---|---|---|---|
| 1 | 销售订单 Sales Order | `SAL-ORD-2026-00001` | 已提交 / Completed | 设备装配 X1 ×2 @8800 = 17600，生产类 |
| 2 | 生产计划 Production Plan | `MFG-PP-2026-00001` | 已提交 | 计划 2 台，来源订单 SAL-ORD-2026-00001 |
| 3 | 物料申请 Material Request | `MAT-MR-2026-00001` | 已提交 | RACK 3 + SENSOR 2（采购型） |
| 4 | 采购订单 Purchase Order | `PUR-ORD-2026-00001` | 已提交 | RACK 3@200 + SENSOR 2@300 = 1200 |
| 5 | 采购入库 Purchase Receipt | `MAT-PRE-2026-00002` | 已提交 | 入库 1200，入原材料仓 - QC |
| 6 | 生产工单 Work Order | `MFG-WO-2026-00001` | 已提交 / Completed | 2 台，产出 2 台，源仓原材料仓 / 在制仓生产在制仓 / 成品仓产成品仓 |
| 7 | 生产任务单 Job Card | `PO-JOB00001` | 已提交 / Completed | 装配 60min，李工，完成 2 |
| 8 | 生产任务单 Job Card | `PO-JOB00002` | 已提交 / Completed | 检验 30min，张工，完成 2 |
| 9 | 库存移动 Stock Entry | `MAT-STE-2026-00003` | 已提交 | 工单发料 1440（原料仓 → 在制仓） |
| 10 | 库存移动 Stock Entry | `MAT-STE-2026-00004` | 已提交 | 工单入库 1440（在制仓 → 产成品仓，2 台 ×720） |
| 11 | 交货单 Delivery Note | `MAT-DN-2026-00004` | 已提交 | 2 台 ×8800 = 17600 |
| 12 | 销售发票 Sales Invoice | `ACC-SINV-2026-00002` | 已提交 / Paid | 17600，未收 0 |
| 13 | 收款单 Payment Entry | `ACC-PAY-2026-00002` | 已提交 | 现金 17600（应收账款 1 - QC → 现金 - QC） |

**作废重做记录（成本修正，见第 6 节 GAP-05-01）**：`MAT-PRE-2026-00001`、`MAT-STE-2026-00001`、`MAT-STE-2026-00002`、`MAT-DN-2026-00003`、`ACC-SINV-2026-00001`、`ACC-PAY-2026-00001` 均已作废（docstatus=2），不参与账面金额。

## 3. 主数据

**BOM `BOM-ASSY-X1-001`（默认 BOM，已提交，单台）**

| 物料 | 数量 | 单价 | 金额 |
|---|---|---|---|
| RACK 机架 | 2 件 | 200 | 400 |
| SENSOR 传感器 | 1 件 | 300 | 300 |
| FASTENER 紧固件 | 4 件 | 5 | 20 |
| **材料成本合计** | | | **720 元/台** |

| 工序 | 工位 | 标准工时 |
|---|---|---|
| 装配 | 装配工位 | 60 分钟 |
| 检验 | 检验工位 | 30 分钟 |

**缺料净算（下单前库存 → 需求 → 缺口）**

| 物料 | 2 台需求 | 下单前库存 | 缺口 | 处理 |
|---|---|---|---|---|
| RACK | 4 | 1 | 3 | 采购 3 |
| SENSOR | 2 | 0 | 2 | 采购 2 |
| FASTENER | 8 | 12 | 富余 4 | 不采购 |

**人员**：李工 `HR-EMP-00001`（装配）、张工 `HR-EMP-00002`（检验）、刘工 `HR-EMP-00003`（备用）

## 4. 库存台账（Stock Ledger Entry，可复核）

| 物料 | 仓库 | 变动 | 结存 | 单位成本 | 来源单据 |
|---|---|---|---|---|---|
| RACK | 原材料仓 - QC | 0（期初 1） | 1 | 200.00 | Stock Reconciliation MAT-RECO-2026-00005 |
| RACK | 原材料仓 - QC | +3 | 4 | 200.00 | Purchase Receipt MAT-PRE-2026-00002 |
| RACK | 原材料仓 - QC | −4 | 0 | 200.00 | Stock Entry MAT-STE-2026-00003 |
| RACK | 生产在制仓 - QC | +4 | 4 | 200.00 | Stock Entry MAT-STE-2026-00003 |
| RACK | 生产在制仓 - QC | −4 | 0 | 200.00 | Stock Entry MAT-STE-2026-00004 |
| SENSOR | 原材料仓 - QC | +2 | 2 | 300.00 | Purchase Receipt MAT-PRE-2026-00002 |
| SENSOR | 原材料仓 - QC | −2 | 0 | 300.00 | Stock Entry MAT-STE-2026-00003 |
| SENSOR | 生产在制仓 - QC | +2 / −2 | 0 | 300.00 | MAT-STE-2026-00003 / 00004 |
| FASTENER | 原材料仓 - QC | 0（期初 12） | 12 | 5.00 | Stock Reconciliation MAT-RECO-2026-00006 |
| FASTENER | 原材料仓 - QC | −8 | 4 | 5.00 | Stock Entry MAT-STE-2026-00003 |
| FASTENER | 生产在制仓 - QC | +8 / −8 | 0 | 5.00 | MAT-STE-2026-00003 / 00004 |
| **ASSY-X1** | **产成品仓 - QC** | **+2** | **2** | **720.00** | **Stock Entry MAT-STE-2026-00004（完工）** |
| **ASSY-X1** | **产成品仓 - QC** | **−2** | **0** | **720.00** | **Delivery Note MAT-DN-2026-00004** |

## 5. 财务核对

| 凭证 | 科目 | 借方 | 贷方 |
|---|---|---|---|
| ACC-SINV-2026-00002 | 应收账款 1 - QC | 17,600.00 | |
| ACC-SINV-2026-00002 | 销售 - QC | | 17,600.00 |
| ACC-PAY-2026-00002 | 现金 - QC | 17,600.00 | |
| ACC-PAY-2026-00002 | 应收账款 1 - QC | | 17,600.00 |

- 应收账款余额：**0**（全额收款）
- 销售收入累计：**17,600**
- 订单 `SAL-ORD-2026-00001`：交付 100%、开票 100%、状态 Completed
- 成本勾稽：BOM 标准成本 720 元/台 = 完工单实际单位成本 720 元/台（材料 1440 / 2 台），无差异

## 6. 已知问题与处理（GAP）

### GAP-05-01（已修复）采购建单未带单价导致成本为 0
- **现象**：首轮执行后 `ASSY-X1` 完工单位成本只有 120 元（材料 240 元），远低于 BOM 的 720 元。
- **根因**：Stage 1 建采购订单时未显式写入 `rate`，`rate` 落 0，采购入库估值为 0；RACK 因期初 1 件按 200 估值、新购 3 件按 0，加权后 50 元/件；SENSOR 全为 0。
- **影响**：只影响金额，数量与流程全部正确。
- **修复**：`poc05_costfix.py` 逆序作废（收款→发票→交货→完工→领料→入库）→ 修正 PO 单价为 RACK 200 / SENSOR 300 → 重做入库、领料、完工、交付、开票、收款。
- **验证**：修复后完工单位成本 720 元/台，与 BOM 标准成本完全一致；SLE 单位成本 200/300/5/720 全部正确。

### GAP-05-02（未修复，影响成本精度）工序成本未计入工单
- **现象**：`MFG-WO-2026-00001` 的 `total_operating_cost = 0`，两道工序 `planned_operating_cost = 0`；工单成本只有材料。
- **根因**：`装配工位` / `检验工位` 的 `hour_rate` 为 0，BOM 工序 `operating_cost` 随之为 0，工单按 BOM 复制。
- **建议修复**：给工位设小时费率（如 装配 100 元/h、检验 80 元/h），新建 BOM 版本后新建工单，工序成本即进入成品成本。
- **当前约定**：本 POC 只承诺「材料成本可勾稽」，人工/制费不计入成品成本。

### GAP-05-03（体验问题）Job Card 上员工显示为编号
- **现象**：生产任务单员工字段显示 `HR-EMP-00001`，不是「李工」。
- **根因**：Employee 命名规则为编号，Link 字段显示 name。
- **建议**：员工命名改用姓名，或在任务单列表/打印格式里改显 `employee_name`。

### 上游缺陷规避：Job Card 自动排程崩溃
- **现象**：工单提交自动生成 Job Card 时抛 `TypeError`（`adjust_start_date_for_holiday` 内对 datetime 调用 `get_time`，`2009-00-00` 解析失败）。
- **规避**：`Manufacturing Settings.disable_capacity_planning = 1`（关闭产能排程）。Job Card 仍按工序自动生成、工时与完成数量照常记录，只是不自动计算排程时段。属上游缺陷，已在 POC-01 记录的环境里可重复。

## 7. 复现步骤

容器内执行（宿主机 Git Bash，注意 `MSYS_NO_PATHCONV=1`）：

```bash
# 0) 主数据与工艺（工位/工序/员工/原料库存/BOM）
docker cp poc/scripts/poc05_prep.py    poc-frappe:/tmp/ && \
docker exec -w /workspace/development/frappe-bench poc-frappe \
  /workspace/development/frappe-bench/env/bin/python /tmp/poc05_prep.py

# 1) 生产计划 → 缺料 → 物料申请 → 采购订单 → 采购入库
docker cp poc/scripts/poc05_stage1.py  poc-frappe:/tmp/ && \
docker exec -w /workspace/development/frappe-bench poc-frappe \
  /workspace/development/frappe-bench/env/bin/python /tmp/poc05_stage1.py

# 2) 生产工单（含 2 道工序）→ 自动生成 Job Card
docker cp poc/scripts/poc05_stage2.py  poc-frappe:/tmp/ && \
docker exec -w /workspace/development/frappe-bench poc-frappe \
  /workspace/development/frappe-bench/env/bin/python /tmp/poc05_stage2.py

# 3) 领料 → 报工 → 完工入库
docker cp poc/scripts/poc05_stage3.py  poc-frappe:/tmp/ && \
docker exec -w /workspace/development/frappe-bench poc-frappe \
  /workspace/development/frappe-bench/env/bin/python /tmp/poc05_stage3.py

# 4) 交付 → 开票 → 收款（另需中文支付方式：poc05_paymode.py）
docker cp poc/scripts/poc05_stage4.py  poc-frappe:/tmp/ && \
docker exec -w /workspace/development/frappe-bench poc-frappe \
  /workspace/development/frappe-bench/env/bin/python /tmp/poc05_stage4.py

# 5) 全量核对（单据链 / SLE / GL / 成本）
docker cp poc/scripts/poc05_verify.py  poc-frappe:/tmp/ && \
docker exec -w /workspace/development/frappe-bench poc-frappe \
  /workspace/development/frappe-bench/env/bin/python /tmp/poc05_verify.py
```

脚本特征：全部幂等（按单号/库存存在性判断，重复执行不会重复建单）；数据只落数据库与 Docker 卷，脚本已入库可重放。

**中文支付方式**：ERPNext 自带 `Cash / Wire Transfer` 为英文，POC 通过 `poc05_paymode.py` 新增「现金」「银行转账」两种中文支付方式，并新增明细科目「银行存款 - QC」（原「银行账户 - QC」为分组科目，不能直接用于支付方式）。

## 8. 截图

| 文件 | 内容 |
|---|---|
| `poc-05-workspace-production.png` | 中文工作台「设计与生产」菜单结构 |
| `poc-05-production-plan.png` | 生产计划 MFG-PP-2026-00001 |
| `poc-05-work-order.png` | 生产工单 MFG-WO-2026-00001（已完成） |
| `poc-05-job-card.png` | 生产任务单 PO-JOB00001（装配，员工，完成 2） |
| `poc-05-material-transfer.png` | 工单发料 MAT-STE-2026-00003 |
| `poc-05-manufacture.png` | 工单入库 MAT-STE-2026-00004（耗料 1440 / 成品 720 单价） |
| `poc-05-delivery-note.png` | 交货单 MAT-DN-2026-00004 |
| `poc-05-sales-invoice.png` | 销售发票 ACC-SINV-2026-00002 |
| `poc-05-payment-entry.png` | 收款单 ACC-PAY-2026-00002 |

截图存放：`D:\ERP\poc\share\screenshots\`（宿主机），容器内 `/hostshare/screenshots/`。截图由容器内无头 chromium 访问 `http://localhost:8000` 生成，界面为简体中文。

## 9. 遗留与后续

1. 工序成本（GAP-05-02）在 POC-06 前决定是否补工位费率后重跑；若补，需新建 BOM 版本。
2. 耗材/零部件/服务三张订单（POC-04）目前处于「已交付未开票」，可在 POC-06 用同一套开票收款动作补齐，用于演示四类订单的财务闭环。
3. 生产计划到工单目前按「计划 → 工单」单件推进，尚未验证多订单合并排产与产能负荷视图，属 POC 范围外。
