# -*- coding: utf-8 -*-
"""POC-03 国产 PC 导航（幂等，可重复执行）。

做三件事，全部使用 Frappe/ERPNext 原生机制，不重写前端、不删 DocType、
不修改任何 erpnext/frappe 标准记录：

1. 在自有模块 CN MFG POC 下创建 10 个中文一级菜单（Workspace）。
   - roles 子表控制哪些角色可见（原生权限门，Workspace.is_permitted 校验）；
   - links 子表组织卡片，每条链接按用户文档权限自动过滤（is_item_allowed），
     某角色看不到任何链接的卡片会整卡隐藏。
2. 给 7 个 POC 测试用户设置 block_modules：除 CN MFG POC 外全部屏蔽。
   屏蔽只影响导航（is_module_visible），不影响文档权限（DocPerm 仍生效），
   因此「界面隐藏 != 服务端授权」由 DocPerm 独立保证。
   Administrator 不动，保留完整后台用于维护。
3. 写入模块显示名翻译：CN MFG POC → 轻制造（DB Translation，优先于 .po）。

运行方式：
  bench --site erpnext-poc.localhost migrate          # 作为补丁自动执行
  bench --site erpnext-poc.localhost execute \\
      cn_mfg_poc.patches.v0_0_2.setup_navigation.execute   # 手动重放（幂等）
"""

import frappe
import json as _json

MODULE = "CN MFG POC"

# (label, sequence, roles, [(卡片标题, [(显示名, 类型, 目标), ...]), ...])
WORKSPACES = [
    ("工作台", 1, [], [
        ("日常待办", [("待办事项", "DocType", "ToDo")]),
        ("业务概览", [
            ("销售订单", "DocType", "Sales Order"),
            ("采购订单", "DocType", "Purchase Order"),
            ("生产工单", "DocType", "Work Order"),
            ("交货单", "DocType", "Delivery Note"),
        ]),
        ("摘要报表", [
            ("销售分析", "Report", "Sales Analytics"),
            ("工单汇总", "Report", "Work Order Summary"),
            ("库存余额", "Report", "Stock Balance"),
        ]),
    ]),
    ("客户与销售", 2, ["Sales User"], [
        ("销售过程", [
            ("销售线索", "DocType", "Lead"),
            ("商机", "DocType", "Opportunity"),
            ("报价单", "DocType", "Quotation"),
            ("销售订单", "DocType", "Sales Order"),
        ]),
        ("客户资料", [
            ("客户", "DocType", "Customer"),
            ("联系人", "DocType", "Contact"),
            ("地址", "DocType", "Address"),
        ]),
        ("交付与回款", [
            ("交货单", "DocType", "Delivery Note"),
            ("销售发票", "DocType", "Sales Invoice"),
            ("收付款", "DocType", "Payment Entry"),
        ]),
    ]),
    ("设计与生产", 3, ["Manufacturing User"], [
        ("产品设计", [
            ("物料", "DocType", "Item"),
            ("物料清单", "DocType", "BOM"),
            ("工艺路线", "DocType", "Routing"),
            ("工序", "DocType", "Operation"),
        ]),
        ("生产计划", [
            ("生产计划", "DocType", "Production Plan"),
            ("物料需求", "DocType", "Material Request"),
        ]),
        ("生产执行", [
            ("生产工单", "DocType", "Work Order"),
            ("生产任务单", "DocType", "Job Card"),
            ("物料移动", "DocType", "Stock Entry"),
        ]),
        ("生产资源", [("工作站", "DocType", "Workstation")]),
    ]),
    ("采购管理", 4, ["Purchase User"], [
        ("采购过程", [
            ("物料需求", "DocType", "Material Request"),
            ("询价单", "DocType", "Request for Quotation"),
            ("供应商报价", "DocType", "Supplier Quotation"),
            ("采购订单", "DocType", "Purchase Order"),
        ]),
        ("供应商资料", [
            ("供应商", "DocType", "Supplier"),
            ("联系人", "DocType", "Contact"),
            ("地址", "DocType", "Address"),
        ]),
        ("入库与发票", [
            ("采购入库", "DocType", "Purchase Receipt"),
            ("采购发票", "DocType", "Purchase Invoice"),
        ]),
    ]),
    ("仓库管理", 5, ["Stock User"], [
        ("库存查询", [
            ("库存余额", "Report", "Stock Balance"),
            ("库存账龄", "Report", "Stock Ageing"),
            ("物料", "DocType", "Item"),
            ("仓库", "DocType", "Warehouse"),
            ("批次", "DocType", "Batch"),
            ("序列号", "DocType", "Serial No"),
        ]),
        ("出入库与盘点", [
            ("物料移动", "DocType", "Stock Entry"),
            ("库存盘点", "DocType", "Stock Reconciliation"),
        ]),
        ("领料与产成品", [
            ("物料需求", "DocType", "Material Request"),
            ("生产工单", "DocType", "Work Order"),
        ]),
    ]),
    ("物流交付", 6, ["Sales User", "Stock User"], [
        ("交付", [
            ("交货单", "DocType", "Delivery Note"),
            ("送货行程", "DocType", "Delivery Trip"),
        ]),
    ]),
    ("财务管理", 7, ["Accounts User"], [
        ("开票", [
            ("销售发票", "DocType", "Sales Invoice"),
            ("采购发票", "DocType", "Purchase Invoice"),
        ]),
        ("收付款", [
            ("收付款", "DocType", "Payment Entry"),
            ("日记账", "DocType", "Journal Entry"),
            ("会计科目", "DocType", "Account"),
        ]),
        ("往来对账", [
            ("应收账龄", "Report", "Accounts Receivable"),
            ("应付账龄", "Report", "Accounts Payable"),
            ("总账", "Report", "General Ledger"),
        ]),
    ]),
    ("经营报表", 8, [
        "Sales Manager", "Purchase Manager", "Stock Manager",
        "Manufacturing Manager", "Accounts Manager", "System Manager",
    ], [
        ("订单与交期", [
            ("销售分析", "Report", "Sales Analytics"),
            ("采购分析", "Report", "Purchase Analytics"),
            ("工单汇总", "Report", "Work Order Summary"),
            ("任务单汇总", "Report", "Job Card Summary"),
        ]),
        ("库存与成本", [
            ("库存余额", "Report", "Stock Balance"),
            ("工单库存", "Report", "Work Order Stock Report"),
            ("库存账龄", "Report", "Stock Ageing"),
        ]),
        ("财务", [
            ("应收账龄", "Report", "Accounts Receivable"),
            ("应付账龄", "Report", "Accounts Payable"),
            ("总账", "Report", "General Ledger"),
        ]),
    ]),
    ("基础资料", 9, [], [
        ("主数据", [
            ("物料", "DocType", "Item"),
            ("客户", "DocType", "Customer"),
            ("供应商", "DocType", "Supplier"),
            ("仓库", "DocType", "Warehouse"),
            ("员工", "DocType", "Employee"),
        ]),
        ("分类与单位", [
            ("物料组", "DocType", "Item Group"),
            ("客户组", "DocType", "Customer Group"),
            ("供应商组", "DocType", "Supplier Group"),
            ("计量单位", "DocType", "UOM"),
        ]),
    ]),
    ("系统设置", 10, ["System Manager"], [
        ("用户与权限", [
            ("用户", "DocType", "User"),
            ("角色", "DocType", "Role"),
            ("角色档案", "DocType", "Role Profile"),
            ("用户权限", "DocType", "User Permission"),
        ]),
        ("公司与参数", [
            ("公司", "DocType", "Company"),
            ("货币", "DocType", "Currency"),
            ("财年", "DocType", "Fiscal Year"),
            ("打印格式", "DocType", "Print Format"),
            ("系统设置", "DocType", "System Settings"),
        ]),
    ]),
]

TRANSLATIONS = [("CN MFG POC", "轻制造")]

# 7 个 POC 业务用户（Administrator 不在列表中，保留完整后台）
POC_USER_EMAILS = [
    "wangming@erpnext-poc.localhost",    # 销售 Sales User/Manager
    "liugong@erpnext-poc.localhost",     # 设计 Manufacturing User/Manager
    "chengong@erpnext-poc.localhost",    # 采购 Purchase User/Manager
    "zhanggong@erpnext-poc.localhost",   # 仓库 Stock User/Manager
    "ligong@erpnext-poc.localhost",      # 车间 Manufacturing User
    "zhoukaiji@erpnext-poc.localhost",   # 财务 Accounts User/Manager
    "zhaojingli@erpnext-poc.localhost",  # 管理 System Manager + 全部业务角色
]


def _target_exists(link_type: str, target: str) -> bool:
    if link_type == "Report":
        return bool(frappe.db.exists("Report", target))
    return bool(frappe.db.exists("DocType", target))


def _block_id() -> str:
    import secrets

    return secrets.token_hex(5)


def _upsert_workspaces():
    created, updated, skipped_links = [], [], []
    for label, seq, roles, cards in WORKSPACES:
        if frappe.db.exists("Workspace", label):
            doc = frappe.get_doc("Workspace", label)
            updated.append(label)
        else:
            doc = frappe.new_doc("Workspace")
            doc.label = label
            created.append(label)
        doc.title = label
        doc.module = MODULE
        doc.public = 1
        doc.is_hidden = 0
        doc.sequence_id = seq
        doc.type = "Workspace"
        # 与 erpnext 自带工作台同模式：app 拥有的 standard 工作台，
        # 开发者模式下可导出为 app 内 JSON（见 poc/scripts/export_workspaces.py）
        doc.standard = 1

        # 重建 links（Card Break + Link），目标不存在的条目跳过并记录
        doc.set("links", [])
        content_blocks = []
        for card_label, items in cards:
            doc.append("links", {"type": "Card Break", "label": card_label})
            kept = 0
            for show, ltype, target in items:
                if not _target_exists(ltype, target):
                    skipped_links.append(f"{label}/{card_label}/{target}")
                    continue
                doc.append("links", {
                    "type": "Link",
                    "label": show,
                    "link_type": ltype,
                    "link_to": target,
                })
                kept += 1
            if kept:
                # content 块引用卡片名（= Card Break label），桌面端按块渲染
                content_blocks.append({
                    "id": _block_id(),
                    "type": "card",
                    "data": {"card_name": card_label, "col": 4},
                })
        doc.content = _json.dumps(content_blocks, ensure_ascii=False)

        # 重建 roles 子表（角色可见性门）
        doc.set("roles", [])
        for r in roles:
            doc.append("roles", {"role": r})

        doc.flags.ignore_permissions = True
        doc.save(ignore_permissions=True)

    return created, updated, skipped_links


def apply_module_blocks():
    """仅导航层：给 7 个 POC 用户屏蔽除自有模块外的全部模块。"""
    blocked_users = []
    all_modules = frappe.get_all("Module Def", pluck="name")
    to_block = [m for m in all_modules if m != MODULE]

    for email in POC_USER_EMAILS:
        if not frappe.db.exists("User", email):
            continue
        user = frappe.get_doc("User", email)
        user.set("block_modules", [])
        for m in to_block:
            user.append("block_modules", {"module": m})
        user.flags.ignore_permissions = True
        user.save(ignore_permissions=True)
        blocked_users.append(email)
    return blocked_users, to_block


def _ensure_translations():
    """模块显示名等站点级 zh 翻译（DB Translation 优先于 .po，与 POC-02 同机制）。"""
    written = 0
    for source_text, translated in TRANSLATIONS:
        existing = frappe.db.get_value(
            "Translation",
            {"language": "zh", "source_text": source_text},
            ["name", "translated_text"],
            as_dict=True,
        )
        if existing:
            if existing.translated_text != translated:
                frappe.db.set_value("Translation", existing.name, "translated_text", translated)
                written += 1
            continue
        frappe.get_doc(
            {
                "doctype": "Translation",
                "language": "zh",
                "source_text": source_text,
                "translated_text": translated,
            }
        ).insert(ignore_permissions=True)
        written += 1
    return written


def execute():
    created, updated, skipped = _upsert_workspaces()
    blocked, block_list = apply_module_blocks()
    translated = _ensure_translations()
    frappe.db.commit()
    frappe.clear_cache()
    print("WORKSPACE_CREATED:", created)
    print("WORKSPACE_UPDATED:", updated)
    print("SKIPPED_LINKS:", skipped)
    print("MODULES_BLOCKED_FOR:", blocked)
    print("BLOCKED_MODULE_COUNT:", len(block_list))
    print("TRANSLATIONS_WRITTEN:", translated)
