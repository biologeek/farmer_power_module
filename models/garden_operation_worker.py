from odoo import api, fields, models


class GardenOperationWorker(models.Model):
    _name = 'garden.operation.worker'
    _description = "Temps passé par employé sur une opération"
    _order = 'operation_id, id'

    operation_id = fields.Many2one(
        'garden.operation', string='Opération', required=True, index=True, ondelete='cascade',
    )
    company_id = fields.Many2one(
        'res.company', string='Société', related='operation_id.company_id', store=True, index=True,
    )
    employee_id = fields.Many2one(
        'hr.employee', string='Employé', required=True, index=True, ondelete='restrict',
        help="Employé qui a travaillé sur l'opération.",
    )
    duration = fields.Float('Durée', help="Temps passé par cet employé, en heures (hh:mm).")
    labour_cost = fields.Float(
        'Coût main-d\'œuvre', compute='_compute_labour_cost', store=True, digits='Product Price',
        groups='odoo_garden.group_garden_chef',
        help="Durée × coût horaire de l'employé (à défaut, taux horaire par défaut).",
    )

    _operation_employee_uniq = models.Constraint(
        'UNIQUE (operation_id, employee_id)', 'Cet employé figure déjà dans le détail de l\'opération.',
    )
    _duration_positive = models.Constraint(
        'CHECK (duration >= 0)', 'La durée ne peut pas être négative.',
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
