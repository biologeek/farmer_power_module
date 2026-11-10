from odoo import api, fields, models


class GardenOperationWorker(models.Model):
    _name = 'garden.operation.worker'
    _description = 'Time Spent per Employee on an Operation'
    _order = 'operation_id, id'

    operation_id = fields.Many2one(
        'garden.operation', string='Operation', required=True, index=True, ondelete='cascade',
    )
    company_id = fields.Many2one(
        'res.company', string='Company', related='operation_id.company_id', store=True, index=True,
    )
    employee_id = fields.Many2one(
        'hr.employee', string='Employee', required=True, index=True, ondelete='restrict',
        help='Employee who worked on the operation.',
    )
    duration = fields.Float('Duration', help='Time spent by this employee, in hours (hh:mm).')
    labour_cost = fields.Float(
        'Labor Cost', compute='_compute_labour_cost', store=True, digits='Product Price',
        groups='farmer_power.group_garden_chef',
        help='Duration × hourly cost of the employee (otherwise, default hourly rate).',
    )

    _operation_employee_uniq = models.Constraint(
        'UNIQUE (operation_id, employee_id)', 'This employee is already in the operation details.',
    )
    _duration_positive = models.Constraint(
        'CHECK (duration >= 0)', 'The duration cannot be negative.',
    )

    @api.depends('duration', 'employee_id.garden_hourly_cost')
    def _compute_labour_cost(self):
        default_rate = self.env['garden.operation']._get_default_hourly_rate()
        for line in self:
            line.labour_cost = line.duration * (line.employee_id.garden_hourly_cost or default_rate)

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines._sync_operation_employees()
        return lines

    def write(self, vals):
        result = super().write(vals)
        if 'employee_id' in vals:
            self._sync_operation_employees()
        return result

    def _sync_operation_employees(self):
        """Les employés détaillés figurent aussi parmi les employés de l'opération (filtres, « Ma journée »)."""
        for line in self:
            if line.employee_id not in line.operation_id.employee_ids:
                line.operation_id.employee_ids = [(4, line.employee_id.id)]

    def _recompute_labour_cost(self):
        self.env.add_to_compute(self._fields['labour_cost'], self)
