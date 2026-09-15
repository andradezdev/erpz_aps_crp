# Copyright (c) 2026, ERPZ and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import now_datetime, getdate, get_datetime, flt, cint
from erpz_aps.engine.aps_engine import APSEngine
from erpz_aps.engine.chain_propagation import propagate_operation_change
from erpz_aps.engine.execution import execute_aps_schedule

@frappe.whitelist()
def run_aps_calculation(ticket_name):
    """Triggers the finite-capacity APS/CRP engine for a given ticket."""
    if not frappe.has_permission("APS Ticket", "write"):
        frappe.throw(_("Sem permissão para executar programação APS."))
        
    engine = APSEngine(ticket_name)
    result = engine.run()
    return result

@frappe.whitelist()
def recalculate_chain(ticket_name, op_name, new_start_datetime, new_workstation=None):
    """
    Called when an operation is dragged and dropped in the interactive Gantt chart.
    Propagates the movement forward across all dependent operations and Work Orders in chain.
    """
    if not frappe.has_permission("APS Ticket", "write"):
        frappe.throw(_("Sem permissão para ajustar programação."))
        
    res = propagate_operation_change(ticket_name, op_name, new_start_datetime, new_workstation)
    return res

@frappe.whitelist()
def approve_ticket(ticket_name):
    """Approves an APS ticket scenario for execution."""
    if not frappe.has_permission("APS Ticket", "write"):
        frappe.throw(_("Sem permissão para aprovar Ticket APS."))
        
    ticket = frappe.get_doc("APS Ticket", ticket_name)
    if ticket.status in ("Efetivado", "Cancelado"):
        frappe.throw(_("Ticket já finalizado não pode ser aprovado."))
        
    ticket.db_set({
        "status": "Aprovado",
        "approved_on": now_datetime(),
        "approved_by": frappe.session.user
    })
    frappe.db.commit()
    return {"status": "success", "message": _("Ticket APS aprovado com sucesso.")}

@frappe.whitelist()
def execute_ticket(ticket_name):
    """Synchronizes scheduled start/end dates directly to Work Orders and Job Cards."""
    if not frappe.has_permission("APS Ticket", "write"):
        frappe.throw(_("Sem permissão para efetivar Ticket APS."))
        
    res = execute_aps_schedule(ticket_name)
    return res

@frappe.whitelist()
def get_gantt_data(ticket_name, group_by="workstation"):
    """
    Returns structured data for the interactive Gantt chart:
    - tasks: list of operation bars
    - links: dependency arrows between predecessor and successor operations
    - resources: workstations
    """
    ops = frappe.get_all(
        "APS Scheduled Operation",
        filters={"aps_ticket": ticket_name},
        fields=[
            "name", "work_order", "mrp_ticket", "production_item", "item_name",
            "operation", "sequence_id", "workstation", "planned_start_time",
            "planned_end_time", "duration_mins", "setup_mins", "runtime_mins",
            "qty_to_produce", "predecessor_operation", "is_fixed", "is_adjusted",
            "has_conflict", "status", "delay_hours"
        ],
        order_by="planned_start_time ASC"
    )

    workstations = frappe.get_all("Workstation", fields=["name", "workstation_name"])
    ws_map = {w.name: w.workstation_name or w.name for w in workstations}

    tasks = []
    links = []

    # Map for building dependency arrows
    wo_ops_map = {}

    for o in ops:
        start_str = str(o.planned_start_time)
        end_str = str(o.planned_end_time)
        
        # Color coding
        progress = 1.0 if o.status == "Concluída" else (0.5 if o.status == "Em Execução" else 0.0)
        
        # Group label
        ws_label = ws_map.get(o.workstation, o.workstation)
        
        task_id = o.name
        task_label = f"[{o.work_order}] {o.operation} ({int(o.duration_mins)}m)"
        
        tasks.append({
            "id": task_id,
            "text": task_label,
            "start_date": start_str,
            "end_date": end_str,
            "duration": o.duration_mins,
            "progress": progress,
            "workstation": o.workstation,
            "workstation_label": ws_label,
            "work_order": o.work_order,
            "production_item": o.production_item,
            "item_name": o.item_name,
            "operation": o.operation,
            "sequence_id": o.sequence_id,
            "qty": o.qty_to_produce,
            "is_adjusted": o.is_adjusted,
            "has_conflict": o.has_conflict,
            "status": o.status,
            "delay_hours": o.delay_hours
        })

        # Track operations by Work Order and sequence
        key = (o.work_order, o.sequence_id)
        wo_ops_map[key] = task_id

    # Build dependency links (predecessor -> successor in the same Work Order)
    for o in ops:
        current_id = o.name
        current_seq = o.sequence_id
        # Find predecessor operation with highest sequence < current_seq in the same WO
        preds = [
            wo_ops_map[(o.work_order, s)] 
            for (w, s) in wo_ops_map.keys() 
            if w == o.work_order and s < current_seq
        ]
        if preds:
            pred_id = preds[-1]
            links.append({
                "id": f"{pred_id}_{current_id}",
                "source": pred_id,
                "target": current_id,
                "type": "0" # finish-to-start
            })

    return {
        "tasks": tasks,
        "links": links,
        "workstations": workstations
    }

@frappe.whitelist()
def get_crp_data(ticket_name, workstation=None):
    """Returns CRP Capacity vs Load data and chart series."""
    filters = {"aps_ticket": ticket_name}
    if workstation:
        filters["workstation"] = workstation

    rows = frappe.get_all(
        "APS Capacity Load",
        filters=filters,
        fields=[
            "workstation", "workstation_name", "period_date",
            "available_capacity_hours", "planned_load_hours",
            "capacity_balance_hours", "utilization_pct", "is_bottleneck",
            "overload_hours", "idle_hours", "operations_count"
        ],
        order_by="period_date ASC, workstation ASC"
    )

    dates = sorted(list(set(str(r.period_date) for r in rows)))
    
    # Aggregated daily capacity vs load
    daily_capacity = {d: 0.0 for d in dates}
    daily_load = {d: 0.0 for d in dates}
    
    for r in rows:
        d_str = str(r.period_date)
        daily_capacity[d_str] += flt(r.available_capacity_hours)
        daily_load[d_str] += flt(r.planned_load_hours)

    return {
        "dates": dates,
        "capacity_series": [round(daily_capacity[d], 1) for d in dates],
        "load_series": [round(daily_load[d], 1) for d in dates],
        "raw_rows": rows
    }

@frappe.whitelist()
def get_ticket_dashboard_metrics(ticket_name):
    """Returns high-level KPI cards data for the APS workbench."""
    ticket = frappe.get_doc("APS Ticket", ticket_name)
    
    total_ops = frappe.db.count("APS Scheduled Operation", {"aps_ticket": ticket_name})
    total_bottlenecks = frappe.db.count("APS Capacity Load", {"aps_ticket": ticket_name, "is_bottleneck": 1})
    delayed_count = frappe.db.count("APS Scheduled Operation", {"aps_ticket": ticket_name, "status": "Atrasada"})
    adjusted_count = frappe.db.count("APS Scheduled Operation", {"aps_ticket": ticket_name, "is_adjusted": 1})
    
    return {
        "status": ticket.status,
        "total_orders": ticket.total_orders or 0,
        "total_operations": total_ops,
        "total_scheduled_hours": ticket.total_scheduled_hours or 0.0,
        "average_utilization_pct": ticket.average_utilization_pct or 0.0,
        "total_bottlenecks": total_bottlenecks,
        "delayed_orders_count": delayed_count,
        "adjusted_operations": adjusted_count,
        "mrp_ticket": ticket.mrp_ticket or "",
        "execution_time": ticket.execution_time_seconds or 0.0
    }

@frappe.whitelist()
def get_scheduled_operations_summary(ticket_name, workstation=None, work_order=None, status=None, start=0, page_length=50):
    """Returns paginated scheduled operations for the detailed grid."""
    filters = {"aps_ticket": ticket_name}
    if workstation:
        filters["workstation"] = workstation
    if work_order:
        filters["work_order"] = ["like", f"%{work_order}%"]
    if status:
        filters["status"] = status

    total_count = frappe.db.count("APS Scheduled Operation", filters=filters)
    items = frappe.get_all(
        "APS Scheduled Operation",
        filters=filters,
        fields=[
            "name", "work_order", "mrp_ticket", "production_item", "item_name",
            "operation", "sequence_id", "workstation", "planned_start_time",
            "planned_end_time", "duration_mins", "setup_mins", "runtime_mins",
            "qty_to_produce", "is_adjusted", "has_conflict", "status", "delay_hours"
        ],
        start=cint(start),
        page_length=cint(page_length),
        order_by="planned_start_time ASC, sequence_id ASC"
    )

    return {
        "total": total_count,
        "items": items
    }
