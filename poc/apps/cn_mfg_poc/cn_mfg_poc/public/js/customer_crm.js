// CRM-100：正式客户详情补「新建销售订单」与「客户中心」入口。
// 只做路由与默认值预填，订单仍由用户在原生表单里保存/提交（不自动 submit）。

frappe.ui.form.on("Customer", {
	refresh(frm) {
		if (frm.is_new()) return;

		frm.add_custom_button(__("新建销售订单"), () => {
			frappe.route_options = { customer: frm.doc.name };
			frappe.new_doc("Sales Order");
		}).addClass("btn-primary");

		frm.add_custom_button(__("客户中心"), () => {
			window.open("/customer_detail?name=" + encodeURIComponent(frm.doc.name), "_blank");
		});
	},
});
