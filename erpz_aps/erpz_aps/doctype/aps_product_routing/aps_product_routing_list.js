// Copyright (c) 2026, ERPZ and contributors
// For license information, please see license.txt

frappe.listview_settings["APS Product Routing"] = {
	onload(listview) {
		listview.page.add_button(__("Importar Roteiro (Excel)"), function() {
			show_routing_import_dialog(listview);
		}, { btn_class: "btn-primary" });

		listview.page.add_button(__("Baixar Modelo Excel"), function() {
			window.open("/api/method/erpz_aps.api.download_routing_template");
		});
	}
};

function show_routing_import_dialog(parent_view) {
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
						Informe a estação de trabalho titular, a quantidade de referência (ex: 5 peças), o tempo (ex: 15 min), a sobreposição em % e o recurso alternativo do produto.<br>
						Todas as linhas serão importadas e agrupadas automaticamente pelo código do produto.
						<div class="mt-2">
							<a href="/api/method/erpz_aps.api.download_routing_template" class="btn btn-xs btn-primary" target="_blank">
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
		primary_action_label: __("Importar Roteiros"),
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
							title: __("Roteiros Importados"),
							indicator: "green",
							message: __("Foram importados {0} roteiros com {1} operações sequenciadas com sucesso!", [r.message.imported_routings, r.message.total_operations])
						});
						parent_view.refresh();
					}
				}
			});
		}
	});
	d.show();
}
