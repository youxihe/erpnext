# -*- coding: utf-8 -*-
# 我的车间任务：当前登录员工在 Job Card Time Log 中的任务，服务端按 Employee.user_id 过滤。
# 管理员/系统管理角色可见全部，用于车间派工核对。

import frappe


def execute(filters=None):
    user = frappe.session.user
    is_manager = (
        user == "Administrator"
        or "System Manager" in frappe.get_roles(user)
    )

    conditions = "jc.docstatus < 2"
    values = {}
    if not is_manager:
        conditions += " and e.user_id = %(user)s"
        values["user"] = user

    data = frappe.db.sql(
        f"""
        select
            jc.name            as job_card,
            jc.work_order      as work_order,
            jc.production_item as production_item,
            jc.operation       as operation,
            jc.workstation     as workstation,
            tl.employee        as employee,
            e.employee_name    as employee_name,
            jc.for_quantity    as for_quantity,
            jc.total_completed_qty as completed_qty,
            jc.status          as status,
            tl.from_time       as from_time,
            tl.to_time         as to_time,
            tl.time_in_mins    as time_in_mins
        from `tabJob Card Time Log` tl
        join `tabJob Card` jc on tl.parent = jc.name
        left join `tabEmployee` e on tl.employee = e.name
        where tl.parentfield = 'time_logs' and {conditions}
        order by jc.name, tl.from_time
        """,
        values,
        as_dict=1,
    )

    columns = [
        {"label": "任务单", "fieldname": "job_card", "fieldtype": "Link", "options": "Job Card", "width": 160},
        {"label": "生产工单", "fieldname": "work_order", "fieldtype": "Link", "options": "Work Order", "width": 170},
        {"label": "产品", "fieldname": "production_item", "fieldtype": "Link", "options": "Item", "width": 120},
        {"label": "工序", "fieldname": "operation", "fieldtype": "Data", "width": 90},
        {"label": "工位", "fieldname": "workstation", "fieldtype": "Link", "options": "Workstation", "width": 110},
        {"label": "员工", "fieldname": "employee_name", "fieldtype": "Data", "width": 90},
        {"label": "应做数量", "fieldname": "for_quantity", "fieldtype": "Float", "width": 90},
        {"label": "已完成", "fieldname": "completed_qty", "fieldtype": "Float", "width": 90},
        {"label": "状态", "fieldname": "status", "fieldtype": "Data", "width": 120},
        {"label": "开始时间", "fieldname": "from_time", "fieldtype": "Datetime", "width": 140},
        {"label": "结束时间", "fieldname": "to_time", "fieldtype": "Datetime", "width": 140},
        {"label": "用时(分)", "fieldname": "time_in_mins", "fieldtype": "Float", "width": 90},
    ]
    return columns, data
