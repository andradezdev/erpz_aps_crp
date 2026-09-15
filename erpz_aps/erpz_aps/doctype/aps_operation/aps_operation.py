# Copyright (c) 2026, ERPZ and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import flt

class APSOperation(Document):
    def validate(self):
        # Auto-compute unit production time
        batch = flt(self.batch_qty)
        cycle = flt(self.cycle_time_mins)
        if batch > 0:
            self.time_per_unit_mins = round(cycle / batch, 4)
        else:
            self.time_per_unit_mins = cycle

        # Validation for overlap percentages
        if flt(self.overlap_pct) < 0 or flt(self.overlap_pct) > 100:
            frappe.throw("Sobreposição com a próxima operação deve estar entre 0% e 100%.")

        if flt(self.allow_wo_overlap_pct) < 0 or flt(self.allow_wo_overlap_pct) > 100:
            frappe.throw("Sobreposição com outra OP deve estar entre 0% e 100%.")
