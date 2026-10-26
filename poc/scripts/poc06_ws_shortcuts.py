#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""POC-06：给中文工作台补「快捷入口」磁贴，提升国产 PC 使用体验。

POC-03 建的中文工作台只有文字链接区块，缺快捷磁贴（用户要点进列表才能找到单据）。
本脚本为关键工作台补齐 4~6 个快捷入口（DocType 列表 / 报表），幂等。
用法：docker exec -w /workspace/development/frappe-bench poc-frappe \
        /workspace/development/frappe-bench/env/bin/python /tmp/poc06_ws_shortcuts.py
"""
import json
import frappe

frappe.init(site="erpnext-poc.localhost", sites_path="/workspace/development/frappe-bench/sites")
frappe.connect()
frappe.set_user("Administrator")

SHORTCUTS = {
    "设计与生产": [
        ("生产工单", "DocType", "Work Order"),
        ("生产计划", "DocType", "Production Plan"),
        ("物料清单", "DocType", "BOM"),
        ("生产任务单", "DocType", "Job Card"),
        ("物料移动", "DocType", "Stock Entry"),
        ("工位", "DocType", "Workstation"),
    ],
    "仓库管理": [
        ("物料", "DocType", "Item"),
        ("仓库", "DocType", "Warehouse"),
        ("物料移动", "DocType", "Stock Entry"),
        ("库存余额", "Report", "Stock Balance"),
        ("库存汇总", "Report", "Stock Summary"),
        ("库存对账", "DocType", "Stock Reconciliation"),
    ],
    "客户与销售": [
        ("销售订单", "DocType", "Sales Order"),
        ("交货单", "DocType", "Delivery Note"),
        ("销售发票", "DocType", "Sales Invoice"),
        ("客户", "DocType", "Customer"),
        ("物料价格", "DocType", "Item Price"),
    ],
    "采购管理": [
        ("采购订单", "DocType", "Purchase Order"),
        ("采购入库", "DocType", "Purchase Receipt"),
        ("物料申请", "DocType", "Material Request"),
        ("供应商", "DocType", "Supplier"),
        ("采购订单分析", "Report", "Purchase Order Analysis"),
    ],
    "财务管理": [
        ("销售发票", "DocType", "Sales Invoice"),
        ("收款单", "DocType", "Payment Entry"),
        ("总账凭证", "DocType", "Journal Entry"),
        ("应收账款汇总", "Report", "Accounts Receivable"),
        ("科目表", "DocType", "Account"),
    ],
    "物流交付": [
        ("交货单", "DocType", "Delivery Note"),
        ("销售订单", "DocType", "Sales Order"),
        ("物流单", "DocType", "Shipment"),
        ("交货单趋势", "Report", "Delivery Note Trends"),
    ],
    "基础资料": [
        ("物料", "DocType", "Item"),
        ("物料清单", "DocType", "BOM"),
        ("客户", "DocType", "Customer"),
        ("供应商", "DocType", "Supplier"),
        ("员工", "DocType", "Employee"),
        ("计量单位", "DocType", "UOM"),
    ],
    "经营报表": [
        ("库存余额", "Report", "Stock Balance"),
        ("销售订单分析", "Report", "Sales Order Analysis"),
        ("采购订单分析", "Report", "Purchase Order Analysis"),
        ("应收账款汇总", "Report", "Accounts Receivable"),
        ("生产计划汇总", "Report", "Production Analytics"),
    ],
}

modified = 0
for ws_name, items in SHORTCUTS.items():
    if not frappe.db.exists("Workspace", ws_name):
        print(f"[跳过] 工作台不存在: {ws_name}")
        continue
    ws = frappe.get_doc("Workspace", ws_name)
    existing = {(s.type, s.link_to) for s in ws.shortcuts}
    added = []
    for label, typ, link_to in items:
        if (typ, link_to) in existing:
            continue
        if typ == "DocType" and not frappe.db.exists("DocType", link_to):
            continue
        if typ == "Report" and not frappe.db.exists("Report", link_to):
            print(f"     报表缺省跳过: {link_to}")
            continue
        ws.append("shortcuts", {
            "type": typ,
            "label": label,
            "link_to": link_to,
            "doc_view": "List" if typ == "DocType" else "",
            "color": "Grey",
        })
        added.append(label)
    if added:
        ws.flags.ignore_permissions = True
        ws.save()
        modified += 1
        print(f"[更新] {ws_name}：新增 {len(added)} 个快捷入口 → {', '.join(added)}")
    else:
        print(f"[跳过] {ws_name}：快捷入口已齐（{len(ws.shortcuts)} 个）")

frappe.db.commit()
frappe.clear_cache()
print(f"\n完成：更新 {modified} 个工作台，已清缓存。")
for ws_name in SHORTCUTS:
    if frappe.db.exists("Workspace", ws_name):
        cnt = frappe.db.count("Workspace Shortcut", {"parent": ws_name})
        print(f"  {ws_name}: {cnt} 个快捷入口")
