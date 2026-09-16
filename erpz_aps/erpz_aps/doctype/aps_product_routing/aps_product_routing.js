// Copyright (c) 2026, ERPZ and contributors
// For license information, please see license.txt

frappe.ui.form.on("APS Product Routing", {
	refresh(frm) {
		frm.add_custom_button(__("Importar Roteiro (Excel)"), function() {
			show_routing_import_dialog_form(frm);
		}, __("Ações"));

		frm.add_custom_button(__("Baixar Modelo Excel"), function() {
			const item = frm.doc.item_code ? ("?item_code=" + frm.doc.item_code) : "";
			window.open("/api/method/erpz_aps.api.download_routing_template" + item);
		}, __("Ações"));
	}
});

frappe.ui.form.on("APS Routing Operation Item", {
	batch_qty(frm, cdt, cdn) {
		calc_unit_time(frm, cdt, cdn);
	},
	cycle_time_mins(frm, cdt, cdn) {
		calc_unit_time(frm, cdt, cdn);
	}
});

function calc_unit_time(frm, cdt, cdn) {
	let row = locals[cdt][cdn];
	let batch = flt(row.batch_qty);
	let cycle = flt(row.cycle_time_mins);
	if (batch > 0 && cycle > 0) {
		frappe.model.set_value(cdt, cdn, "time_per_unit_mins", flt(cycle / batch, 4));
	}
}

function show_routing_import_dialog_form(frm) {
	let d = new frappe.ui.Dialog({
		title: __("Importar Roteiro Produtivo por Produto (Excel)"),
		fields: [
			{
				fieldtype: "HTML",
				fieldname: "instructions",
				options: `
					<div class="alert alert-info small mb-3">
						<b>Instruções para Cadastro em Massa do Roteiro:</b><br>
						No modelo Excel, cadastre todas as operações de cada produto linha por linha (ex: linha 1: 10 - Cortar, linha 2: 20 - Dobrar, linha 3: 30 - Embalar).<br>
						Informe a estação titular, a quantidade de referência (ex: 5 peças), o tempo (ex: 15 min), a sobreposição em % e o recurso alternativo do produto.
						<div class="mt-2">
							<a href="/api/method/erpz_aps.api.download_routing_template?item_code=${frm.doc.item_code || ''}" class="btn btn-xs btn-primary" target="_blank">
								<i class="octicon octicon-cloud-download"></i> Baixar Modelo Excel (.xlsx)
							</a>
						</div>
					</div>
				`
			},
			{
				label: __("Arquivo Excel (.xlsx)"),
				fieldname: "excel_file",
				fieldtype: "Attach",
				reqd: 1
			}
		],
		primary_action_label: __("Importar Roteiro"),
		primary_action(values) {
			d.hide();
			frappe.show_alert({ message: __("Processando roteiros produtivos..."), indicator: "blue" });
			frappe.call({
				method: "erpz_aps.api.import_product_routing_excel",
				args: { file_url: values.excel_file },
				freeze: true,
				freeze_message: __("Importando operações e recursos alternativos..."),
				callback: function(r) {
					if (r.message && r.message.success) {
						frappe.msgprint({
							title: __("Roteiro Importado"),
							indicator: "green",
							message: __("Roteiro importado com sucesso! {0} operações atualizadas.", [r.message.total_operations])
						});
						frm.reload_doc();
					}
				}
			});
		}
	});
	d.show();
}
