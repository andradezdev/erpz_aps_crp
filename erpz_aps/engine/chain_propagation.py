# Copyright (c) 2026, ERPZ and contributors
# For license information, please see license.txt

from datetime import datetime, timedelta
import frappe
from frappe.utils import get_datetime, now_datetime, flt
from erpz_aps.engine.calendar_utils import add_working_minutes

def propagate_operation_change(ticket_name, op_name, new_start_dt, new_workstation=None):
    """
    Propagates drag-and-drop changes in chain:
    1. Repositions target operation.
    2. Enforces precedence chain on all successor operations of the same Work Order.
    3. Validates predecessors and flags conflicts if any.
    4. Propagates to dependent parent Work Orders.
    5. Resolves workstation overlaps according to finite capacity.
    6. Logs the adjustment in APS Adjustment History.
    """
    new_start = get_datetime(new_start_dt)
    
    # Load all operations of this ticket
    all_ops = frappe.get_all(
        "APS Scheduled Operation",
        filters={"aps_ticket": ticket_name},
        fields=["*"]
    )
    
    op_map = {o.name: o for o in all_ops}
    target = op_map.get(op_name)
    if not target:
        frappe.throw(f"Operação {op_name} não encontrada no Ticket {ticket_name}")
        
    prev_start = target.planned_start_time
    prev_end = target.planned_end_time
    prev_ws = target.workstation
    
    # 1. Update target operation
    if new_workstation and new_workstation != target.workstation:
        target.is_alternative_used = 1
        target.original_workstation = target.original_workstation or target.workstation
        target.workstation = new_workstation
        
    duration = flt(target.duration_mins or 30.0)
    target.planned_start_time = new_start
    target.planned_end_time = add_working_minutes(new_start, duration, target.workstation)
    target.is_adjusted = 1
    target.adjustment_timestamp = now_datetime()
    target.has_conflict = 0
    target.conflict_reason = ""
    
    impacted_count = 0
    
    # 2. Check predecessors of the same Work Order (Sequence < target.sequence_id)
    same_wo_preds = [o for o in all_ops if o.work_order == target.work_order and o.sequence_id < target.sequence_id]
    for pred in same_wo_preds:
        if get_datetime(pred.planned_end_time) > get_datetime(target.planned_start_time):
            target.has_conflict = 1
            target.conflict_reason = f"Conflito de Precedência: Início ({target.planned_start_time}) antes do término da Operação {pred.operation} ({pred.planned_end_time})."
            
    # 3. Propagate forward to all SUCCESSORS of the same Work Order (Sequence > target.sequence_id)
    same_wo_succs = [o for o in all_ops if o.work_order == target.work_order and o.sequence_id > target.sequence_id]
    same_wo_succs.sort(key=lambda x: x.sequence_id)
    
    cursor_end = target.planned_end_time
    transfer_buffer_mins = 15.0 # Transfer interval between operations
    
    for succ in same_wo_succs:
        min_start = add_working_minutes(cursor_end, transfer_buffer_mins, succ.workstation)
        if get_datetime(succ.planned_start_time) < get_datetime(min_start):
            succ.planned_start_time = min_start
            succ.planned_end_time = add_working_minutes(min_start, flt(succ.duration_mins or 30.0), succ.workstation)
            succ.is_adjusted = 1
            succ.adjustment_timestamp = now_datetime()
            succ.has_conflict = 0
            cursor_end = succ.planned_end_time
            impacted_count += 1
        else:
            cursor_end = succ.planned_end_time
            
    # 4. Resolve workstation overlap on the target workstation (Finite Capacity)
    # Operations from other work orders on the same workstation that collide
    same_ws_ops = [
        o for o in all_ops 
        if o.workstation == target.workstation and o.name != target.name and o.work_order != target.work_order
    ]
    same_ws_ops.sort(key=lambda x: x.planned_start_time)
    
    for other in same_ws_ops:
        # Check collision: if other starts during [target.start, target.end]
        if get_datetime(target.planned_start_time) <= get_datetime(other.planned_start_time) < get_datetime(target.planned_end_time):
            # Shift other to start after target
            shift_start = target.planned_end_time
            other.planned_start_time = shift_start
            other.planned_end_time = add_working_minutes(shift_start, flt(other.duration_mins or 30.0), other.workstation)
            other.is_adjusted = 1
            impacted_count += 1
            
            # Propagate other's successors
            other_succs = [o for o in all_ops if o.work_order == other.work_order and o.sequence_id > other.sequence_id]
            other_succs.sort(key=lambda x: x.sequence_id)
            cur_o_end = other.planned_end_time
            for os_op in other_succs:
                m_start = add_working_minutes(cur_o_end, transfer_buffer_mins, os_op.workstation)
                if get_datetime(os_op.planned_start_time) < get_datetime(m_start):
                    os_op.planned_start_time = m_start
                    os_op.planned_end_time = add_working_minutes(m_start, flt(os_op.duration_mins or 30.0), os_op.workstation)
                    os_op.is_adjusted = 1
                    cur_o_end = os_op.planned_end_time
                    impacted_count += 1
                    
    # 5. Persist updated operations
    for op in all_ops:
        if op.get("is_adjusted") or op.name == target.name or op.get("has_conflict"):
            frappe.db.set_value("APS Scheduled Operation", op.name, {
                "workstation": op.workstation,
                "is_alternative_used": op.get("is_alternative_used", 0),
                "planned_start_time": op.planned_start_time,
                "planned_end_time": op.planned_end_time,
                "is_adjusted": op.get("is_adjusted", 0),
                "has_conflict": op.get("has_conflict", 0),
                "conflict_reason": op.get("conflict_reason", "")
            })
            
    # 6. Record in APS Adjustment History
    hist = frappe.new_doc("APS Adjustment History")
    hist.aps_ticket = ticket_name
    hist.operation_schedule = target.name
    hist.work_order = target.work_order
    hist.operation = target.operation
    hist.moved_by = frappe.session.user
    hist.moved_at = now_datetime()
    hist.previous_workstation = prev_ws
    hist.new_workstation = target.workstation
    hist.previous_start = prev_start
    hist.new_start = target.planned_start_time
    hist.previous_end = prev_end
    hist.new_end = target.planned_end_time
    hist.impacted_operations_count = impacted_count
    hist.details = f"Operação deslocada no Gantt para {target.planned_start_time}. {impacted_count} operações subsequentes recalculadas na cadeia."
    hist.insert(ignore_permissions=True)
    
    # 7. Update ticket status to 'Ajustado'
    frappe.db.set_value("APS Ticket", ticket_name, "status", "Ajustado")
    frappe.db.commit()
    
    return {
        "status": "success",
        "target_op": target.name,
        "impacted_count": impacted_count,
        "has_conflict": target.has_conflict,
        "conflict_reason": target.conflict_reason
    }
