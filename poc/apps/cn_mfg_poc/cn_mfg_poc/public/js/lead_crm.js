// CRM-100：客户报备（Lead）详情一键「转为正式客户」。
// 真正的写操作在 cn_mfg_poc.crm.convert_lead（服务端校验角色与权限、幂等）；
// 这里只加按钮并处理返回，不复制任何业务规则。

frappe.ui.form.on("Lead", {
	refresh(frm) {
		if (frm.is_new()) return;

		frm.add_custom_button(__("客户中心"), () => {
			window.open("/customer_center?tab=lead", "_blank");
		});

		if (frm.doc.customer) {
			frm.add_custom_button(__("打开客户"), () => {
				frappe.set_route("Form", "Customer", frm.doc.customer);
			});
			return;
		}

		if (frm.doc.status === "Converted") return;

		frm.add_custom_button(__("转为正式客户"), () => convert_lead(frm)).addClass("btn-primary");
	},
});

function convert_lead(frm) {
	frappe.confirm(
		__("将报备 {0} 转为正式客户？首次报备人会保留为 {1}。", [
			frm.doc.name,
			frm.doc.lead_owner || __("当前用户"),
		]),
		() => {
			frappe.call({
				method: "cn_mfg_poc.crm.convert_lead",
				type: "POST",
				args: { lead: frm.doc.name },
				freeze: true,
				freeze_message: __("正在创建正式客户…"),
				callback(r) {
					const d = r.message || {};
					if (d.created) {
						frappe.show_alert({
							message: __("已转为正式客户 {0}", [d.customer]),
							indicator: "green",
						});
						frappe.set_route("Form", "Customer", d.customer);
					} else if (d.existing_customer) {
						frappe.msgprint({
							title: __("已有同名客户"),
							message: d.message || __("已存在同名正式客户 {0}", [d.existing_customer]),
							indicator: "orange",
						});
						frappe.set_route("Form", "Customer", d.existing_customer);
					} else {
						frm.reload_doc();
						frappe.show_alert({ message: d.message || __("已处理"), indicator: "blue" });
					}
				},
			});
		}
	);
}
