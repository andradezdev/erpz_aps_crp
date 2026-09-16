# Copyright (c) 2026, ERPZ and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import flt

class APSProductRouting(Document):
	def validate(self):
		if hasattr(self, "operations"):
			for row in self.operations:
				batch = flt(row.batch_qty)
				cycle = flt(row.cycle_time_mins)
				if batch > 0:
					row.time_per_unit_mins = round(cycle / batch, 4)
				else:
					row.time_per_unit_mins = cycle
