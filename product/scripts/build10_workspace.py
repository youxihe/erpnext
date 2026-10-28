# -*- coding: utf-8 -*-
"""BUILD-10 工作台入口更新 + 历史 Job Card 空时间行清理。幂等。"""
import frappe, json

frappe.init(site="erpnext-poc.localhost", sites_path="/workspace/development/frappe-bench/sites")
frappe.connect()
frappe.set_user("Administrator")

# ---------------------------------------------------------------- 1. 客户与销售：销售线索 → 客户报备
ws = frappe.get_doc("Workspace", "客户与销售")
changed = False
for l in ws.links:
    if l.link_to == "Lead" and l.label == "销售线索":
        l.label = "客户报备"
        changed = True
if changed:
    ws.flags.ignore_permissions = True
    ws.save()
    frappe.db.commit()
    print("[更新] 客户与销售：销售线索 → 客户报备")
else:
    print("[跳过] 客户与销售已是客户报备")

# ---------------------------------------------------------------- 2. 设计与生产：加「我的车间任务」报表链接
ws = frappe.get_doc("Workspace", "设计与生产")
has = any(l.label == "我的车间任务" for l in ws.links)
if not has:
    new_links = []
    for l in ws.links:
        new_links.append(l)
        if l.label == "生产任务单":
            ws.append("links", {
                "type": "Link",
                "label": "我的车间任务",
                "link_type": "Report",
                "link_to": "我的车间任务",
                "is_query_report": 1,
                "hidden": 0,
                "onboard": 0,
            })
    # append 已追加到末尾；重新按 idx 排列使它紧跟生产任务单
    rows = list(ws.links)
    target = [r for r in rows if r.label == "我的车间任务"]
    others = [r for r in rows if r.label != "我的车间任务"]
    idx = next(i for i, r in enumerate(others) if r.label == "生产任务单") + 1
    rows = others[:idx] + target + others[idx:]
    for i, r in enumerate(rows):
        r.idx = i + 1
    ws.links = []
    for r in rows:
        d = r.as_dict()
        d.pop("doctype", None)
        d.pop("name", None)
        ws.append("links", d)
    ws.flags.ignore_permissions = True
    ws.save()
    frappe.db.commit()
    print("[更新] 设计与生产：新增报表链接 我的车间任务")
else:
    print("[跳过] 设计与生产已有我的车间任务")

print("设计与生产 links:", [(l.label, l.link_to) for l in frappe.get_doc("Workspace", "设计与生产").links])

# ---------------------------------------------------------------- 3. 清理历史 Job Card 空时间行
for jc_name in ("PO-JOB00001", "PO-JOB00002"):
    jc = frappe.get_doc("Job Card", jc_name)
    empties = [t for t in jc.time_logs if not t.from_time]
    if empties:
        keep = [t for t in jc.time_logs if t.from_time]
        jc.time_logs = None
        for t in keep:
            jc.append("time_logs", {
                "employee": t.employee, "from_time": t.from_time, "to_time": t.to_time,
                "completed_qty": t.completed_qty, "time_in_mins": t.time_in_mins,
                "operation": t.get("operation"),
            })
        jc.flags.ignore_permissions = True
        jc.save()
        frappe.db.commit()
        print(f"[清理] {jc_name}: 删除 {len(empties)} 行空时间记录，保留 {len(keep)} 行")
    else:
        print(f"[跳过] {jc_name} 无空时间行")

frappe.clear_cache()
print("完成")
