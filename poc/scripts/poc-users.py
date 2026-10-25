# -*- coding: utf-8 -*-
"""POC 测试用户创建脚本（幂等：存在则跳过/补角色）。

在容器内运行：
  cd /workspace/development/frappe-bench && ./env/bin/python poc_users.py

用户列表见 docs/poc/TEST_DATA.md「用户/员工」。
真实登录名使用本地邮箱规范，密码不在本文件中（统一走 setup_users 的随机/固定口令，
由 D:/ERP/poc/CREDENTIALS.local.md 记录）。
"""
import frappe

frappe.init(site="erpnext-poc.localhost",
            sites_path="/workspace/development/frappe-bench/sites")
frappe.connect()

USERS = [
    # (full_name, local_part, roles, department_note)
    ("王明", "wangming", ["Sales User", "Sales Manager"], "销售"),
    ("刘工", "liugong", ["Manufacturing User", "Manufacturing Manager"], "设计"),
    ("陈工", "chengong", ["Purchase User", "Purchase Manager"], "采购"),
    ("张工", "zhanggong", ["Stock User", "Stock Manager"], "仓库"),
    ("李工", "ligong", ["Manufacturing User"], "车间"),
    ("周会计", "zhoukaiji", ["Accounts User", "Accounts Manager"], "财务"),
    ("赵经理", "zhaojingli", ["System Manager", "Sales User", "Stock User",
                              "Manufacturing User", "Purchase User", "Accounts User"], "管理"),
]

DOMAIN = "erpnext-poc.localhost"


def ensure_roles(role_names):
    for r in role_names:
        if not frappe.db.exists("Role", r):
            frappe.get_doc({"doctype": "Role", "role_name": r}).insert(ignore_permissions=True)


def run(password: str):
    ensure_roles([r for _, _, rs, _ in USERS for r in rs])

    created, updated = [], []
    for full_name, local_part, roles, note in USERS:
        email = f"{local_part}@{DOMAIN}"
        if not frappe.db.exists("User", email):
            doc = frappe.get_doc({
                "doctype": "User",
                "email": email,
                "first_name": full_name,
                "full_name": f"{full_name}（{note}）",
                "enabled": 1,
                "new_password": password,
                "send_welcome_email": 0,
                # 语言不设置 → 走 System Settings.language 回退，这正是 POC-02 要验证的
                "language": "",
                "time_zone": "Asia/Shanghai",
            })
            doc.insert(ignore_permissions=True)
            created.append(email)
        else:
            doc = frappe.get_doc("User", email)

        existing = set(d.role for d in doc.get("roles") or [])
        for r in roles:
            if r not in existing:
                doc.append("roles", {"role": r})
        doc.save(ignore_permissions=True)
        updated.append(email)

    frappe.db.commit()
    print("CREATED:", created)
    print("ENSURED:", updated)


if __name__ == "__main__":
    # 默认统一初始口令；仅用于本机隔离 POC 站点
    run("Poc@2026user")
