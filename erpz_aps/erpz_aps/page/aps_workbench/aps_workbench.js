// Copyright (c) 2026, ERPZ and contributors
// For license information, please see license.txt

function init_aps_workbench(wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Programação da Produção & Gantt (APS/CRP)"),
		single_column: true
	});

	frappe.aps_workbench = new APSWorkbench(page);
}

function show_aps_workbench(wrapper) {
	if (frappe.aps_workbench && frappe.route_options && frappe.route_options.ticket) {
		frappe.aps_workbench.ticket_field.set_value(frappe.route_options.ticket);
		frappe.route_options = null;
	}
}

frappe.pages["aps_workbench"].on_page_load = init_aps_workbench;
frappe.pages["aps_workbench"].on_page_show = show_aps_workbench;

frappe.pages["aps-workbench"] = frappe.pages["aps_workbench"];

class APSWorkbench {
	constructor(page) {
		this.page = page;
		this.current_ticket = null;
		this.active_tab = "gantt";
		this.chart = null;
		this.gantt_data = null;
		this.day_width = 140; // pixels per day
		this.min_date = null;
		this.max_date = null;
		this.init();
	}

	init() {
		this.setup_header();
		this.render_layout();
		this.bind_events();
		this.load_initial_ticket();
	}

	setup_header() {
		const me = this;

		// Ticket Selector
		this.ticket_field = this.page.add_field({
			fieldname: "aps_ticket",
			label: __("Ticket APS"),
			fieldtype: "Link",
			options: "APS Ticket",
			change() {
				const val = me.ticket_field.get_value();
				if (val && val !== me.current_ticket) {
					me.current_ticket = val;
					me.reload_all();
				}
			}
		});

		// Button: Novo Ticket
		this.page.add_button(__("Novo Ticket"), function() {
			frappe.new_doc("APS Ticket");
		});

		// Button: Calcular APS
		this.btn_calculate = this.page.add_button(__("Calcular APS"), function() {
			me.run_calculation();
		}, { icon: "refresh" });

		// Button: Aprovar Cenário
		this.btn_approve = this.page.add_button(__("Aprovar Cenário"), function() {
			me.approve_scenario();
		});

		// Button: Efetivar Programação
		this.btn_execute = this.page.add_button(__("Efetivar Programação"), function() {
			me.execute_scenario();
		}, { btn_class: "btn-danger" });

		// Button: Ver Ticket MRP
		this.btn_mrp = this.page.add_button(__("Ver Ticket MRP"), function() {
			if (me.current_mrp_ticket) {
				frappe.set_route("mrp-workbench", { ticket: me.current_mrp_ticket });
			}
		});
		this.btn_mrp.hide();
	}

	render_layout() {
		this.$container = $(`
			<div class="aps-workbench">
				<!-- Stepper Card -->
				<div class="aps-header-card">
					<div class="d-flex justify-content-between align-items-center">
						<div>
							<h4 class="m-0 font-weight-bold" id="aps-ticket-title">Selecione um Ticket APS</h4>
							<small class="text-muted" id="aps-ticket-subtitle">Planejamento de Capacidade (CRP) e Sequenciamento Avançado (APS)</small>
						</div>
						<div id="aps-status-badge"></div>
					</div>
					<div class="aps-stepper" id="aps-stepper">
						<div class="aps-step" data-step="1"><div class="aps-step-circle">1</div>Simulação</div>
						<div class="aps-step-line"></div>
						<div class="aps-step" data-step="2"><div class="aps-step-circle">2</div>Calculado</div>
						<div class="aps-step-line"></div>
						<div class="aps-step" data-step="3"><div class="aps-step-circle">3</div>Ajustado (Gantt)</div>
						<div class="aps-step-line"></div>
						<div class="aps-step" data-step="4"><div class="aps-step-circle">4</div>Aprovado</div>
						<div class="aps-step-line"></div>
						<div class="aps-step" data-step="5"><div class="aps-step-circle">5</div>Efetivado</div>
					</div>
				</div>

				<!-- KPI Cards -->
				<div class="aps-kpi-grid">
					<div class="aps-kpi-card">
						<span class="aps-kpi-title">Ordens Programadas</span>
						<span class="aps-kpi-val text-primary" id="kpi-orders">-</span>
					</div>
					<div class="aps-kpi-card">
						<span class="aps-kpi-title">Operações Sequenciadas</span>
						<span class="aps-kpi-val" id="kpi-operations">-</span>
					</div>
					<div class="aps-kpi-card">
						<span class="aps-kpi-title">Carga Total (Horas)</span>
						<span class="aps-kpi-val text-purple" id="kpi-hours">-</span>
					</div>
					<div class="aps-kpi-card">
						<span class="aps-kpi-title">Utilização Média</span>
						<span class="aps-kpi-val text-success" id="kpi-utilization">-</span>
					</div>
					<div class="aps-kpi-card">
						<span class="aps-kpi-title">Gargalos de Capacidade</span>
						<span class="aps-kpi-val text-danger" id="kpi-bottlenecks">-</span>
					</div>
					<div class="aps-kpi-card">
						<span class="aps-kpi-title">Ordens em Atraso</span>
						<span class="aps-kpi-val text-danger" id="kpi-delayed">-</span>
					</div>
				</div>

				<!-- Tabs Container -->
				<div class="aps-tabs-container">
					<div class="aps-nav-tabs">
						<div class="aps-nav-tab active" data-tab="gantt">
							<i class="octicon octicon-graph"></i> Programação & Gantt Interativo
						</div>
						<div class="aps-nav-tab" data-tab="crp">
							<i class="octicon octicon-dashboard"></i> Carga x Capacidade (CRP)
						</div>
						<div class="aps-nav-tab" data-tab="operations">
							<i class="octicon octicon-list-ordered"></i> Grade de Operações
						</div>
						<div class="aps-nav-tab" data-tab="history">
							<i class="octicon octicon-history"></i> Histórico de Ajustes
						</div>
					</div>

					<div class="aps-tab-content">
						<!-- Tab 1: Gantt -->
						<div class="aps-tab-pane" id="pane-gantt">
							<div class="d-flex justify-content-between align-items-center mb-3">
								<div class="d-flex gap-2 align-items-center">
									<small class="text-muted font-weight-bold">Dica:</small>
									<span class="small text-muted">Arraste uma operação na linha do tempo para reprogramar. A mudança propagará automaticamente em cadeia para todas as operações sucessoras.</span>
								</div>
								<div class="d-flex gap-2">
									<button class="btn btn-sm btn-default" id="btn-export-gantt"><i class="octicon octicon-file"></i> Exportar Gantt (Excel)</button>
									<button class="btn btn-sm btn-default" id="btn-refresh-gantt"><i class="octicon octicon-sync"></i> Atualizar Gantt</button>
								</div>
							</div>
							<div class="aps-gantt-wrap" id="aps-gantt-container">
								<div class="text-center text-muted p-5">Carregando cronograma da produção...</div>
							</div>
						</div>

						<!-- Tab 2: CRP -->
						<div class="aps-tab-pane d-none" id="pane-crp">
							<div id="aps-crp-chart" style="min-height: 280px; margin-bottom: 25px;"></div>
							<h6 class="font-weight-bold mb-3">Detalhamento de Carga x Capacidade por Posto</h6>
							<div class="table-responsive">
								<table class="table table-bordered table-sm" id="aps-crp-table">
									<thead>
										<tr>
											<th>Posto de Trabalho</th>
											<th>Data</th>
											<th>Capacidade Disponível (h)</th>
											<th>Carga Programada (h)</th>
											<th>Saldo (h)</th>
											<th>Utilização (%)</th>
											<th>Sobrecarga (h)</th>
											<th>Situação</th>
										</tr>
									</thead>
									<tbody id="aps-crp-tbody"></tbody>
								</table>
							</div>
						</div>

						<!-- Tab 3: Operations Grid -->
						<div class="aps-tab-pane d-none" id="pane-operations">
							<div class="d-flex justify-content-between align-items-center mb-3">
								<h6 class="font-weight-bold m-0">Operações Sequenciadas na Ordem do Gantt</h6>
								<button class="btn btn-sm btn-default" id="btn-export-ops"><i class="octicon octicon-file"></i> Exportar Operações (Excel)</button>
							</div>
							<div class="table-responsive">
								<table class="table table-bordered table-sm" id="aps-ops-table">
									<thead>
										<tr>
											<th width="40">#</th>
											<th>Início Programado</th>
											<th>Término Programado</th>
											<th>Posto de Trabalho</th>
											<th>Ordem de Produção</th>
											<th>Item</th>
											<th>Operação</th>
											<th>Duração</th>
											<th>Predecessora</th>
											<th>Situação</th>
											<th>Ações</th>
										</tr>
									</thead>
									<tbody id="aps-ops-tbody"></tbody>
								</table>
							</div>
						</div>

						<!-- Tab 4: History -->
						<div class="aps-tab-pane d-none" id="pane-history">
							<h6 class="font-weight-bold mb-2">Auditoria de Reprogramações e Movimentações no Gantt</h6>
							<div class="table-responsive">
								<table class="table table-bordered table-sm" id="aps-hist-table">
									<thead>
										<tr>
											<th>Data/Hora</th>
											<th>Usuário</th>
											<th>Ordem</th>
											<th>Operação</th>
											<th>Início Anterior</th>
											<th>Novo Início</th>
											<th>Posto</th>
											<th>Operações Impactadas</th>
											<th>Detalhes</th>
										</tr>
									</thead>
									<tbody id="aps-hist-tbody"></tbody>
								</table>
							</div>
						</div>
					</div>
				</div>
			</div>
		`).appendTo(this.page.main);
	}

	bind_events() {
		const me = this;

		// Tab switching
		this.$container.find(".aps-nav-tab").on("click", function() {
			const tab = $(this).data("tab");
			me.$container.find(".aps-nav-tab").removeClass("active");
			$(this).addClass("active");
			me.$container.find(".aps-tab-pane").addClass("d-none");
			me.$container.find(`#pane-${tab}`).removeClass("d-none");
			me.active_tab = tab;

			if (tab === "gantt") {
				me.load_gantt();
			} else if (tab === "crp") {
				me.load_crp_chart();
			} else if (tab === "operations") {
				me.load_operations_grid();
			} else if (tab === "history") {
				me.load_adjustment_history();
			}
		});

		this.$container.find("#btn-refresh-gantt").on("click", function() {
			me.load_gantt();
		});

		this.$container.find("#btn-export-gantt, #btn-export-ops").on("click", function() {
			me.export_gantt_excel();
		});
	}

	load_initial_ticket() {
		const me = this;
		frappe.db.get_list("APS Ticket", {
			order_by: "creation desc",
			limit: 1
		}).then(records => {
			if (records && records.length > 0) {
				me.ticket_field.set_value(records[0].name);
			}
		});
	}

	reload_all() {
		if (!this.current_ticket) return;
		this.load_metrics();
		this.load_gantt();
	}

	load_metrics() {
		const me = this;
		frappe.call({
			method: "erpz_aps.api.get_ticket_dashboard_metrics",
			args: { ticket_name: this.current_ticket },
			callback: function(r) {
				if (r.message) {
					const m = r.message;
					$("#aps-ticket-title").text(`Ticket APS: ${me.current_ticket}`);
					$("#aps-ticket-subtitle").text(`Situação: ${m.status} | Tempo Processamento: ${m.execution_time}s`);
					$("#kpi-orders").text(m.total_orders);
					$("#kpi-operations").text(m.total_operations);
					$("#kpi-hours").text(m.total_scheduled_hours + "h");
					$("#kpi-utilization").text(m.average_utilization_pct + "%");
					$("#kpi-bottlenecks").text(m.total_bottlenecks);
					$("#kpi-delayed").text(m.delayed_orders_count);

					me.current_mrp_ticket = m.mrp_ticket;
					if (m.mrp_ticket) {
						me.btn_mrp.show().text(`Origem MRP: ${m.mrp_ticket}`);
					} else {
						me.btn_mrp.hide();
					}

					me.update_stepper(m.status);
					me.update_action_buttons(m.status);
				}
			}
		});
	}

	update_stepper(status) {
		const stepMap = {
			"Em Preparação": 1,
			"Processando": 1,
			"Calculado": 2,
			"Ajustado": 3,
			"Em Análise": 4,
			"Aprovado": 4,
			"Efetivado": 5
		};
		const activeStep = stepMap[status] || 1;
		$(".aps-step").each(function() {
			const s = parseInt($(this).data("step"));
			$(this).removeClass("active completed");
			if (s < activeStep) {
				$(this).addClass("completed");
			} else if (s === activeStep) {
				$(this).addClass("active");
			}
		});
	}

	update_action_buttons(status) {
		if (status === "Efetivado") {
			this.btn_execute.show().prop("disabled", true).addClass("disabled").text(__("Efetivado (Concluído)"));
			this.btn_approve.hide();
		} else if (status === "Aprovado") {
			this.btn_execute.show().prop("disabled", false).removeClass("disabled").text(__("Efetivar Programação"));
			this.btn_approve.hide();
		} else if (["Calculado", "Ajustado", "Em Análise", "Com Inconsistências"].includes(status)) {
			this.btn_approve.show().prop("disabled", false).removeClass("disabled");
			this.btn_execute.show().prop("disabled", true).addClass("disabled").text(__("Efetivar Programação"));
		} else {
			this.btn_approve.hide();
			this.btn_execute.hide();
		}
	}

	load_gantt() {
		const me = this;
		frappe.call({
			method: "erpz_aps.api.get_gantt_data",
			args: { ticket_name: this.current_ticket },
			callback: function(r) {
				if (r.message) {
					me.gantt_data = r.message;
					me.render_interactive_gantt();
				}
			}
		});
	}

	render_interactive_gantt() {
		const me = this;
		const container = $("#aps-gantt-container").empty();
		const data = this.gantt_data;

		if (!data || !data.tasks || data.tasks.length === 0) {
			container.html(`<div class="text-center text-muted p-5">Nenhuma operação programada neste Ticket. Clique em <b>Calcular APS</b> para gerar o cronograma.</div>`);
			return;
		}

		// Calculate date range
		const startDates = data.tasks.map(t => new Date(t.start_date).getTime());
		const endDates = data.tasks.map(t => new Date(t.end_date).getTime());
		const minTime = Math.min(...startDates);
		const maxTime = Math.max(...endDates);

		const startDate = new Date(minTime);
		startDate.setHours(0, 0, 0, 0);
		const endDate = new Date(maxTime);
		endDate.setHours(23, 59, 59, 999);

		me.min_date = startDate;
		me.max_date = endDate;

		const totalDays = Math.max(7, Math.ceil((endDate - startDate) / (1000 * 60 * 60 * 24)));
		const totalWidth = totalDays * me.day_width;

		// 1. Build Legend
		$(`
			<div class="aps-gantt-legend">
				<span class="aps-legend-item"><span class="aps-legend-color" style="background: #2490ef;"></span> Programada</span>
				<span class="aps-legend-item"><span class="aps-legend-color" style="background: #ed8936;"></span> Ajustada (Gantt)</span>
				<span class="aps-legend-item"><span class="aps-legend-color" style="background: #ecc94b;"></span> Em Execução / Apontada</span>
				<span class="aps-legend-item"><span class="aps-legend-color" style="background: #38a169;"></span> Concluída / Apontada Total</span>
				<span class="aps-legend-item"><span class="aps-legend-color" style="background: #e53e3e;"></span> Em Atraso / Conflito</span>
				<span class="aps-legend-item"><span class="aps-legend-color" style="background: repeating-linear-gradient(45deg, #cbd5e0, #cbd5e0 3px, #edf2f7 3px, #edf2f7 6px);"></span> Indisponível (Fim de Semana / Bloqueio)</span>
			</div>
		`).appendTo(container);

		// 2. Build Header
		let headerDaysHtml = "";
		for (let i = 0; i < totalDays; i++) {
			const d = new Date(startDate.getTime() + i * 24 * 60 * 60 * 1000);
			const dayStr = d.toLocaleDateString("pt-BR", { weekday: "short", day: "2-digit", month: "2-digit" });
			headerDaysHtml += `<div class="aps-gantt-day-col" style="width: ${me.day_width}px;">${dayStr}</div>`;
		}

		const ganttHeader = $(`
			<div class="aps-gantt-header">
				<div class="aps-gantt-resource-col">Posto de Trabalho</div>
				<div class="aps-gantt-timeline-head" style="width: ${totalWidth}px;">
					${headerDaysHtml}
				</div>
			</div>
		`).appendTo(container);

		// Group tasks by workstation
		const tasksByWs = {};
		data.workstations.forEach(ws => {
			tasksByWs[ws.name] = [];
		});
		data.tasks.forEach(t => {
			if (!tasksByWs[t.workstation]) {
				tasksByWs[t.workstation] = [];
			}
			tasksByWs[t.workstation].push(t);
		});

		// 3. Build Workstation Rows
		Object.keys(tasksByWs).forEach(wsName => {
			const wsTasks = tasksByWs[wsName];
			const wsLabel = data.workstations.find(w => w.name === wsName)?.workstation_name || wsName;

			const row = $(`
				<div class="aps-gantt-row" data-workstation="${wsName}">
					<div class="aps-gantt-resource-label">
						<span>${wsLabel}</span>
						<small class="text-muted">${wsTasks.length} operações</small>
					</div>
					<div class="aps-gantt-timeline-cells" style="width: ${totalWidth}px;"></div>
				</div>
			`).appendTo(container);

			const cellContainer = row.find(".aps-gantt-timeline-cells");

			// Render Blocked Periods & Weekends
			const wsBlocked = (data.blocked_periods || []).filter(b => b.workstation === wsName);
			wsBlocked.forEach(blk => {
				const bStart = new Date(blk.from_datetime).getTime();
				const bEnd = new Date(blk.to_datetime).getTime();
				if (bEnd > startDate.getTime() && bStart < endDate.getTime()) {
					const offsetDays = Math.max(0, (bStart - startDate.getTime()) / (1000 * 60 * 60 * 24));
					const leftPx = offsetDays * me.day_width;
					const durationDays = (Math.min(endDate.getTime(), bEnd) - Math.max(startDate.getTime(), bStart)) / (1000 * 60 * 60 * 24);
					const widthPx = Math.max(30, durationDays * me.day_width);
					const isMaint = blk.type === "block";

					$(`
						<div class="aps-gantt-blocked-interval ${isMaint ? 'maintenance' : ''}" style="left: ${leftPx}px; width: ${widthPx}px;" title="${blk.title}&#10;${blk.from_datetime} até ${blk.to_datetime}">
							<span style="padding: 2px 4px; text-overflow: ellipsis; overflow: hidden; white-space: nowrap;">${blk.title}</span>
						</div>
					`).appendTo(cellContainer);
				}
			});

			// Position task bars
			wsTasks.forEach(task => {
				const tStart = new Date(task.start_date).getTime();
				const tEnd = new Date(task.end_date).getTime();

				const offsetDays = (tStart - startDate.getTime()) / (1000 * 60 * 60 * 24);
				const leftPx = offsetDays * me.day_width;
				const durationDays = Math.max(0.05, (tEnd - tStart) / (1000 * 60 * 60 * 24));
				const widthPx = Math.max(90, durationDays * me.day_width);

				const statusClass = task.color_status || (task.has_conflict ? "delayed" : (task.is_adjusted ? "adjusted" : "scheduled"));

				const taskBar = $(`
					<div class="aps-task-bar ${statusClass}" data-op-id="${task.id}" data-wo="${task.work_order}" data-seq="${task.sequence_id}" style="left: ${leftPx}px; width: ${widthPx}px;" title="OP: ${task.work_order} - ${task.operation}&#10;Situação: ${task.status_label || task.status}&#10;Início: ${task.start_date}&#10;Término: ${task.end_date}&#10;Qtd: ${task.qty}">
						<div class="aps-task-content">
							<span class="aps-task-badge">${task.sequence_id}</span>
							<b>${task.operation}</b>
							<small>(${task.work_order})</small>
						</div>
						<i class="octicon octicon-grabber ml-1"></i>
					</div>
				`).appendTo(cellContainer);

				// Drag and Drop implementation
				me.setup_drag_and_drop(taskBar, task, cellContainer, startDate);
			});
		});
	}

	setup_drag_and_drop(taskBar, task, container, baseDate) {
		const me = this;
		let isDragging = false;
		let startX = 0;
		let origLeft = 0;

		taskBar.on("mousedown", function(e) {
			isDragging = true;
			startX = e.clientX;
			origLeft = parseFloat(taskBar.css("left")) || 0;
			taskBar.addClass("dragging");

			$(document).on("mousemove.apsdrag", function(e) {
				if (!isDragging) return;
				const dx = e.clientX - startX;
				taskBar.css("left", `${origLeft + dx}px`);
			});

			$(document).on("mouseup.apsdrag", function(e) {
				if (!isDragging) return;
				isDragging = false;
				taskBar.removeClass("dragging");
				$(document).off(".apsdrag");

				const finalLeft = parseFloat(taskBar.css("left")) || 0;
				const dayOffset = finalLeft / me.day_width;
				const newStartTime = new Date(baseDate.getTime() + dayOffset * 24 * 60 * 60 * 1000);

				// Format YYYY-MM-DD HH:MM:SS
				const pad = n => n < 10 ? '0' + n : n;
				const formattedDt = `${newStartTime.getFullYear()}-${pad(newStartTime.getMonth() + 1)}-${pad(newStartTime.getDate())} ${pad(newStartTime.getHours())}:${pad(newStartTime.getMinutes())}:00`;

				// Call backend chain propagation!
				frappe.show_alert({ message: __("Propagando recálculo da cadeia dependente..."), indicator: "blue" });

				frappe.call({
					method: "erpz_aps.api.recalculate_chain",
					args: {
						ticket_name: me.current_ticket,
						op_name: task.id,
						new_start_datetime: formattedDt
					},
					freeze: true,
					freeze_message: __("Recalculando precedências e sucessores..."),
					callback: function(r) {
						if (r.message && r.message.status === "success") {
							frappe.show_alert({
								message: __("Cadeia recalculada: {0} operações sucessoras sincronizadas.", [r.message.impacted_count]),
								indicator: "green"
							});
							me.reload_all();
						}
					}
				});
			});
		});
	}

	load_crp_chart() {
		const me = this;
		frappe.call({
			method: "erpz_aps.api.get_crp_data",
			args: { ticket_name: this.current_ticket },
			callback: function(r) {
				if (r.message && r.message.dates) {
					const data = r.message;
					const chartData = {
						labels: data.dates.map(d => frappe.datetime.str_to_user(d)),
						datasets: [
							{ name: "Capacidade Disponível (h)", values: data.capacity_series, chartType: "line" },
							{ name: "Carga Programada (h)", values: data.load_series, chartType: "bar" }
						]
					};

					if (me.chart) {
						me.chart.destroy();
					}
					me.chart = new frappe.Chart("#aps-crp-chart", {
						title: __("Carga Programada x Capacidade Disponível (CRP)"),
						data: chartData,
						type: "axis-mixed",
						height: 280,
						colors: ["#2490ef", "#ed8936"]
					});

					// Table
					const tbody = $("#aps-crp-tbody").empty();
					data.raw_rows.forEach(rw => {
						const badge = rw.is_bottleneck ?
							`<span class="badge badge-danger">Gargalo / Sobrecarga</span>` :
							`<span class="badge badge-success">Normal</span>`;

						tbody.append(`
							<tr>
								<td><strong>${rw.workstation_name || rw.workstation}</strong></td>
								<td>${frappe.datetime.str_to_user(rw.period_date)}</td>
								<td>${rw.available_capacity_hours}h</td>
								<td>${rw.planned_load_hours}h</td>
								<td class="${rw.capacity_balance_hours < 0 ? 'text-danger font-weight-bold' : ''}">${rw.capacity_balance_hours}h</td>
								<td><b>${rw.utilization_pct}%</b></td>
								<td>${rw.overload_hours > 0 ? rw.overload_hours + 'h' : '-'}</td>
								<td>${badge}</td>
							</tr>
						`);
					});
				}
			}
		});
	}

	load_operations_grid() {
		const me = this;
		frappe.call({
			method: "erpz_aps.api.get_scheduled_operations_summary",
			args: { ticket_name: this.current_ticket, page_length: 200 },
			callback: function(r) {
				const tbody = $("#aps-ops-tbody").empty();
				if (r.message && r.message.items) {
					r.message.items.forEach((o, index) => {
						const isAdjustedBadge = o.is_adjusted ? `<span class="badge badge-warning ml-1">Ajustado</span>` : "";
						const statusBadge = o.status === "Atrasada" ? "badge-danger" : (o.status === "Concluída" ? "badge-success" : "badge-info");

						tbody.append(`
							<tr>
								<td class="font-weight-bold text-muted text-center">${index + 1}</td>
								<td><b>${frappe.datetime.str_to_user(o.planned_start_time)}</b></td>
								<td><b>${frappe.datetime.str_to_user(o.planned_end_time)}</b></td>
								<td><span class="badge badge-light">${o.workstation}</span></td>
								<td>
									<a href="#" class="btn-open-wo font-weight-bold text-primary" data-wo="${o.work_order}">
										<i class="octicon octicon-link-external mr-1"></i>${o.work_order}
									</a>
								</td>
								<td><strong>${o.production_item}</strong><br><small class="text-muted">${o.item_name || ''}</small></td>
								<td><span class="badge badge-secondary mr-1">${o.sequence_id}</span> <b>${o.operation}</b></td>
								<td>${o.duration_mins} min</td>
								<td>${o.predecessor_operation || '-'}</td>
								<td><span class="badge ${statusBadge}">${o.status}</span>${isAdjustedBadge}</td>
								<td>
									<button class="btn btn-xs btn-default btn-open-wo" data-wo="${o.work_order}" title="Abrir Ordem de Produção">
										<i class="octicon octicon-eye"></i> Abrir OP
									</button>
								</td>
							</tr>
						`);
					});

					tbody.off("click", ".btn-open-wo").on("click", ".btn-open-wo", function(e) {
						e.preventDefault();
						const wo = $(this).data("wo");
						if (wo) frappe.set_route("Form", "Work Order", wo);
					});
				}
			}
		});
	}

	export_gantt_excel() {
		const me = this;
		if (!this.current_ticket) return;
		window.open(`/api/method/erpz_aps.api.export_aps_gantt_excel?ticket_name=${me.current_ticket}`);
	}

	load_adjustment_history() {
		frappe.db.get_list("APS Adjustment History", {
			filters: { aps_ticket: this.current_ticket },
			fields: ["moved_at", "moved_by", "work_order", "operation", "previous_start", "new_start", "new_workstation", "impacted_operations_count", "details"],
			order_by: "moved_at DESC"
		}).then(records => {
			const tbody = $("#aps-hist-tbody").empty();
			if (records && records.length > 0) {
				records.forEach(h => {
					tbody.append(`
						<tr>
							<td>${frappe.datetime.str_to_user(h.moved_at)}</td>
							<td>${h.moved_by}</td>
							<td><strong>${h.work_order}</strong></td>
							<td>${h.operation}</td>
							<td>${frappe.datetime.str_to_user(h.previous_start)}</td>
							<td><b class="text-primary">${frappe.datetime.str_to_user(h.new_start)}</b></td>
							<td>${h.new_workstation}</td>
							<td><span class="badge badge-info">${h.impacted_operations_count} ops</span></td>
							<td><small class="text-muted">${h.details || ''}</small></td>
						</tr>
					`);
				});
			} else {
				tbody.append(`<tr><td colspan="9" class="text-center text-muted p-4">Nenhum ajuste manual realizado via Gantt neste Ticket.</td></tr>`);
			}
		});
	}

	run_calculation() {
		const me = this;
		if (!this.current_ticket) return;

		frappe.confirm(__("Deseja iniciar o motor de cálculo e sequenciamento finito APS?"), function() {
			frappe.call({
				method: "erpz_aps.api.run_aps_calculation",
				args: { ticket_name: me.current_ticket },
				freeze: true,
				freeze_message: __("Sequenciando operações e calculando capacidade finita..."),
				callback: function(r) {
					frappe.show_alert({ message: __("Sequenciamento APS concluído com sucesso!"), indicator: "green" });
					me.reload_all();
				}
			});
		});
	}

	approve_scenario() {
		const me = this;
		if (!this.current_ticket) return;

		frappe.call({
			method: "erpz_aps.api.approve_ticket",
			args: { ticket_name: me.current_ticket },
			callback: function(r) {
				frappe.show_alert({ message: __("Cenário APS Aprovado! Pronto para efetivação."), indicator: "green" });
				me.reload_all();
			}
		});
	}

	execute_scenario() {
		const me = this;
		if (!this.current_ticket) return;

		frappe.confirm(__("Deseja sincronizar as datas e horários sequenciados nas Ordens de Produção e Job Cards do ERPNext?"), function() {
			frappe.call({
				method: "erpz_aps.api.execute_ticket",
				args: { ticket_name: me.current_ticket },
				freeze: true,
				freeze_message: __("Atualizando Work Orders e Job Cards no ERPNext..."),
				callback: function(r) {
					if (r.message && r.message.status === "already_executed") {
						frappe.msgprint({
							title: __("Ticket Já Efetivado"),
							indicator: "blue",
							message: __("Todos os horários deste Ticket já foram sincronizados nas Ordens de Produção.")
						});
					} else {
						frappe.msgprint({
							title: __("Efetivação Concluída"),
							indicator: "green",
							message: __("Programação efetivada: {0} Work Orders e {1} Job Cards atualizados.", [r.message.updated_work_orders, r.message.updated_job_cards])
						});
					}
					me.reload_all();
				}
			});
		});
	}

	show_import_routing_dialog() {
		const me = this;
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
							Informe a estação titular, a quantidade de referência (ex: 5 peças), o tempo (ex: 15 min), a sobreposição em % e a estação alternativa do produto.
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
							me.reload_all();
						}
					}
				});
			}
		});
		d.show();
	}
}
