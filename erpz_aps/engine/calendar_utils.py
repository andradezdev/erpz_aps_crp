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

def is_weekend_work_allowed(workstation):
    """
    Checks if the workstation allows work on weekends.
    """
    if not workstation:
        return False
    return bool(frappe.db.get_value("APS Resource", workstation, "allow_weekend_work"))

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

def get_active_workstation_blocks(workstation):
    """
    Fetches all active maintenance and breakdown blocks for this workstation.
    """
    if not workstation:
        return []

    return frappe.get_all(
        "APS Resource Block",
        filters={"workstation": workstation, "is_active": 1},
        fields=["name", "block_type", "recurrence", "from_datetime", "to_datetime", "is_weekend_block"]
    )

def is_workstation_blocked(workstation, check_datetime):
    """Checks if check_datetime falls inside an active block for workstation."""
    blocks = get_active_workstation_blocks(workstation)
    dt = get_datetime(check_datetime)
    for b in blocks:
        if b.get("from_datetime") and b.get("to_datetime"):
            if get_datetime(b["from_datetime"]) <= dt <= get_datetime(b["to_datetime"]):
                return True
    return False

def get_effective_workstation_start(workstation, desired_start, company=None):
    """
    Snaps desired_start out of non-working hours, lunch breaks, weekends, and active maintenance blocks.
    Guarantees the operation begins at a moment when the machine is genuinely available.
    """
    current = get_datetime(desired_start)
    windows = get_workstation_working_intervals(workstation)
    holidays = get_workstation_holidays(workstation, company) if workstation else set()
    weekend_allowed = is_weekend_work_allowed(workstation) if workstation else False
    blocks = get_active_workstation_blocks(workstation)

    first_window_start = windows[0][0]
    last_window_end = windows[-1][1]

    loop_guard = 0
    while loop_guard < 500:
        loop_guard += 1
        is_weekend = current.weekday() in (5, 6)

        # 1. Skip Weekend & Holidays
        if (is_weekend and not weekend_allowed) or current.date() in holidays:
            current = datetime.combine(current.date() + timedelta(days=1), first_window_start)
            continue

        # 2. Check if inside an active maintenance block
        in_block_end = None
        for b in blocks:
            if b.get("is_weekend_block") and is_weekend:
                in_block_end = datetime.combine(current.date() + timedelta(days=1), first_window_start)
                break
            if b.get("from_datetime") and b.get("to_datetime"):
                b_from = get_datetime(b["from_datetime"])
                b_to = get_datetime(b["to_datetime"])
                if b_from <= current < b_to:
                    in_block_end = b_to
                    break

        if in_block_end:
            current = in_block_end
            continue

        cur_time = current.time()

        # 3. Before first window of the day
        if cur_time < first_window_start:
            current = datetime.combine(current.date(), first_window_start)
            continue

        # 4. After last window of the day
        if cur_time >= last_window_end:
            current = datetime.combine(current.date() + timedelta(days=1), first_window_start)
            continue

        # 5. During break between windows (e.g. lunch)
        in_break = False
        for idx in range(len(windows) - 1):
            if windows[idx][1] <= cur_time < windows[idx + 1][0]:
                current = datetime.combine(current.date(), windows[idx + 1][0])
                in_break = True
                break
        if in_break:
            continue

        break

    return current

def add_working_minutes(start_dt, minutes_to_add, workstation=None, company=None):
    """
    Advances start_dt by minutes_to_add, extending across:
    1. Lunch breaks and non-working hours.
    2. Weekends (unless allow_weekend_work is enabled).
    3. Maintenance, breakdown, and unavailability blocks (pauses during block, resumes after block).
    Never enters infinite loops.
    """
    current = get_effective_workstation_start(workstation, start_dt, company)
    remaining_mins = max(1.0, float(minutes_to_add))
    
    windows = get_workstation_working_intervals(workstation)
    holidays = get_workstation_holidays(workstation, company) if workstation else set()
    weekend_allowed = is_weekend_work_allowed(workstation) if workstation else False
    blocks = get_active_workstation_blocks(workstation)

    first_window_start = windows[0][0]
    last_window_end = windows[-1][1]

    loop_count = 0
    max_loops = 2000

    while remaining_mins > 0:
        loop_count += 1
        if loop_count > max_loops:
            # Safety exit: advance remaining mins as calendar time to prevent system hang
            current += timedelta(minutes=remaining_mins)
            break

        # 1. Skip weekend & holidays
        is_weekend = current.weekday() in (5, 6)
        if (is_weekend and not weekend_allowed) or current.date() in holidays:
            current = datetime.combine(current.date() + timedelta(days=1), first_window_start)
            continue

        # 2. Check if current falls inside an active block
        in_block_end = None
        for b in blocks:
            if b.get("is_weekend_block") and is_weekend:
                in_block_end = datetime.combine(current.date() + timedelta(days=1), first_window_start)
                break
            if b.get("from_datetime") and b.get("to_datetime"):
                b_from = get_datetime(b["from_datetime"])
                b_to = get_datetime(b["to_datetime"])
                if b_from <= current < b_to:
                    in_block_end = b_to
                    break

        if in_block_end:
            current = in_block_end
            continue

        cur_time = current.time()

        # Before shift start
        if cur_time < first_window_start:
            current = datetime.combine(current.date(), first_window_start)
            cur_time = first_window_start

        # After shift end
        if cur_time >= last_window_end:
            current = datetime.combine(current.date() + timedelta(days=1), first_window_start)
            continue

        # Find which working window we are in
        found_window = False
        for (w_start, w_end) in windows:
            if w_start <= cur_time < w_end:
                window_end_dt = datetime.combine(current.date(), w_end)

                # Check if a block starts INSIDE this working window after current
                next_block_start = None
                for b in blocks:
                    if b.get("from_datetime") and b.get("to_datetime"):
                        b_from = get_datetime(b["from_datetime"])
                        if current < b_from < window_end_dt:
                            if next_block_start is None or b_from < next_block_start:
                                next_block_start = b_from

                effective_end_dt = next_block_start if next_block_start else window_end_dt
                available_mins = (effective_end_dt - current).total_seconds() / 60.0

                if available_mins <= 0:
                    current = effective_end_dt
                    found_window = True
                    break

                if remaining_mins <= available_mins:
                    current += timedelta(minutes=remaining_mins)
                    remaining_mins = 0
                else:
                    remaining_mins -= available_mins
                    current = effective_end_dt

                found_window = True
                break
            elif cur_time < w_start:
                current = datetime.combine(current.date(), w_start)
                found_window = True
                break

        if not found_window:
            current = datetime.combine(current.date() + timedelta(days=1), first_window_start)

    return current
