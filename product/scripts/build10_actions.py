# -*- coding: utf-8 -*-
"""BUILD-10 业务动作：补料 → 报备客户(王明) → 新工单(刘工) → 领料 → 任务进度(李工)。

幂等：所有动作先查重，重跑输出 [跳过]。
"""
import frappe
from frappe.utils import nowdate, now_datetime, add_to_date

frappe.init(site="erpnext-poc.localhost", sites_path="/workspace/development/frappe-bench/sites")
frappe.connect()
frappe.set_user("Administrator")

COMPANY = "昆山启程智能设备有限公司"
WH_RAW = "原材料仓 - QC"
WH_WIP = "生产在制仓 - QC"
WH_FG = "产成品仓 - QC"
BOM = "BOM-ASSY-X1-001"
LEAD_COMPANY = "宁波海天精工股份有限公司"


def as_user(u):
    frappe.set_user(u)


def submit(doc):
    doc.insert()
    doc.submit()
    frappe.db.commit()
    return doc


print("=" * 60)

# ---------------------------------------------------------------- 1. 补料（Material Receipt）
need = {"RACK": 2, "SENSOR": 1}
receipt_name = None
for item, qty in need.items():
    if qty <= 0:
        continue
    done = frappe.get_all(
        "Stock Entry Detail",
        filters={"item_code": item, "docstatus": 1, "t_warehouse": WH_RAW, "qty": qty},
        fields=["parent"],
    )
    if done:
        print(f"[跳过] 补料入库已存在: {done[0]['parent']} ({item} x{qty})")
        receipt_name = receipt_name or done[0]["parent"]
        continue
    as_user("Administrator")
    se = frappe.new_doc("Stock Entry")
    se.company = COMPANY
    se.purpose = "Material Receipt"
    se.stock_entry_type = "Material Receipt"
    se.set_posting_time = 1
    se.append("items", {
        "item_code": item, "qty": qty, "t_warehouse": WH_RAW,
        "basic_rate": 200 if item == "RACK" else 300,
    })
    submit(se)
    receipt_name = se.name
    print(f"[创建] 补料入库(物资接收): {se.name} → {item} x{qty} @ {WH_RAW}")

# ---------------------------------------------------------------- 2. 客户报备（Lead，王明）
as_user("wangming@erpnext-poc.localhost")
lead = frappe.db.get_value("Lead", {"company_name": LEAD_COMPANY}, "name")
if lead:
    print(f"[跳过] 客户报备已存在: {lead}")
else:
    ld = frappe.new_doc("Lead")
    ld.company_name = LEAD_COMPANY
    ld.lead_name = "周主管"
    ld.mobile_no = "13800001111"
    ld.lead_owner = "wangming@erpnext-poc.localhost"
    ld.status = "Open"
    ld.insert()
    frappe.db.commit()
    lead = ld.name
    print(f"[创建] 客户报备(销售线索): {lead} → {LEAD_COMPANY} / 报备人 王明")

cust = frappe.db.get_value("Customer", {"customer_name": LEAD_COMPANY}, "name")
if cust:
    print(f"[跳过] 报备转客户已存在: {cust}")
else:
    from erpnext.crm.doctype.lead.lead import make_customer
    cdoc = frappe.get_doc(make_customer(lead))
    cdoc.company = COMPANY
    cdoc.insert()
    frappe.db.commit()
    cust = cdoc.name
    # 报备闭环：线索状态置为已转化
    ldoc = frappe.get_doc("Lead", lead)
    ldoc.status = "Converted"
    ldoc.save()
    frappe.db.commit()
    print(f"[创建] 报备转正式客户: {cust}（线索状态 → Converted）")

# ---------------------------------------------------------------- 3. 新生产工单（刘工）
wo_name = frappe.db.get_value("Work Order", {"production_item": "ASSY-X1", "qty": 1, "docstatus": [">", 0]}, "name")
if wo_name:
    print(f"[跳过] 演示工单已存在: {wo_name}")
else:
    as_user("liugong@erpnext-poc.localhost")
    wo = frappe.new_doc("Work Order")
    wo.company = COMPANY
    wo.production_item = "ASSY-X1"
    wo.item_name = "设备装配 X1"
    wo.bom_no = BOM
    wo.qty = 1
    wo.fg_warehouse = WH_FG
    wo.wip_warehouse = WH_WIP
    wo.source_warehouse = WH_RAW
    wo.stock_uom = "台"
    wo.planned_start_date = f"{nowdate()} 14:00:00"
    wo.expected_delivery_date = add_to_date(nowdate(), days=3)
    wo.set_work_order_operations()
    submit(wo)
    wo_name = wo.name
    print(f"[创建] 生产工单: {wo_name}（ASSY-X1 x1，自动生成 Job Card）")

frappe.set_user("Administrator")
wo = frappe.get_doc("Work Order", wo_name)
print(f"  工单状态: {wo.status} | 任务单: {frappe.get_all('Job Card', filters={'work_order': wo_name}, fields=['name','operation','status'])}")

# ---------------------------------------------------------------- 4. 领料（原材料仓 → 生产在制仓）
trf = frappe.get_all("Stock Entry", filters={
    "purpose": "Material Transfer for Manufacture", "docstatus": 1, "work_order": wo_name}, fields=["name"])
if trf:
    print(f"[跳过] 本工单领料已存在: {trf[0]['name']}")
else:
    from erpnext.manufacturing.doctype.work_order.work_order import make_stock_entry
    se_dict = make_stock_entry(wo_name, "Material Transfer for Manufacture", wo.qty)
    se = frappe.get_doc(se_dict)
    submit(se)
    print(f"[创建] 领料单: {se.name}（原材料仓 → 生产在制仓）")

# ---------------------------------------------------------------- 5. 我的任务进度（李工：装配 0.5/1 进行中）
as_user("ligong@erpnext-poc.localhost")
jc_rows = frappe.get_all("Job Card", filters={"work_order": wo_name, "operation": "装配"}, fields=["name"])
jc = frappe.get_doc("Job Card", jc_rows[0]["name"])
if jc.time_logs:
    print(f"[跳过] 任务已有进度: {jc.name} status={jc.status} completed={jc.total_completed_qty}")
else:
    jc.start_timer(employees="HR-EMP-00001", start_time=add_to_date(now_datetime(), minutes=-30))
    frappe.db.commit()
    jc = frappe.get_doc("Job Card", jc.name)
    jc.complete_job_card(qty=0.5, pending_qty=0.5, end_time=now_datetime())
    frappe.db.commit()
    jc = frappe.get_doc("Job Card", jc.name)
    print(f"[更新] 任务进度: {jc.name} → status={jc.status} completed={jc.total_completed_qty}/{jc.for_quantity}（李工，进行中）")

frappe.set_user("Administrator")

# ---------------------------------------------------------------- 汇总
print("=" * 60)
print("Bin 现状:")
for b in frappe.db.sql("select item_code,warehouse,actual_qty from tabBin where actual_qty<>0 order by item_code", as_dict=1):
    print(f"  {b['item_code']} @ {b['warehouse']}: {b['actual_qty']}")
print("BUILD-10 动作完成")
