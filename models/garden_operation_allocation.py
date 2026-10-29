from odoo import api, fields, models


class GardenOperationAllocation(models.Model):
    _name = 'garden.operation.allocation'
    _description = 'Allocation of an Operation to a Crop'
    _order = 'date desc, operation_id, id'
    # Lignes calculées quand une opération passe à « faite » : le temps et le coût sont répartis entre
    # les cultures concernées. Les rapports de rentabilité (phase 5) ne lisent que ces lignes.

    operation_id = fields.Many2one(
        'garden.operation', string='Operation', required=True, index=True, ondelete='cascade',
    )
    crop_id = fields.Many2one(
        'garden.crop', string='Crop', required=True, index=True, ondelete='cascade',
    )
    company_id = fields.Many2one(
        'res.company', string='Company', related='operation_id.company_id', store=True, index=True,
    )
    date = fields.Date(
        'Date', related='operation_id.date', store=True, index=True,
        help='Date the operation was carried out.',
    )
    type_id = fields.Many2one(
        'garden.operation.type', string='Operation Type', related='operation_id.type_id', store=True, index=True,
    )
    category = fields.Selection(related='operation_id.category', string='Category', store=True)
    bed_id = fields.Many2one('garden.bed', string='Bed', related='crop_id.bed_id', store=True, index=True)
    template_id = fields.Many2one(
        'garden.crop.template', string='Template', related='crop_id.template_id', store=True, index=True,
    )
    variety_id = fields.Many2one('garden.variety', string='Variety', related='crop_id.variety_id', store=True)
    share = fields.Float(
        'Share (%)',
        help='Share of the operation attributed to the crop, proportional to its occupied area.',
    )
    hours = fields.Float(
        'Hours', compute='_compute_amounts', store=True,
        help='Total time of the operation × share of the crop.',
    )
    labour_cost = fields.Float(
        'Labor Cost', compute='_compute_labour_cost', store=True, digits='Product Price',
        groups='odoo_garden.group_garden_chef',
        help='Labor cost of the operation × share of the crop.',
    )
    input_cost = fields.Float(
        'Input Cost', compute='_compute_input_cost', store=True, digits='Product Price',
        groups='odoo_garden.group_garden_chef',
        help='Input cost of the operation × share of the crop.',
    )

    @api.depends('operation_id.total_hours', 'share')
    def _compute_amounts(self):
        for allocation in self:
            allocation.hours = allocation.operation_id.total_hours * allocation.share / 100.0

    @api.depends('operation_id.labour_cost', 'share')
    def _compute_labour_cost(self):
        for allocation in self:
            allocation.labour_cost = allocation.operation_id.labour_cost * allocation.share / 100.0

    @api.depends('operation_id.input_cost', 'share')
    def _compute_input_cost(self):
        for allocation in self:
            allocation.input_cost = allocation.operation_id.input_cost * allocation.share / 100.0
