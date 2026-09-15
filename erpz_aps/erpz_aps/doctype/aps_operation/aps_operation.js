// Copyright (c) 2026, ERPZ and contributors
// For license information, please see license.txt

frappe.ui.form.on("APS Operation", {
	refresh(frm) {
		calculate_unit_time(frm);
	},
	batch_qty(frm) {
		calculate_unit_time(frm);
	},
	cycle_time_mins(frm) {
		calculate_unit_time(frm);
	}
});

function calculate_unit_time(frm) {
	const batch = flt(frm.doc.batch_qty);
	const cycle = flt(frm.doc.cycle_time_mins);
	if (batch > 0 && cycle > 0) {
		const unit = cycle / batch;
		frm.set_value("time_per_unit_mins", flt(unit, 4));
	}
}
