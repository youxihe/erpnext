# -*- coding: utf-8 -*-
"""扫描 frappe / erpnext zh.po 中关键 UI 术语的空翻译，输出缺口清单。

用法（容器内）：
  ./env/bin/python check_zh_gaps.py
"""
import re
import os

FILES = [
    "/workspace/development/frappe-bench/apps/frappe/frappe/locale/zh.po",
    "/workspace/development/frappe-bench/apps/erpnext/erpnext/locale/zh.po",
]

# POC 关键页面/按钮/字段会用到的英文原文
KEYS = [
    "Item", "Customer", "Supplier", "Company", "Warehouse", "BOM", "Work Order",
    "Job Card", "Stock Entry", "Material Request", "Purchase Order", "Purchase Receipt",
    "Purchase Invoice", "Delivery Note", "Sales Invoice", "Sales Order", "Payment Entry",
    "Production Plan", "Workstation", "Operation", "Lead Time Days", "Item Name",
    "Item Group", "Item Price", "Stock Balance", "Stock Ledger Entry", "Bin",
    "No {0} created", "No {0} found", "Clear the filters to see all records.",
    "A customer's confirmed order.", "Create a new {0}", "New {0}",
    "Submit", "Cancel", "Amend", "Save", "Delete", "Print", "Email", "Attach",
    "Refresh", "Get Items From", "Payment", "Advance", "Rate", "Amount", "Quantity",
    "Pending", "Completed", "Stopped", "Draft", "To Deliver", "To Bill",
    "Work Order Item", "Production Item", "Planned Start Date", "Actual Start Date",
    "For Quantity", "Transfer Material", "Manufacture", "Material Transfer",
    "Work Order Operations", "Operations", "Job Card Summary",
]


def load_po(path):
    """返回 {msgid: [msgstr, ...]}（含 msgctxt 分组）"""
    entries = {}
    msgid = None
    msgstr = None
    ctx = None
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if line.startswith("msgctxt "):
                ctx = line[8:].strip('"')
            elif line.startswith("msgid "):
                msgid = line[6:].strip('"')
                msgstr = None
            elif line.startswith("msgstr "):
                msgstr = line[7:].strip('"')
                if msgid is not None:
                    key = f"{ctx}|{msgid}" if ctx else msgid
                    entries.setdefault(msgid, []).append(msgstr if msgstr is not None else "")
                ctx = None
            elif line.startswith('"') and msgstr is not None:
                msgstr += line.strip('"')
    return entries


def main():
    merged = {}
    per_file = {}
    for p in FILES:
        app = "frappe" if "/frappe/" in p else "erpnext"
        d = load_po(p)
        per_file[app] = d
        for k, v in d.items():
            merged.setdefault(k, []).append((app, v))

    print(f"{'msgid':<44} {'frappe':<10} {'erpnext':<10} 结论")
    print("-" * 86)
    gaps = []
    for k in KEYS:
        f = next((v[0] for a, v in merged.get(k, []) if a == "frappe"), None)
        e = next((v[0] for a, v in merged.get(k, []) if a == "erpnext"), None)
        fv = "-" if f is None else (f if f else "<空>")
        ev = "-" if e is None else (e if e else "<空>")
        status = ""
        if not f and not e:
            status = "MISSING(两处都没有)"
            gaps.append((k, None))
        elif (f == "") and (e in (None, "")):
            status = "GAP(空)"
            gaps.append((k, None))
        elif f == "" and e:
            status = "ok(erpnext补)"
        elif e == "" and f:
            status = "ok(frappe补)"
        else:
            status = "ok"
        print(f"{k:<44} {fv:<10} {ev:<10} {status}")

    print("\n### 需要补翻译（写入自定义 App fixtures）###")
    for k, _ in gaps:
        print(" -", k)
    return gaps


if __name__ == "__main__":
    main()
