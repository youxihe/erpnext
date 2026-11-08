# -*- coding: utf-8 -*-
"""BUILD-91 轻制造：固定生产进度（Project Template + Project/Task）。

遵循 docs/product/decisions/LIGHT_MANUFACTURING_20261108.md：
- 生产人员只更新 Project Task 的状态/日期/备注/附件，不操作 Job Card。
- Task 状态与库存彻底解耦；完工入库只能由原生 Work Order / Stock Entry 产生。
- 一生产类销售订单 ↔ 一个生产进度 Project，按九阶段模板生成 Task，幂等。
- PC / H5 / Bot 共用本模块，服务端按当前会话用户做角色与数据域校验。
"""

import json
from urllib.parse import quote

import frappe
from frappe import _
from frappe.utils import add_days, getdate, nowdate, today

TEMPLATE_TYPE = "整机生产九阶段"
DEFAULT_DUE_SOON_DAYS = 3

# 「最小字段」：名称 subject、目标日期 exp_end_date、完成时间 completed_on 为原生；
# 负责人/状态/备注/附件/来源订单用最小自定义字段，不新建 DocType。
STAGES = [
    {"subject": "机架焊接", "start": 0, "duration": 3},
    {"subject": "机加工件加工", "start": 3, "duration": 4},
    {"subject": "内钣金焊接", "start": 7, "duration": 3},
    {"subject": "电控板组装", "start": 10, "duration": 2},
    {"subject": "管道焊接", "start": 12, "duration": 3},
    {"subject": "机构件组装", "start": 15, "duration": 3},
    {"subject": "电气组装", "start": 18, "duration": 2},
    {"subject": "外蒙板组装", "start": 20, "duration": 3},
    {"subject": "调整老化", "start": 23, "duration": 2},
]

STATUS_TO_NATIVE = {
    "待开始": "Open",
    "进行中": "Working",
    "已完成": "Completed",
    "异常": "Pending Review",
}
NATIVE_TO_STATUS = {v: k for k, v in STATUS_TO_NATIVE.items()}

CUSTOM_FIELDS = [
    ("production_owner", "生产负责人", "Link", "User", "status", 0),
    ("production_status", "生产状态", "Select", "待开始\n进行中\n已完成\n异常", "production_owner", 0),
    ("production_note", "生产备注", "Small Text", None, "production_status", 0),
    ("production_attachment", "任务附件", "Attach", None, "production_note", 0),
    ("source_sales_order", "来源销售订单", "Link", "Sales Order", "project", 1),
]

MANAGER_ROLES = {"Manufacturing Manager", "System Manager"}
STAFF_ROLES = {"Employee", "Manufacturing User", "Manufacturing Manager", "System Manager"}
READ_ROLES = STAFF_ROLES | {"Sales User", "Sales Manager", "Accounts User", "Accounts Manager"}


def _roles():
    return set(frappe.get_roles())


def _require(cond, msg, exc=frappe.PermissionError):
    if not cond:
        frappe.throw(msg, exc)


def _desk_url(doctype, name=None):
    """Desk 路由（与 order_execution._desk_url 同规则），供门户 iframe 与新窗口共用。"""
    import re

    slug = re.sub(r"[^a-z0-9]+", "-", (doctype or "").lower()).strip("-")
    return "/desk/" + slug + ("/" + quote(str(name), safe="") if name else "")


def _audit(subject_name, action, detail=None):
    frappe.logger("cn_production").info(
        json.dumps(
            {
                "user": frappe.session.user,
                "action": action,
                "task": subject_name,
                "detail": detail,
                "time": str(nowdate()),
            },
            ensure_ascii=False,
        )
    )


def due_soon_days():
    """临期阈值，可在 site_config 用 production_due_soon_days 覆盖（默认 3 日）。"""
    try:
        return max(1, int(frappe.conf.get("production_due_soon_days") or DEFAULT_DUE_SOON_DAYS))
    except (TypeError, ValueError):
        return DEFAULT_DUE_SOON_DAYS


def due_state(task):
    """逾期 / 临期 / 正常 / 已完成 / 未排期（只读计算，不写库）。"""
    status = task.get("production_status") or NATIVE_TO_STATUS.get(task.get("status"), "待开始")
    if status == "已完成":
        return "已完成"
    if not task.get("exp_end_date"):
        return "未排期"
    end = getdate(task["exp_end_date"])
    now = getdate(today())
    if end < now:
        return "逾期"
    if end <= add_days(now, due_soon_days()):
        return "临期"
    return "正常"


# ---------------------------------------------------------------- 配置（幂等）


def _stage_description(i):
    return "整机生产九阶段模板 · 第 %d 阶段（可由负责人调整目标日期与备注）" % i


def _ensure_stage_template_tasks():
    """返回九个模板 Task 名称；幂等，且能自愈早期失败 setup 留下的普通副本。

    ERPNext v16 的 Task.validate_status() 会在 ``status="Template"`` 但
    ``is_template=0`` 时把状态强制改回 Open；Project Template.validate_template_tasks()
    又只认 ``is_template=1`` 的 Task。因此模板 Task 必须同时设置两者。
    历史失败 setup 产生的「无 project / is_template=0 / status=Open」副本仅是本脚本
    自己创建的孤儿数据（无单据引用），这里复用第一条并清理其余，保证模板唯一。
    """
    names = []
    stats = {"created": [], "repaired": [], "removed": []}
    for i, stage in enumerate(STAGES, 1):
        rows = frappe.get_all(
            "Task",
            filters={"subject": stage["subject"]},
            fields=["name", "status", "is_template", "start", "duration",
                    "project", "template_task", "creation"],
            order_by="creation", limit=100,
        )
        orphans = [r for r in rows if not r.get("project")]
        orphan_by_name = {r["name"]: r for r in orphans}
        real_templates = [r for r in orphans if r["is_template"]]
        canonical = real_templates[0]["name"] if real_templates else (
            orphans[0]["name"] if orphans else None
        )

        if canonical and not orphan_by_name[canonical]["is_template"]:
            frappe.db.set_value("Task", canonical, {
                "is_template": 1,
                "status": "Template",
                "start": stage["start"],
                "duration": stage["duration"],
                "task_weight": 1,
                "description": _stage_description(i),
            }, update_modified=False)
            stats["repaired"].append(canonical)
        elif not canonical:
            t = frappe.new_doc("Task")
            t.subject = stage["subject"]
            t.is_template = 1
            t.status = "Template"
            t.start = stage["start"]
            t.duration = stage["duration"]
            t.task_weight = 1
            t.description = _stage_description(i)
            t.insert(ignore_permissions=True)
            canonical = t.name
            stats["created"].append(canonical)

        # 只清理能被证明是失败 setup 残留的孤儿副本，绝不碰项目下的正式 Task。
        for r in orphans:
            if (r["name"] != canonical and not r["is_template"] and r["status"] == "Open"
                    and not r.get("template_task")
                    and r["start"] == stage["start"] and r["duration"] == stage["duration"]):
                frappe.delete_doc("Task", r["name"], force=True, ignore_permissions=True,
                                  delete_permanently=True)
                stats["removed"].append(r["name"])
        names.append(canonical)
    frappe.db.commit()
    return names, stats


def setup_template():
    """建自定义字段 + 九个模板 Task + Project Template；可重复执行。"""
    created = {"custom_fields": [], "template_tasks": [], "project_template": None}

    for fieldname, label, fieldtype, options, insert_after, read_only in CUSTOM_FIELDS:
        name = "Task-%s" % fieldname
        if frappe.db.exists("Custom Field", name):
            continue
        cf = frappe.new_doc("Custom Field")
        cf.dt = "Task"
        cf.fieldname = fieldname
        cf.label = label
        cf.fieldtype = fieldtype
        if options:
            cf.options = options
        cf.insert_after = insert_after
        cf.read_only = read_only
        cf.insert(ignore_permissions=True)
        created["custom_fields"].append(name)
    frappe.db.commit()
    frappe.clear_cache(doctype="Task")

    task_names, stats = _ensure_stage_template_tasks()
    created["template_tasks"] = stats["created"]
    created["repaired_template_tasks"] = stats["repaired"]
    created["removed_orphan_tasks"] = stats["removed"]

    if not frappe.db.exists("Project Type", TEMPLATE_TYPE):
        pt = frappe.new_doc("Project Type")
        pt.project_type = TEMPLATE_TYPE
        pt.insert(ignore_permissions=True)
        frappe.db.commit()

    if frappe.db.exists("Project Template", TEMPLATE_TYPE):
        # UX-96A：模板一旦存在就视为人工配置权威，迁移不得用 STAGES 常量覆盖
        # （管理员可在 /production_template 改名/调顺序/改默认排期）。
        # 只有模板被清空（0 行）时才按当前 STAGES 自愈补齐，避免空模板导致无法创建项目。
        if frappe.db.exists("Project Template Task", {"parent": TEMPLATE_TYPE}):
            created["project_template"] = TEMPLATE_TYPE
            created["skipped_existing_template"] = True
            return created
        for n in task_names:
            frappe.get_doc({
                "doctype": "Project Template Task",
                "parent": TEMPLATE_TYPE,
                "parenttype": "Project Template",
                "parentfield": "tasks",
                "task": n,
            }).insert(ignore_permissions=True)
        frappe.db.commit()
        created["project_template"] = TEMPLATE_TYPE
        created["repaired_empty_template"] = True
        return created

    tmpl = frappe.new_doc("Project Template")
    # Project Template 使用 prompt autoname，必须显式给 name
    tmpl.name = TEMPLATE_TYPE
    tmpl.project_type = TEMPLATE_TYPE
    for n in task_names:
        tmpl.append("tasks", {"task": n})
    tmpl.insert(ignore_permissions=True, set_name=TEMPLATE_TYPE)
    frappe.db.commit()
    created["project_template"] = tmpl.name
    return created


# ---------------------------------------------------------------- 一单一项目（幂等）


def _ensure_project_tasks(project, sales_order, owners=None):
    """按 Project Template 的九行补齐缺失的原生 Task；按阶段 subject 去重。

    不用 ERPNext 原生 Project.after_insert() → copy_from_template()：v16 的
    create_task_from_template() 内部用 ``.insert()`` 而非
    ``.insert(ignore_permissions=True)``，而 Task 原生只授权 Projects User /
    HR Manager 建单，生产经理会抛 PermissionError。这里由服务端在创建人
    角色已校验通过后，用同一模板行 + 原生日期算法生成 Task，行为一致且可控。
    """
    owners = owners or {}
    tmpl = frappe.get_doc("Project Template", TEMPLATE_TYPE)
    existing = {r["subject"]: r["name"] for r in frappe.get_all(
        "Task", filters={"project": project.name}, fields=["name", "subject"], limit=100,
    )}
    created = []
    for i, row in enumerate(tmpl.tasks, 1):
        td = frappe.get_doc("Task", row.task)
        if td.subject in existing:
            continue
        owner = owners.get(str(i)) or owners.get(td.subject) or frappe.session.user
        task = frappe.new_doc("Task")
        task.subject = td.subject
        task.project = project.name
        task.status = "Open"
        task.template_task = td.name
        task.exp_start_date = project.calculate_start_date(td)
        task.exp_end_date = project.calculate_end_date(td)
        task.description = td.description
        task.task_weight = td.task_weight
        task.type = td.type
        task.issue = td.issue
        task.is_group = td.is_group
        task.color = td.color
        task.production_owner = owner
        task.production_status = "待开始"
        task.source_sales_order = sales_order
        task.insert(ignore_permissions=True)
        created.append(task.name)
    return created


def _project_tasks(project):
    return frappe.get_all(
        "Task", filters={"project": project},
        fields=["name", "subject", "exp_start_date", "exp_end_date", "production_status",
                "production_owner", "source_sales_order", "status", "template_task"],
        order_by="exp_start_date, name", limit=100,
    )


@frappe.whitelist(methods=["POST"])
def create_project(sales_order, start_date=None, owners=None):
    """为一张生产类销售订单建立/复用生产进度 Project，按九阶段模板生成 Task。

    幂等：同一 sales_order 已有 Project 时直接返回原项目与原有 Task，不重复生成。
    owners：可选 JSON，阶段序号(1-9 或阶段名) → ERP User；未指定的阶段按默认分派。
    """
    _require(_roles() & MANAGER_ROLES, _("仅生产负责人/系统管理员可创建生产进度项目"))
    so = frappe.db.get_value(
        "Sales Order", sales_order,
        ["name", "docstatus", "business_type", "company"], as_dict=True,
    )
    _require(so, _("销售订单不存在：{0}").format(sales_order), frappe.ValidationError)
    _require(so["docstatus"] == 1, _("销售订单未确认，不能生成生产进度"), frappe.ValidationError)
    _require(so["business_type"] == "生产", _("只有生产类订单才生成生产进度项目"), frappe.ValidationError)

    _require(frappe.db.exists("Project Template", TEMPLATE_TYPE), _("九阶段模板未初始化，请先执行 setup_template()"))
    if isinstance(owners, str):
        owners = json.loads(owners or "{}")
    owners = owners or {}

    existing = frappe.db.get_value("Project", {"sales_order": sales_order}, "name")
    if existing:
        proj = frappe.get_doc("Project", existing)
        repaired = _ensure_project_tasks(proj, sales_order, owners)
        if repaired:
            frappe.db.commit()
        return {"project": existing, "replayed": True,
                "project_url": _desk_url("Project", existing),
                "tasks": _project_tasks(existing), "repaired_tasks": repaired,
                "message": _("该订单已有生产进度项目，未重复生成")}

    start = start_date or nowdate()
    proj = frappe.new_doc("Project")
    proj.project_name = "%s 生产进度" % sales_order
    proj.sales_order = sales_order
    proj.company = so["company"]
    proj.status = "Open"
    proj.is_active = "Yes"
    proj.expected_start_date = start
    # 九阶段按 start+duration 排到 +25 天，遇到节假日顺延；项目结束日留 10 天缓冲，
    # 否则 Task.validate_parent_project_dates() 会对新建任务抛出 InvalidDates。
    proj.expected_end_date = add_days(getdate(start), 35)
    # 故意不在 insert 前设置 project_template：避免原生 after_insert.copy_from_template()
    # 在 Task 无建单权限的角色下抛 PermissionError。insert 仍会原生回写 Sales Order.project。
    proj.insert(ignore_permissions=True)
    proj.db_set("project_template", TEMPLATE_TYPE)
    _ensure_project_tasks(proj, sales_order, owners)
    frappe.db.commit()
    rows = _project_tasks(proj.name)
    _audit(proj.name, "创建生产进度项目", "%s tasks=%d" % (sales_order, len(rows)))
    return {
        "project": proj.name,
        "project_url": _desk_url("Project", proj.name),
        "replayed": False,
        "sales_order": sales_order,
        "template": TEMPLATE_TYPE,
        "tasks": rows,
    }


# ---------------------------------------------------------------- 我的任务 / 更新


def _task_row(name):
    return frappe.db.get_value(
        "Task", name,
        ["name", "subject", "project", "source_sales_order", "production_owner",
         "production_status", "status", "exp_start_date", "exp_end_date", "completed_on",
         "production_note", "production_attachment", "description"],
        as_dict=True,
    )


def _serialize(row):
    d = dict(row)
    d["due_state"] = due_state(d)
    d["production_status"] = d.get("production_status") or NATIVE_TO_STATUS.get(d.get("status"), "待开始")
    return d


@frappe.whitelist(methods=["GET"])
def tasks_mine(limit=50):
    """本人负责的生产任务；管理角色可见全部（可选 mine_only=0）。"""
    _require(_roles() & STAFF_ROLES, _("当前角色无权查看生产任务"))
    filters = {"status": ("not in", ["Template", "Cancelled"])}
    if not (_roles() & MANAGER_ROLES):
        filters["production_owner"] = frappe.session.user
    rows = frappe.get_all("Task", filters=filters, fields=[
        "name", "subject", "project", "source_sales_order", "production_owner",
        "production_status", "status", "exp_start_date", "exp_end_date", "completed_on",
        "production_note", "production_attachment", "description",
    ], order_by="exp_end_date, name", limit=int(limit))
    result = [_serialize(r) for r in rows]
    return {
        "user": frappe.session.user,
        "tasks": result,
        "due_soon_days": due_soon_days(),
        "summary": {
            "total": len(result),
            "overdue": sum(1 for r in result if r["due_state"] == "逾期"),
            "due_soon": sum(1 for r in result if r["due_state"] == "临期"),
            "completed": sum(1 for r in result if r["due_state"] == "已完成"),
        },
    }


@frappe.whitelist(methods=["POST"])
def tasks_update(task, production_status=None, note=None, attachment=None, exp_end_date=None):
    """本人更新任务：状态 / 备注 / 附件 / 目标日期。严格校验负责人，不触发任何库存事务。"""
    _require(_roles() & STAFF_ROLES, _("当前角色无权更新生产任务"))
    row = _task_row(task)
    _require(row, _("任务不存在：{0}").format(task), frappe.ValidationError)
    _require(row["status"] != "Template", _("模板任务不能直接更新"), frappe.ValidationError)
    _require(
        row.get("production_owner") == frappe.session.user,
        _("该任务负责人不是您（{0}），不能代他人更新").format(row.get("production_owner")),
    )

    values = {}
    if production_status is not None:
        _require(production_status in STATUS_TO_NATIVE,
                 _("生产状态无效：{0}").format(production_status), frappe.ValidationError)
        values["production_status"] = production_status
        values["status"] = STATUS_TO_NATIVE[production_status]
        if production_status == "已完成":
            values["completed_on"] = nowdate()
            values["completed_by"] = frappe.session.user
        else:
            values["completed_on"] = None
            values["completed_by"] = None
    if note is not None:
        values["production_note"] = note
        values["description"] = note
    if attachment is not None:
        values["production_attachment"] = attachment
    if exp_end_date is not None:
        values["exp_end_date"] = exp_end_date
    _require(values, _("没有需要更新的内容"), frappe.ValidationError)

    doc = frappe.get_doc("Task", task)
    doc.update(values)
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    _audit(task, "更新生产任务", json.dumps(values, ensure_ascii=False, default=str))
    updated = _serialize(_task_row(task))
    return {"task": task, **updated, "stock_unchanged": True}


@frappe.whitelist(methods=["POST"])
def assign_task(task, owner, exp_end_date=None, note=None):
    """生产经理分派负责人 / 调整目标日期 / 修改备注（本人更新之外的管理动作）。"""
    _require(_roles() & MANAGER_ROLES, _("仅生产负责人/系统管理员可分派任务"))
    _require(frappe.db.exists("User", owner), _("ERP 用户不存在：{0}").format(owner), frappe.ValidationError)
    row = _task_row(task)
    _require(row and row["status"] != "Template", _("任务不存在或为模板"), frappe.ValidationError)
    values = {"production_owner": owner}
    if exp_end_date:
        values["exp_end_date"] = exp_end_date
    if note is not None:
        values["production_note"] = note
        values["description"] = note
    frappe.db.set_value("Task", task, values, update_modified=False)
    frappe.db.commit()
    _audit(task, "分派生产任务", "%s %s %s" % (owner, exp_end_date or "", (note or "")[:40]))
    names = _owner_names([{"production_owner": owner}])
    return {"task": task, "owner_name": names.get(owner, owner), **_serialize(_task_row(task))}


@frappe.whitelist(methods=["GET"])
def my_production_orders(limit=50):
    """PC 下拉可选的生产类已确认销售订单；按当前用户 Sales Order 读权限过滤。"""
    _require(_roles() & READ_ROLES, _("当前角色无权查看订单生产进度"))
    is_manager = bool(_roles() & MANAGER_ROLES)
    rows = frappe.get_all(
        "Sales Order",
        filters={"business_type": "生产", "docstatus": 1},
        fields=["name", "customer_name", "delivery_date", "status", "project"],
        order_by="name desc", limit=int(limit),
    )
    visible = []
    for r in rows:
        if not (is_manager or frappe.has_permission("Sales Order", "read", doc=r["name"])):
            continue
        r["has_project"] = bool(r.get("project"))
        visible.append(r)
    return {"user": frappe.session.user, "orders": visible}


@frappe.whitelist(methods=["GET"])
def order_progress(sales_order):
    """订单生产进度概览：完成数 / 总数 / 逾期 / 临期 / 最近异常（只读）。"""
    _require(_roles() & READ_ROLES, _("当前角色无权查看订单生产进度"))
    _require(
        frappe.has_permission("Sales Order", "read", doc=sales_order) or (_roles() & MANAGER_ROLES),
        _("无权查看该销售订单"),
    )
    project = frappe.db.get_value("Project", {"sales_order": sales_order}, "name")
    if not project:
        return {"sales_order": sales_order, "project": None, "started": False,
                "message": _("该订单尚未建立生产进度项目")}
    rows = frappe.get_all("Task", filters={"project": project, "status": ("not in", ["Template", "Cancelled"])}, fields=[
        "name", "subject", "source_sales_order", "production_owner", "production_status",
        "status", "exp_end_date", "completed_on", "production_note", "production_attachment",
    ], order_by="exp_end_date, name")
    result = [_serialize(r) for r in rows]
    return {
        "sales_order": sales_order,
        "project": project,
        "started": True,
        "due_soon_days": due_soon_days(),
        "total": len(result),
        "completed": sum(1 for r in result if r["due_state"] == "已完成"),
        "overdue": sum(1 for r in result if r["due_state"] == "逾期"),
        "due_soon": sum(1 for r in result if r["due_state"] == "临期"),
        "last_exception": next(
            (r["production_note"] for r in result if r["production_status"] == "异常" and r.get("production_note")),
            None,
        ),
        "tasks": result,
    }


# ---------------------------------------------------------------- UX-96A 管理入口
# 用户现场反馈：/production_board?view=order 只能看，不知道模板在哪配、怎么给新订单
# 生成任务、怎么改负责人。下面补充「模板管理 + 订单建项 + 分派」三组受控接口。
# 全部只写 Project/Task（过程记录），不触碰 Stock Ledger / Bin / Work Order。


def _require_manager():
    _require(_roles() & MANAGER_ROLES, _("仅生产负责人/系统管理员可执行该操作"))


def _owner_names(rows):
    """把 owner 邮箱补成中文姓名，前端下拉和表格都按姓名展示。"""
    users = {r.get("production_owner") for r in rows if r.get("production_owner")}
    if not users:
        return {}
    return {
        u["name"]: (u.get("full_name") or u["name"])
        for u in frappe.get_all("User", filters={"name": ["in", list(users)]},
                                fields=["name", "full_name"], limit=100)
    }


def _template_order():
    """模板当前顺序 → {模板Task: 序号}，用于订单任务按阶段顺序展示。"""
    try:
        tmpl = frappe.get_doc("Project Template", TEMPLATE_TYPE)
    except Exception:
        return {}
    return {r.task: i for i, r in enumerate(tmpl.tasks, 1)}


@frappe.whitelist(methods=["GET"])
def template_detail():
    """九阶段模板详情（管理员/生产经理）。只读，不产生任何业务数据。"""
    _require_manager()
    _require(frappe.db.exists("Project Template", TEMPLATE_TYPE),
             _("九阶段模板尚未初始化，请先执行 migrate"), frappe.ValidationError)
    tmpl = frappe.get_doc("Project Template", TEMPLATE_TYPE)
    rows = []
    for i, row in enumerate(tmpl.tasks, 1):
        t = frappe.db.get_value(
            "Task", row.task,
            ["name", "subject", "start", "duration", "description", "status", "is_template"],
            as_dict=True,
        )
        if not t:
            continue
        rows.append({
            "idx": i,
            "task": t["name"],
            "subject": t["subject"],
            "start": t["start"],
            "duration": t["duration"],
            "description": t["description"],
            "is_template": bool(t["is_template"]),
        })
    return {
        "template": TEMPLATE_TYPE,
        "project_type": tmpl.project_type,
        "native_url": "/desk/project-template/" + quote(TEMPLATE_TYPE),
        "tasks": rows,
        "total": len(rows),
        "can_manage": True,
        "effect_note": _("模板修改只影响之后新建的生产进度；已生成订单任务保持原样，"
                         "需要调整请到「订单生产进度」逐单修改。"),
    }


def _template_task_names():
    tmpl = frappe.get_doc("Project Template", TEMPLATE_TYPE)
    return [r.task for r in tmpl.tasks]


@frappe.whitelist(methods=["POST"])
def template_update_task(task, subject=None, start=None, duration=None, description=None):
    """维护单个模板阶段：名称 / 相对开始天数 / 工期 / 描述。

    只允许改 is_template=1 的模板 Task；项目下真实任务必须走订单视图的分派接口。
    """
    _require_manager()
    _require(task in _template_task_names(), _("该任务不属于九阶段模板"), frappe.ValidationError)
    td = frappe.get_doc("Task", task)
    _require(td.is_template, _("该项目任务不是模板任务，不能在模板里修改"), frappe.ValidationError)

    values = {}
    if subject is not None:
        subject = (subject or "").strip()
        _require(subject, _("阶段名称不能为空"), frappe.ValidationError)
        values["subject"] = subject
    if start is not None:
        try:
            values["start"] = max(0, int(start))
        except (TypeError, ValueError):
            frappe.throw(_("开始天数必须是整数"), frappe.ValidationError)
    if duration is not None:
        try:
            duration = int(duration)
        except (TypeError, ValueError):
            frappe.throw(_("工期必须是整数天"), frappe.ValidationError)
        _require(duration >= 1, _("工期至少 1 天"), frappe.ValidationError)
        values["duration"] = duration
    if description is not None:
        values["description"] = description
    _require(values, _("没有需要修改的内容"), frappe.ValidationError)

    td.update(values)
    td.save(ignore_permissions=True)
    # 子表 subject 是只读 fetch 字段，重命名后同步，避免模板页显示旧名称
    if "subject" in values:
        for row in frappe.get_all("Project Template Task",
                                  filters={"parent": TEMPLATE_TYPE, "task": task},
                                  fields=["name"], limit=1):
            frappe.db.set_value("Project Template Task", row["name"], "subject",
                                values["subject"], update_modified=False)
    frappe.db.commit()
    frappe.clear_cache(doctype="Task")
    _audit(task, "修改生产阶段模板", json.dumps(values, ensure_ascii=False, default=str))
    return {"template": TEMPLATE_TYPE, "task": task, "updated": values,
            "effect": _("仅影响之后新建的生产进度项目")}


@frappe.whitelist(methods=["POST"])
def template_move_task(task, direction="up"):
    """调整阶段顺序（上移/下移），顺序决定新项目生成任务的先后。"""
    _require_manager()
    direction = (direction or "").lower()
    _require(direction in ("up", "down"), _("方向只能是 up 或 down"), frappe.ValidationError)
    tmpl = frappe.get_doc("Project Template", TEMPLATE_TYPE)
    rows = list(tmpl.tasks)
    pos = next((i for i, r in enumerate(rows) if r.task == task), None)
    _require(pos is not None, _("该任务不属于九阶段模板"), frappe.ValidationError)
    target = pos - 1 if direction == "up" else pos + 1
    _require(0 <= target < len(rows), _("已经到边界，无法继续移动"), frappe.ValidationError)

    rows[pos], rows[target] = rows[target], rows[pos]
    for i, row in enumerate(rows, 1):
        frappe.db.set_value("Project Template Task", row.name, "idx", i, update_modified=False)
    frappe.db.commit()
    frappe.clear_cache(doctype="Project Template")
    _audit(task, "调整生产阶段顺序", direction)
    return {"template": TEMPLATE_TYPE, "moved": True, "direction": direction,
            "order": [{"task": r.task, "idx": i} for i, r in enumerate(rows, 1)]}


@frappe.whitelist(methods=["GET"])
def assignable_users(limit=50):
    """可被分派生产任务的用户（启用 + 生产相关角色），返回中文姓名。"""
    _require(_roles() & READ_ROLES, _("当前角色无权查看人员"))
    rows = frappe.db.sql(
        """select distinct u.name, u.full_name
           from `tabUser` u
           join `tabHas Role` r on r.parent = u.name and r.parenttype = 'User'
           where u.enabled = 1 and u.name not in ('Administrator', 'Guest')
             and r.role in ('Manufacturing User', 'Manufacturing Manager', 'Employee')
           order by u.full_name, u.name limit %s""",
        (int(limit),), as_dict=True,
    )
    return {"users": [{"user": r["name"], "name": r["full_name"] or r["name"]} for r in rows]}


@frappe.whitelist(methods=["GET"])
def order_board(sales_order):
    """订单生产进度管理视图：订单 + 项目 + 任务（含中文负责人、可管理标记）。

    与 order_progress 的区别：这里面向管理动作，额外返回 can_manage / can_create /
    可读原因与分派所需字段；只读聚合逻辑仍复用同一批 Task 记录。
    """
    _require(_roles() & READ_ROLES, _("当前角色无权查看订单生产进度"))
    so = frappe.db.get_value(
        "Sales Order", sales_order,
        ["name", "customer", "customer_name", "status", "docstatus", "business_type",
         "delivery_date", "transaction_date"], as_dict=True,
    )
    _require(so, _("销售订单不存在：{0}").format(sales_order), frappe.ValidationError)
    can_manage = bool(_roles() & MANAGER_ROLES)
    _require(frappe.has_permission("Sales Order", "read", doc=sales_order) or can_manage,
             _("无权查看该销售订单"))

    project = frappe.db.get_value(
        "Project", {"sales_order": sales_order},
        ["name", "status", "expected_start_date", "expected_end_date"], as_dict=True,
    )
    order = {
        "name": so["name"],
        "customer_name": so["customer_name"],
        "status": so["status"],
        "docstatus": so["docstatus"],
        "business_type": so["business_type"],
        "delivery_date": str(so["delivery_date"]) if so["delivery_date"] else None,
        "transaction_date": str(so["transaction_date"]) if so["transaction_date"] else None,
        "url": _desk_url("Sales Order", sales_order),
    }

    block = None
    if so["docstatus"] != 1:
        block = _("订单尚未提交确认，不能生成生产进度")
    elif so["business_type"] != "生产":
        block = _("只有生产类订单才生成生产进度")

    tasks = []
    if project:
        order_map = _template_order()
        rows = frappe.get_all(
            "Task", filters={"project": project["name"],
                             "status": ("not in", ["Template", "Cancelled"])},
            fields=["name", "subject", "project", "source_sales_order", "production_owner",
                    "production_status", "status", "exp_start_date", "exp_end_date",
                    "completed_on", "production_note", "template_task"],
            limit=100,
        )
        rows.sort(key=lambda r: (order_map.get(r.get("template_task"), 99), r["name"]))
        names = _owner_names(rows)
        for r in rows:
            d = _serialize(r)
            d["owner_name"] = names.get(r.get("production_owner")) or (r.get("production_owner") or "")
            d["template_index"] = order_map.get(r.get("template_task"))
            tasks.append(d)

    return {
        "user": frappe.session.user,
        "order": order,
        "project": project["name"] if project else None,
        "project_url": _desk_url("Project", project["name"]) if project else None,
        "project_status": project["status"] if project else None,
        "template": TEMPLATE_TYPE,
        "can_manage": can_manage,
        "can_create": bool(can_manage and not block),
        "create_block_reason": block,
        "due_soon_days": due_soon_days(),
        "tasks": tasks,
        "total": len(tasks),
        "completed": sum(1 for r in tasks if r["due_state"] == "已完成"),
        "overdue": sum(1 for r in tasks if r["due_state"] == "逾期"),
        "due_soon": sum(1 for r in tasks if r["due_state"] == "临期"),
        "stock_note": _("任务完成只记录过程状态，不产生库存过账；入库仍以 Work Order / Stock Entry 为准"),
    }
