#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""POC-06：给中文工作台加「关键指标数字卡」（v16 原生 number_card 区块）。

指标：
  生产工单数     Work Order 计数（已提交）
  本月销售额     Sales Invoice 合计 grand_total
  未收款金额     Sales Invoice 合计 outstanding_amount
  库存总值       Bin 合计 stock_value
用法：docker exec -w /workspace/development/frappe-bench poc-frappe \
        /workspace/development/frappe-bench/env/bin/python /tmp/poc06_ws_cards.py
"""
import json
import frappe

frappe.init(site="erpnext-poc.localhost", sites_path="/workspace/development/frappe-bench/sites")
frappe.connect()
frappe.set_user("Administrator")

CARDS = [
    {
        "label": "生产工单数",
        "document_type": "Work Order",
        "function": "Count",
        "filters_json": json.dumps([["Work Order", "docstatus", "=", 1]]),
        "color": "#318AD8",
    },
    {
        "label": "销售额",
        "document_type": "Sales Invoice",
        "function": "Sum",
        "aggregate_function_based_on": "grand_total",
        "filters_json": json.dumps([["Sales Invoice", "docstatus", "=", 1]]),
        "color": "#29CD42",
    },
    {
        "label": "未收款金额",
        "document_type": "Sales Invoice",
        "function": "Sum",
        "aggregate_function_based_on": "outstanding_amount",
        "filters_json": json.dumps([["Sales Invoice", "docstatus", "=", 1]]),
        "color": "#CB2929",
    },
    {
        "label": "库存总值",
        "document_type": "Bin",
        "function": "Sum",
        "aggregate_function_based_on": "stock_value",
        "filters_json": json.dumps([["Bin", "stock_value", ">", 0]]),
        "color": "#E24C00",
    },
]

for c in CARDS:
    name = c["label"]
    if frappe.db.exists("Number Card", name):
        print(f"[跳过] 数字卡已存在: {name}")
        continue
    d = frappe.new_doc("Number Card")
    d.label = name
    d.type = "Document Type"
    d.document_type = c["document_type"]
    d.function = c["function"]
    if c.get("aggregate_function_based_on"):
        d.aggregate_function_based_on = c["aggregate_function_based_on"]
    d.filters_json = c["filters_json"]
    d.is_public = 1
    d.show_percentage_stats = 1
    d.stats_time_interval = "Monthly"
    d.color = c["color"]
    d.flags.ignore_permissions = True
    d.insert()
    frappe.db.commit()
    print(f"[创建] 数字卡: {name}（{c['document_type']} / {c['function']}）")

# 把数字卡插到工作台内容开头
LAYOUT = {
    "设计与生产": ["生产工单数"],
    "财务管理": ["销售额", "未收款金额"],
    "仓库管理": ["库存总值"],
}

for ws_name, cards in LAYOUT.items():
    ws = frappe.get_doc("Workspace", ws_name)
    content = json.loads(ws.content)
    existing = {b.get("data", {}).get("number_card_name") for b in content if b.get("type") == "number_card"}
    new_blocks = []
    for i, cname in enumerate(cards):
        if cname in existing:
            continue
        new_blocks.append({
            "id": f"ncard_{ws_name}_{i}",
            "type": "number_card",
            "data": {"number_card_name": cname, "col": 3},
        })
    if new_blocks:
        ws.content = json.dumps(new_blocks + content, ensure_ascii=False)
        ws.flags.ignore_permissions = True
        ws.save()
        frappe.db.commit()
        print(f"[更新] {ws_name}：新增 {len(new_blocks)} 个数字卡区块")
    else:
        print(f"[跳过] {ws_name}：数字卡区块已存在")

frappe.clear_cache()
print("\n工作台区块一览：")
for ws_name in ("设计与生产", "仓库管理", "财务管理"):
    ws = frappe.get_doc("Workspace", ws_name)
    types = [b.get("type") for b in json.loads(ws.content)]
    print(f"  {ws_name}: {types}")
