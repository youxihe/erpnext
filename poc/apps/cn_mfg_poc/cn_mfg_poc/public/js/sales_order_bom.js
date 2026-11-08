// UX-96B：销售订单行级「本单 BOM」显式选用。
// 权威字段仍是原生 Sales Order Item.bom_no；本脚本只做选择器、过滤与提示，
// 一致性/有效性的最终校验在服务端 cn_mfg_poc.bom_link.validate_sales_order_bom。

frappe.ui.form.on("Sales Order", {
	refresh(frm) {
		// 行内 BOM 只能选同产品、已提交、未停用的 BOM
		frm.set_query("bom_no", "items", function (doc, cdt, cdn) {
			const row = locals[cdt][cdn] || {};
			return { filters: { item: row.item_code || "", docstatus: 1, is_active: 1 } };
		});

		const is_production_draft = frm.doc.docstatus === 0 && frm.doc.business_type === "生产";
		if (is_production_draft) {
			frm.add_custom_button(
				__("选择本单 BOM"),
				() => choose_bom(frm),
				__("物料清单")
			);
		}
		toggle_bom_column(frm);
		show_bom_intro(frm);
	},

	business_type(frm) {
		toggle_bom_column(frm);
		show_bom_intro(frm);
	},
});

// 手工在物料表改 BOM（含清空）也算人工决定：清空=取消确认，填入=确认
frappe.ui.form.on("Sales Order Item", {
	bom_no(frm) {
		if (frm.doc.docstatus !== 0) return;
		const grid = frm.fields_dict.items && frm.fields_dict.items.grid;
		if (!grid) return;
		(frm.doc.items || []).forEach((row) => {
			const want = row.bom_no ? 1 : 0;
			if ((row.custom_bom_confirmed || 0) !== want) {
				frappe.model.set_value(row.doctype, row.name, "custom_bom_confirmed", want);
			}
		});
		show_bom_intro(frm);
	},
});

function toggle_bom_column(frm) {
	const grid = frm.fields_dict.items && frm.fields_dict.items.grid;
	if (!grid) return;
	const show = frm.doc.business_type === "生产";
	grid.update_docfield_property("bom_no", "hidden", show ? 0 : 1);
	grid.update_docfield_property("bom_no", "in_list_view", show ? 1 : 0);
	frm.refresh_field("items");
}

function show_bom_intro(frm) {
	if (frm.doc.docstatus !== 0 || frm.doc.business_type !== "生产") return;
	const items = frm.doc.items || [];
	if (!items.length) return;
	// 只有人工确认过的行才算确认；ERPNext 新建行时自动带入的默认 BOM 不算
	const pending = items.filter((r) => !r.custom_bom_confirmed);
	if (pending.length) {
		frm.set_intro(
			__(
				"有 {0} 行尚未确认本单 BOM：订单执行概览里的物料需求会按产品默认 BOM 作为「建议」展示，" +
					"不代表本单已确认。请点「选择本单 BOM」。",
				[pending.length]
			),
			"yellow"
		);
	} else {
		frm.set_intro(__("全部物料行已选用本单 BOM。"), "blue");
	}
}

function choose_bom(frm) {
	const items = frm.doc.items || [];
	if (!items.length) {
		frappe.msgprint(__("请先添加物料行。"));
		return;
	}
	const labels = items.map(
		(r, i) =>
			`${i + 1} · ${r.item_code} × ${r.qty}` +
			(r.custom_bom_confirmed
				? ` · 已确认 ${r.bom_no || ""}`
				: r.bom_no
				? ` · 未确认（默认带入 ${r.bom_no}）`
				: " · 未确认")
	);

	const dialog = new frappe.ui.Dialog({
		title: __("选择本单 BOM"),
		fields: [
			{
				fieldname: "row",
				fieldtype: "Select",
				label: __("物料行"),
				options: labels,
				default: labels[0],
				reqd: 1,
			},
			{
				fieldname: "bom",
				fieldtype: "Select",
				label: __("本单 BOM"),
				options: [],
				reqd: 1,
				description: __(
					"只列出同产品、已提交且有效的 BOM。默认 BOM 只是建议；写进订单行才代表本单已确认。"
				),
			},
		],
		primary_action_label: __("确认选用"),
		primary_action(values) {
			const idx = labels.indexOf(values.row);
			const row = items[idx];
			if (!row) return;
			frappe.model.set_value(row.doctype, row.name, "bom_no", values.bom);
			// 人工确认标记：让服务端和概览页能区分「默认带入」与「人工确认」
			frappe.model.set_value(row.doctype, row.name, "custom_bom_confirmed", 1);
			dialog.hide();
			frm.refresh_field("items");
			// 立即刷新顶部提示，避免选完仍显示“尚未确认本单 BOM”
			show_bom_intro(frm);
			frappe.show_alert({
				message: __("第 {0} 行已选用 BOM {1}", [idx + 1, values.bom]),
				indicator: "green",
			});
		},
	});

	const load_options = (idx) => {
		const row = items[idx];
		if (!row || !row.item_code) {
			dialog.set_df_property("bom", "options", []);
			return;
		}
		frappe.call({
			method: "cn_mfg_poc.bom_link.bom_options",
			type: "GET",
			args: { item_code: row.item_code },
			callback(r) {
				const data = r.message || {};
				const opts = data.options || [];
				if (!opts.length) {
					dialog.set_df_property("bom", "options", []);
					frappe.msgprint(
						__("物料 {0} 没有已提交且有效的 BOM，请先创建 BOM。", [row.item_code])
					);
					return;
				}
				dialog.set_df_property("bom", "options", opts.map((o) => o.bom));
				const prefer = row.bom_no || data.default_bom || opts[0].bom;
				dialog.set_value("bom", prefer);
			},
		});
	};

	dialog.fields_dict.row.$input.on("change", () => {
		load_options(labels.indexOf(dialog.get_value("row")));
	});
	load_options(0);
	dialog.show();
}
