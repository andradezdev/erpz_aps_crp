# Copyright (c) 2026, ERPZ and contributors
# For license information, please see license.txt

from datetime import datetime, date, time, timedelta
import frappe
from frappe.utils import getdate, get_datetime

def get_workstation_shifts(workstation):
    """
    Returns daily working intervals (in hours) for a workstation.
    Default standard shift: 08:00 to 12:00 and 13:00 to 17:00 (8h).
    """
    # Check if Workstation has custom shift hours or holiday list
    holiday_list = frappe.db.get_value("Workstation", workstation, "holiday_list")
    return {
        "shift_start": time(8, 0),
        "lunch_start": time(12, 0),
        "lunch_end": time(13, 0),
        "shift_end": time(17, 0),
        "holiday_list": holiday_list
    }

def is_workstation_blocked(workstation, check_datetime, blocks_list=None):
    """
    Checks if a workstation has an active maintenance or breakdown block at check_datetime.
    """
    dt = get_datetime(check_datetime)
    if blocks_list:
        for b in blocks_list:
            if b["workstation"] == workstation and b["from_datetime"] <= dt <= b["to_datetime"]:
                return True
        return False

    return bool(frappe.db.exists(
        "APS Resource Block",
        {
            "workstation": workstation,
            "is_active": 1,
            "from_datetime": ["<=", dt],
            "to_datetime": [">=", dt]
        }
    ))

def add_working_minutes(start_dt, minutes_to_add, workstation=None, holiday_list=None):
    """
    Advances start_dt by minutes_to_add, respecting work shifts (08:00-12:00, 13:00-17:00),
    skipping weekends and lunch pauses.
    """
    current = get_datetime(start_dt)
    remaining_mins = max(1.0, float(minutes_to_add))
    
    # Work day boundary
    shift_start = time(8, 0)
    lunch_start = time(12, 0)
    lunch_end = time(13, 0)
    shift_end = time(17, 0)
    
    # Adjust current to next valid working time
    while remaining_mins > 0:
        # 1. Skip weekend
        while current.weekday() in (5, 6): # Sat, Sun
            current = datetime.combine(current.date() + timedelta(days=1), shift_start)
            
        cur_time = current.time()
        
        # 2. Before shift start
        if cur_time < shift_start:
            current = datetime.combine(current.date(), shift_start)
            cur_time = shift_start
            
        # 3. During lunch
        if lunch_start <= cur_time < lunch_end:
            current = datetime.combine(current.date(), lunch_end)
            cur_time = lunch_end
            
        # 4. After shift end
        if cur_time >= shift_end:
            current = datetime.combine(current.date() + timedelta(days=1), shift_start)
            continue
            
        # Current valid working window
        if cur_time < lunch_start:
            window_end = datetime.combine(current.date(), lunch_start)
        else:
            window_end = datetime.combine(current.date(), shift_end)
            
        available_in_window = (window_end - current).total_seconds() / 60.0
        
        if remaining_mins <= available_in_window:
            current += timedelta(minutes=remaining_mins)
            remaining_mins = 0
        else:
            remaining_mins -= available_in_window
            current = window_end
            
    return current
