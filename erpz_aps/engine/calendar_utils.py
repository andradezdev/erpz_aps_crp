# Copyright (c) 2026, ERPZ and contributors
# For license information, please see license.txt

from datetime import datetime, date, time, timedelta
import frappe
from frappe.utils import getdate, get_datetime

def get_workstation_working_intervals(workstation):
    """
    Returns list of (start_time, end_time) working windows for a workstation.
    Reads from tabWorkstation Working Hour if configured, else default: 08:00-12:00 and 13:00-17:00.
    """
    rows = frappe.db.sql("""
        SELECT start_time, end_time, enabled FROM `tabWorkstation Working Hour`
        WHERE parent = %s AND (enabled = 1 OR enabled IS NULL)
        ORDER BY idx ASC
    """, (workstation,), as_dict=True)

    if rows:
        windows = []
        for r in rows:
            st = (datetime.min + r.start_time).time() if isinstance(r.start_time, timedelta) else r.start_time
            et = (datetime.min + r.end_time).time() if isinstance(r.end_time, timedelta) else r.end_time
            if st and et:
                windows.append((st, et))
        if windows:
            return sorted(windows, key=lambda x: x[0])

    return [(time(8, 0), time(12, 0)), (time(13, 0), time(17, 0))]

def get_workstation_holidays(workstation, company=None):
    """
    Returns a set of dates considered holidays for the workstation.
    """
    holiday_list = frappe.db.get_value("Workstation", workstation, "holiday_list")
    if not holiday_list and company:
        holiday_list = frappe.db.get_value("Company", company, "default_holiday_list")
    if not holiday_list:
        return set()

    holidays = frappe.db.sql_list("""
        SELECT holiday_date FROM `tabHoliday` WHERE parent = %s
    """, (holiday_list,))
    return set(getdate(h) for h in holidays)

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

def add_working_minutes(start_dt, minutes_to_add, workstation=None, company=None):
    """
    Advances start_dt by minutes_to_add, strictly respecting:
    1. Workstation specific working hours (from tabWorkstation Working Hour).
    2. Workstation holidays (from Workstation.holiday_list).
    3. Weekends (Saturday, Sunday).
    """
    current = get_datetime(start_dt)
    remaining_mins = max(1.0, float(minutes_to_add))
    
    windows = get_workstation_working_intervals(workstation)
    holidays = get_workstation_holidays(workstation, company) if workstation else set()

    first_window_start = windows[0][0]
    last_window_end = windows[-1][1]

    while remaining_mins > 0:
        # Skip weekend and holidays
        while current.weekday() in (5, 6) or current.date() in holidays:
            current = datetime.combine(current.date() + timedelta(days=1), first_window_start)

        cur_time = current.time()

        # Before first window of the day
        if cur_time < first_window_start:
            current = datetime.combine(current.date(), first_window_start)
            cur_time = first_window_start

        # After last window of the day -> advance to next day
        if cur_time >= last_window_end:
            current = datetime.combine(current.date() + timedelta(days=1), first_window_start)
            continue

        # Find which working window we are in or advance to the next window
        found_window = False
        for (w_start, w_end) in windows:
            if w_start <= cur_time < w_end:
                # We are inside this working window!
                window_end_dt = datetime.combine(current.date(), w_end)
                available_mins = (window_end_dt - current).total_seconds() / 60.0

                if remaining_mins <= available_mins:
                    current += timedelta(minutes=remaining_mins)
                    remaining_mins = 0
                else:
                    remaining_mins -= available_mins
                    current = window_end_dt
                found_window = True
                break
            elif cur_time < w_start:
                # We are in a break between windows (e.g. lunch) -> jump to window start
                current = datetime.combine(current.date(), w_start)
                found_window = True
                break

        if not found_window:
            current = datetime.combine(current.date() + timedelta(days=1), first_window_start)

    return current
