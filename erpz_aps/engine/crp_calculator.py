# Copyright (c) 2026, ERPZ and contributors
# For license information, please see license.txt

from collections import defaultdict
from datetime import datetime, timedelta
import frappe
from frappe.utils import getdate, flt, cint

def calculate_crp_capacity_load(ticket_name, scheduled_operations, from_datetime, to_datetime, threshold_pct=100.0):
    """
    Computes daily load vs capacity per workstation (CRP - Carga x Capacidade):
    - Capacidade Disponível
    - Carga Programada
    - Saldo de Capacidade
    - Percentual de Utilização (%)
    - Identificação de Gargalos / Sobrecarga
    """
    start_d = getdate(from_datetime)
    end_d = getdate(to_datetime)
    num_days = max(1, (end_d - start_d).days + 1)
    
    # 1. Map planned load per (workstation, date)
    load_by_day = defaultdict(float)
    ops_count_by_day = defaultdict(int)
    
    for op in scheduled_operations:
        st = op.get("planned_start_time")
        if not st:
            continue
        op_date = getdate(st)
        duration_hours = flt(op.get("duration_mins", 0.0)) / 60.0
        ws = op.get("workstation")
        load_by_day[(ws, op_date)] += duration_hours
        ops_count_by_day[(ws, op_date)] += 1
        
    # 2. Get active workstations
    workstations = frappe.get_all("Workstation", fields=["name", "workstation_name", "hour_rate"])
    crp_records = []
    
    for ws in workstations:
        ws_name = ws.name
        company = frappe.db.get_value("APS Ticket", ticket_name, "company")
        
        # Check custom APS Resource parameters
        aps_res = frappe.db.get_value("APS Resource", ws_name, ["capacity_hours_per_day", "efficiency_factor"], as_dict=True)
        base_cap = flt(aps_res.capacity_hours_per_day) if aps_res and aps_res.capacity_hours_per_day else 8.0
        eff = (flt(aps_res.efficiency_factor) / 100.0) if aps_res and aps_res.efficiency_factor else 1.0
        effective_capacity = base_cap * eff
        
        for d_offset in range(num_days):
            cur_date = start_d + timedelta(days=d_offset)
            
            # Skip weekend for standard capacity (or 0 capacity on weekend)
            if cur_date.weekday() in (5, 6):
                avail_hours = 0.0
            else:
                avail_hours = effective_capacity
                
            planned_hours = load_by_day.get((ws_name, cur_date), 0.0)
            balance = avail_hours - planned_hours
            
            utilization = (planned_hours / avail_hours * 100.0) if avail_hours > 0 else (100.0 if planned_hours > 0 else 0.0)
            is_bottleneck = 1 if (utilization > threshold_pct or (planned_hours > 0 and avail_hours == 0)) else 0
            overload = max(0.0, planned_hours - avail_hours)
            idle = max(0.0, avail_hours - planned_hours)
            
            crp_records.append({
                "doctype": "APS Capacity Load",
                "aps_ticket": ticket_name,
                "workstation": ws_name,
                "workstation_name": ws.workstation_name or ws_name,
                "company": company,
                "period_date": cur_date,
                "available_capacity_hours": round(avail_hours, 2),
                "planned_load_hours": round(planned_hours, 2),
                "capacity_balance_hours": round(balance, 2),
                "utilization_pct": round(utilization, 1),
                "is_bottleneck": is_bottleneck,
                "overload_hours": round(overload, 2),
                "idle_hours": round(idle, 2),
                "operations_count": ops_count_by_day.get((ws_name, cur_date), 0)
            })
            
    return crp_records
