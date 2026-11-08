// UX-96B：BOM 详情「引用关系」——只看显式引用（订单行 bom_no == 本 BOM），
// 反向列出销售订单行与工单，并按当前账号的数据权限过滤（过滤在服务端完成）。

frappe.ui.form.on("BOM", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("引用关系"), () => show_references(frm));
	},
});

function esc(v) {
	return frappe.utils.escape_html(v == null ? "" : String(v));
}

function show_references(frm) {
	frappe.call({
		method: "cn_mfg_poc.bom_link.bom_references",
		type: "GET",
		args: { bom: frm.doc.name },
		freeze: true,
		callback(r) {
			const d = r.message || {};
			const soRows = d.sales_orders || [];
			const woRows = d.work_orders || [];

			let html = `<p class="text-muted small">${esc(d.explicit_only_note || "")}</p>`;
			html += `<h6 class="mt-3">${__("销售订单行")}（${soRows.length}）</h6>`;
			if (!soRows.length) {
				html += `<p class="text-muted">${__("暂无订单显式选用本 BOM。")}</p>`;
			} else {
				html +=
					'<table class="table table-bordered table-sm"><thead><tr>' +
					["订单号", "客户", "产品行", "数量", "状态", "交期"]
						.map((h) => `<th>${esc(__(h))}</th>`)
						.join("") +
					"</tr></thead><tbody>";
				soRows.forEach((o) => {
					html +=
						"<tr>" +
						`<td><a href="${esc(o.url)}" target="_blank">${esc(o.sales_order)}</a></td>` +
						`<td>${esc(o.customer)}</td>` +
						`<td>${esc(o.item_code)}（第 ${esc(o.line_idx)} 行）</td>` +
						`<td>${esc(o.qty)}</td>` +
						`<td>${esc(__(o.status))}${Number(o.docstatus) === 0 && String(__(o.status)).indexOf("草稿") < 0 ? " · 草稿" : ""}</td>` +
						`<td>${esc(o.delivery_date || "—")}</td>` +
						"</tr>";
				});
				html += "</tbody></table>";
			}

			html += `<h6 class="mt-3">${__("生产工单")}（${woRows.length}）</h6>`;
			if (!woRows.length) {
				html += `<p class="text-muted">${__("暂无工单引用本 BOM（或您无权查看对应工单）。")}</p>`;
			} else {
				html +=
					'<table class="table table-bordered table-sm"><thead><tr>' +
					["工单号", "产品", "计划数量", "已生产", "状态", "来源订单"]
						.map((h) => `<th>${esc(__(h))}</th>`)
						.join("") +
					"</tr></thead><tbody>";
				woRows.forEach((w) => {
					html +=
						"<tr>" +
						`<td><a href="${esc(w.url)}" target="_blank">${esc(w.work_order)}</a></td>` +
						`<td>${esc(w.production_item)}</td>` +
						`<td>${esc(w.qty)}</td>` +
						`<td>${esc(w.produced_qty)}</td>` +
						`<td>${esc(__(w.status))}${Number(w.docstatus) === 0 && String(__(w.status)).indexOf("草稿") < 0 ? " · 草稿" : ""}</td>` +
						`<td>${esc(w.sales_order || "—")}</td>` +
						"</tr>";
				});
				html += "</tbody></table>";
			}

			html += `<p class="text-muted small mt-3">${esc(d.scope_note || "")}</p>`;
			frappe.msgprint({
				title: __("BOM 引用关系 · {0}", [d.bom]),
				message: html,
				wide: true,
			});
		},
	});
}
