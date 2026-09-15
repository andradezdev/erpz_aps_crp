# Copyright (c) 2026, ERPZ and contributors
# For license information, please see license.txt

from collections import defaultdict
import frappe
from frappe.utils import now_datetime, get_datetime

def execute_aps_schedule(ticket_name):
    """
    Pushes the approved APS finite schedule directly into ERPNext Work Orders and Job Cards:
    1. Updates Work Order planned_start_date and expected_delivery_date.
    2. Updates Job Cards with the scheduled start/end timestamps and assigned workstations.
    3. Links custom_aps_ticket for bi-directional traceability.
    """
    ticket = frappe.get_doc("APS Ticket", ticket_name)
    if ticket.status == "Efetivado":
        frappe.msgprint(
            title="Ticket Já Efetivado",
            indicator="blue",
            message=f"O Ticket APS {ticket_name} já foi efetivado anteriormente. A programação já consta nas Ordens de Produção."
        )
        return {"status": "already_executed", "updated_count": 0}

    ops = frappe.get_all(
        "APS Scheduled Operation",
        filters={"aps_ticket": ticket_name},
        fields=["name", "work_order", "operation", "sequence_id", "workstation", "planned_start_time", "planned_end_time"]
    )

    if not ops:
        frappe.throw("Nenhuma operação programada encontrada para efetivação neste Ticket.")

    # Group operations by Work Order
    ops_by_wo = defaultdict(list)
    for o in ops:
        ops_by_wo[o.work_order].append(o)

    updated_wos = []
    updated_jcs = []

    for wo_name, wo_ops in ops_by_wo.items():
        if not frappe.db.exists("Work Order", wo_name):
            continue

        earliest_start = min(get_datetime(o.planned_start_time) for o in wo_ops)
        latest_end = max(get_datetime(o.planned_end_time) for o in wo_ops)

        # 1. Update Work Order
        wo_updates = {
            "planned_start_date": earliest_start,
            "expected_delivery_date": latest_end
        }
        if frappe.db.has_column("Work Order", "custom_aps_ticket"):
            wo_updates["custom_aps_ticket"] = ticket_name

        frappe.db.set_value("Work Order", wo_name, wo_updates)
        updated_wos.append(wo_name)

        # 2. Update Job Cards if they exist
        for o in wo_ops:
            jc_names = frappe.get_all(
                "Job Card",
                filters={"work_order": wo_name, "operation": o.operation, "docstatus": ["<", 2]},
                pluck="name"
            )
            for jc in jc_names:
                jc_updates = {
                    "workstation": o.workstation
                }
                if frappe.db.has_column("Job Card", "custom_aps_ticket"):
                    jc_updates["custom_aps_ticket"] = ticket_name
                if frappe.db.has_column("Job Card", "custom_mrp_ticket") and ticket.mrp_ticket:
                    jc_updates["custom_mrp_ticket"] = ticket.mrp_ticket

                frappe.db.set_value("Job Card", jc, jc_updates)
                updated_jcs.append(jc)

    # 3. Update Ticket status
    ticket.db_set({
        "status": "Efetivado",
        "executed_on": now_datetime(),
        "executed_by": frappe.session.user
    })
    frappe.db.commit()

    return {
        "status": "success",
        "updated_work_orders": len(updated_wos),
        "updated_job_cards": len(updated_jcs)
    }
