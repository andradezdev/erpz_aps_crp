# Copyright (c) 2026, ERPZ and contributors
# For license information, please see license.txt

import time
from collections import defaultdict
from datetime import datetime, timedelta
import frappe
from frappe.utils import getdate, get_datetime, now_datetime, flt, cint
from erpz_aps.engine.calendar_utils import add_working_minutes, is_workstation_blocked
from erpz_aps.engine.crp_calculator import calculate_crp_capacity_load

class APSEngine:
    def __init__(self, ticket_name):
        self.ticket_name = ticket_name
        self.ticket = frappe.get_doc("APS Ticket", ticket_name)
        self.settings = frappe.get_single("APS Settings")
        
        self.workstations = {} # ws_name -> dict
        self.work_orders = []  # list of Work Orders to schedule
        self.operations = []   # list of operations to schedule
        self.scheduled_ops = [] # result scheduled operations
        self.crp_loads = []
        
        # Tracking workstation busy intervals: ws_name -> list of (start_dt, end_dt)
        self.workstation_timeline = defaultdict(list)

    def run(self):
        start_time = time.time()
        self.ticket.db_set("status", "Processando")
        frappe.db.commit()

        try:
            # 1. Clean previous calculation for this ticket
            frappe.db.delete("APS Scheduled Operation", {"aps_ticket": self.ticket_name})
            frappe.db.delete("APS Capacity Load", {"aps_ticket": self.ticket_name})
            frappe.db.delete("APS Adjustment History", {"aps_ticket": self.ticket_name})
            frappe.db.commit()

            # 2. Load Workstations and active resources
            self.load_workstations()

            # 3. Load Work Orders to schedule
            self.load_work_orders()

            # 4. Schedule operations in finite capacity
            self.schedule_operations()

            # 5. Calculate CRP Capacity Load (Carga x Capacidade)
            self.crp_loads = calculate_crp_capacity_load(
                ticket_name=self.ticket_name,
                scheduled_operations=self.scheduled_ops,
                from_datetime=self.ticket.horizon_start,
                to_datetime=self.ticket.horizon_end,
                threshold_pct=flt(self.settings.overload_threshold_pct or 100.0)
            )

            # 6. Persist to database
            self.persist_all()

            # 7. Update ticket metrics and status
            exec_time = round(time.time() - start_time, 2)
            total_ops = len(self.scheduled_ops)
            total_wo = len(set(o["work_order"] for o in self.scheduled_ops))
            total_hrs = sum(flt(o["duration_mins"]) for o in self.scheduled_ops) / 60.0
            
            # Bottlenecks count
            bottlenecks = sum(1 for c in self.crp_loads if c.get("is_bottleneck"))
            delayed_orders = sum(1 for o in self.scheduled_ops if o.get("delay_hours", 0) > 0)
            
            avg_util = 0.0
            if self.crp_loads:
                avg_util = sum(c["utilization_pct"] for c in self.crp_loads) / len(self.crp_loads)

            self.ticket.db_set({
                "status": "Calculado",
                "total_orders": total_wo,
                "total_operations": total_ops,
                "total_scheduled_hours": round(total_hrs, 2),
                "average_utilization_pct": round(avg_util, 1),
                "total_bottlenecks": bottlenecks,
                "delayed_orders_count": delayed_orders,
                "execution_time_seconds": exec_time,
                "calculated_on": now_datetime(),
                "calculated_by": frappe.session.user
            })
            frappe.db.commit()

            return {
                "status": "Calculado",
                "total_orders": total_wo,
                "total_operations": total_ops,
                "execution_time": exec_time
            }

        except Exception as e:
            frappe.db.rollback()
            self.ticket.db_set("status", "Com Inconsistências")
            frappe.db.commit()
            raise e

    def load_workstations(self):
        ws_list = frappe.get_all("Workstation", fields=["name", "workstation_name", "hour_rate"])
        for ws in ws_list:
            res = frappe.db.get_value("APS Resource", ws.name, ["efficiency_factor", "capacity_hours_per_day"], as_dict=True)
            self.workstations[ws.name] = {
                "workstation": ws.name,
                "name": ws.workstation_name or ws.name,
                "efficiency": (flt(res.efficiency_factor) / 100.0) if res and res.efficiency_factor else 1.0,
                "daily_hours": flt(res.capacity_hours_per_day) if res and res.capacity_hours_per_day else 8.0
            }

    def load_work_orders(self):
        conditions = ["docstatus < 2", "status NOT IN ('Completed', 'Stopped', 'Cancelled')"]
        values = []

        if self.ticket.company:
            conditions.append("company = %s")
            values.append(self.ticket.company)

        # Traceability with MRP Ticket!
        if self.ticket.mrp_ticket:
            conditions.append("custom_mrp_ticket = %s")
            values.append(self.ticket.mrp_ticket)

        if self.ticket.work_order_filter:
            conditions.append("name = %s")
            values.append(self.ticket.work_order_filter)

        if self.ticket.item_filter:
            conditions.append("production_item = %s")
            values.append(self.ticket.item_filter)

        sql = f"""
            SELECT name, production_item, qty, produced_qty,
                   planned_start_date, expected_delivery_date, bom_no, company,
                   custom_mrp_ticket
            FROM `tabWork Order`
            WHERE {" AND ".join(conditions)}
            ORDER BY expected_delivery_date ASC, planned_start_date ASC
        """
        if values:
            self.work_orders = frappe.db.sql(sql, tuple(values), as_dict=True)
        else:
            self.work_orders = frappe.db.sql(sql, as_dict=True)

    def schedule_operations(self):
        horizon_start = get_datetime(self.ticket.horizon_start or now_datetime())
        horizon_end = get_datetime(self.ticket.horizon_end or (horizon_start + timedelta(days=30)))

        # Pre-load custom APS Operations
        aps_op_records = frappe.get_all(
            "APS Operation",
            filters={"is_active": 1},
            fields=["name", "operation_code", "operation_name", "sequence_id", "item_code", "workstation", "batch_qty", "cycle_time_mins", "setup_time_mins", "transfer_time_mins", "overlap_pct", "allow_wo_overlap_pct"]
        )

        for wo in self.work_orders:
            wo_name = wo.name
            qty = flt(wo.qty) - flt(wo.produced_qty)
            if qty <= 0:
                continue

            # Load operations from Work Order or BOM
            ops = frappe.get_all(
                "Work Order Operation",
                filters={"parent": wo_name},
                fields=["operation", "workstation", "time_in_mins", "sequence_id", "idx"],
                order_by="sequence_id ASC, idx ASC"
            )

            if not ops and wo.bom_no:
                ops = frappe.get_all(
                    "BOM Operation",
                    filters={"parent": wo.bom_no},
                    fields=["operation", "workstation", "time_in_mins", "idx"],
                    order_by="idx ASC"
                )
                for i, o in enumerate(ops):
                    o["sequence_id"] = (i + 1) * 10

            if not ops:
                # If no operations defined, check if custom APS Operation matches the item
                custom_item_ops = [ao for ao in aps_op_records if ao.item_code == wo.production_item]
                if custom_item_ops:
                    ops = [{
                        "operation": ao.operation_name or ao.operation_code,
                        "workstation": ao.workstation,
                        "time_in_mins": (ao.cycle_time_mins / max(1.0, ao.batch_qty)),
                        "sequence_id": ao.sequence_id or 10
                    } for ao in custom_item_ops]
                else:
                    default_ws = list(self.workstations.keys())[0] if self.workstations else "Posto Geral"
                    ops = [{
                        "operation": "Produção Geral",
                        "workstation": default_ws,
                        "time_in_mins": 60.0,
                        "sequence_id": 10
                    }]

            # Order precedence cursor
            wo_cursor = max(horizon_start, get_datetime(wo.planned_start_date or horizon_start))
            prev_op_name = None
            prev_op_start = None
            prev_op_end = None
            prev_op_overlap_pct = 0.0

            for op in ops:
                ws_name = op.get("workstation")
                if not ws_name or ws_name not in self.workstations:
                    ws_name = list(self.workstations.keys())[0] if self.workstations else "Posto 01"

                # Check custom APS Operation for reference metrics and overlap %
                matched_aps_op = None
                for ao in aps_op_records:
                    if ao.item_code == wo.production_item and (ao.sequence_id == op.get("sequence_id") or ao.operation_name == op.get("operation") or ao.operation_code == op.get("operation")):
                        matched_aps_op = ao
                        break
                if not matched_aps_op:
                    for ao in aps_op_records:
                        if not ao.item_code and (ao.operation_name == op.get("operation") or ao.operation_code == op.get("operation") or ao.sequence_id == op.get("sequence_id")):
                            matched_aps_op = ao
                            break

                if matched_aps_op:
                    ws_name = matched_aps_op.workstation or ws_name
                    setup_mins = flt(matched_aps_op.setup_time_mins or 0.0)
                    batch_ref = flt(matched_aps_op.batch_qty or 1.0)
                    cycle_ref = flt(matched_aps_op.cycle_time_mins or 10.0)
                    unit_time_mins = cycle_ref / max(0.001, batch_ref)
                    total_run_mins = qty * unit_time_mins
                    overlap_pct = flt(matched_aps_op.overlap_pct or 0.0)
                    transfer_buffer = flt(matched_aps_op.transfer_time_mins or 15.0)
                else:
                    setup_mins = 15.0 if self.settings.consider_setup_time else 0.0
                    run_per_unit = flt(op.get("time_in_mins") or 10.0)
                    total_run_mins = qty * run_per_unit
                    overlap_pct = 0.0
                    transfer_buffer = 15.0 if self.settings.consider_transfer_time and prev_op_end else 0.0

                efficiency = self.workstations.get(ws_name, {}).get("efficiency", 1.0)
                total_duration_mins = setup_mins + (total_run_mins / max(0.1, efficiency))

                # Earliest start respecting Precedence & Overlap
                if prev_op_end and prev_op_start:
                    if prev_op_overlap_pct > 0:
                        overlap_fraction = 1.0 - (prev_op_overlap_pct / 100.0)
                        predecessor_ready = prev_op_start + ((prev_op_end - prev_op_start) * overlap_fraction)
                        earliest_start = add_working_minutes(predecessor_ready, transfer_buffer, ws_name, wo.company)
                    else:
                        earliest_start = add_working_minutes(prev_op_end, transfer_buffer, ws_name, wo.company)
                else:
                    earliest_start = wo_cursor

                # Finite Capacity: Find slot on workstation
                actual_start, actual_end = self.find_finite_slot(ws_name, earliest_start, total_duration_mins)

                # Record scheduled operation
                delay_hours = 0.0
                if wo.expected_delivery_date:
                    due_dt = get_datetime(wo.expected_delivery_date)
                    if actual_end > due_dt:
                        delay_hours = round((actual_end - due_dt).total_seconds() / 3600.0, 1)

                status = "Atrasada" if delay_hours > 0 else "Programada"
                item_name = frappe.db.get_value("Item", wo.production_item, "item_name") or wo.production_item

                sched_op = {
                    "doctype": "APS Scheduled Operation",
                    "name": frappe.generate_hash(length=12),
                    "aps_ticket": self.ticket_name,
                    "work_order": wo_name,
                    "mrp_ticket": wo.get("custom_mrp_ticket"),
                    "production_item": wo.production_item,
                    "item_name": item_name,
                    "operation": op.get("operation"),
                    "sequence_id": cint(op.get("sequence_id") or 10),
                    "workstation": ws_name,
                    "is_alternative_used": 0,
                    "original_workstation": ws_name,
                    "planned_start_time": actual_start,
                    "planned_end_time": actual_end,
                    "duration_mins": round(total_duration_mins, 1),
                    "setup_mins": setup_mins,
                    "runtime_mins": round(total_duration_mins - setup_mins, 1),
                    "qty_to_produce": qty,
                    "predecessor_operation": prev_op_name,
                    "predecessor_end_time": prev_op_end,
                    "is_fixed": 0,
                    "is_adjusted": 0,
                    "has_conflict": 0,
                    "status": status,
                    "delay_hours": delay_hours
                }

                self.scheduled_ops.append(sched_op)

                # Reserve slot on workstation timeline
                self.workstation_timeline[ws_name].append((actual_start, actual_end))

                # Update cursor for next sequential operation
                prev_op_name = f"{op.get('operation')} (Seq {op.get('sequence_id')})"
                prev_op_start = actual_start
                prev_op_end = actual_end
                prev_op_overlap_pct = overlap_pct

    def find_finite_slot(self, workstation, earliest_start, duration_mins):
        """
        Finds the earliest available time window on workstation >= earliest_start
        where no other operation is scheduled.
        """
        cursor = earliest_start
        timeline = sorted(self.workstation_timeline[workstation], key=lambda x: x[0])

        while True:
            candidate_end = add_working_minutes(cursor, duration_mins, workstation)
            overlap = False

            for (occ_start, occ_end) in timeline:
                # Check collision: [cursor, candidate_end] overlaps with [occ_start, occ_end]
                if not (candidate_end <= occ_start or cursor >= occ_end):
                    overlap = True
                    cursor = occ_end # Slide cursor to end of occupied slot
                    break

            if not overlap:
                return cursor, candidate_end

    def persist_all(self):
        # 1. Scheduled Operations
        if self.scheduled_ops:
            cols = [
                "name", "aps_ticket", "work_order", "mrp_ticket", "production_item", "item_name",
                "operation", "sequence_id", "workstation", "is_alternative_used", "original_workstation",
                "planned_start_time", "planned_end_time", "duration_mins", "setup_mins", "runtime_mins",
                "qty_to_produce", "predecessor_operation", "predecessor_end_time", "is_fixed",
                "is_adjusted", "has_conflict", "status", "delay_hours"
            ]
            rows = []
            for op in self.scheduled_ops:
                rows.append([
                    op["name"], op["aps_ticket"], op["work_order"], op.get("mrp_ticket"),
                    op.get("production_item"), op.get("item_name"), op["operation"], op["sequence_id"],
                    op["workstation"], op.get("is_alternative_used", 0), op.get("original_workstation"),
                    op["planned_start_time"], op["planned_end_time"], op["duration_mins"], op["setup_mins"],
                    op["runtime_mins"], op["qty_to_produce"], op.get("predecessor_operation"),
                    op.get("predecessor_end_time"), op.get("is_fixed", 0), op.get("is_adjusted", 0),
                    op.get("has_conflict", 0), op.get("status", "Programada"), op.get("delay_hours", 0.0)
                ])
            frappe.db.bulk_insert("APS Scheduled Operation", cols, rows)

        # 2. Capacity Loads
        if self.crp_loads:
            c_cols = [
                "name", "aps_ticket", "workstation", "workstation_name", "company", "period_date",
                "available_capacity_hours", "planned_load_hours", "capacity_balance_hours",
                "utilization_pct", "is_bottleneck", "overload_hours", "idle_hours", "operations_count"
            ]
            c_rows = []
            for c in self.crp_loads:
                c_rows.append([
                    frappe.generate_hash(length=12), c["aps_ticket"], c["workstation"],
                    c.get("workstation_name"), c.get("company"), c["period_date"],
                    c["available_capacity_hours"], c["planned_load_hours"], c["capacity_balance_hours"],
                    c["utilization_pct"], c["is_bottleneck"], c["overload_hours"], c["idle_hours"],
                    c["operations_count"]
                ])
            frappe.db.bulk_insert("APS Capacity Load", c_cols, c_rows)
