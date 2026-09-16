// Copyright (c) 2026, ERPZ and contributors
// For license information, please see license.txt

frappe.ui.form.on("APS Product Routing", {
	refresh(frm) {
		if (frm.doc.doctype === "APS Product Routing") {
			frm.add_custom_button(__("Importar Roteiro (Excel)"), function() {
				frappe.call({
					method: "erpz_aps.api.show_routing_import_dialog",
					args: { item_code: frm.doc.item_code }
				});
			}, __("Ações"));
			frm.add_custom_button(__("Baixar Modelo Excel"), function() {
				window.open("/api/method/erpz_aps.api.download_routing_template");
			}, __("Ações"));
		}
	}
});

frappe.ui.form.on("APS Routing Operation Item", {
	batch_qty(frm, cdt, cdn) {
		calc_item_unit_time(frm, cdt, cdn);
	},
	cycle_time_mins(frm, cdt, cdn) {
		calc_item_unit_time(frm, cdt, cdn);
	}
});

function calc_item_unit_time(frm, cdt, cdn) {
	let row = locals[cdt][cdn];
	let batch = flt(row.batch_qty);
	let cycle = flt(row.cycle_time_mins);
	if (batch > 0 && cycle > 0) {
		frappe.model.set_value(cdt, cdn, "time_per_unit_mins", flt(cycle / batch, 4));
	}
}
