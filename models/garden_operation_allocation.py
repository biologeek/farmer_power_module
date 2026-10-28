from odoo import api, fields, models


class GardenOperationAllocation(models.Model):
    _name = 'garden.operation.allocation'
    _description = "Répartition d'une opération sur une culture"
    _order = 'date desc, operation_id, id'
    # Lignes calculées quand une opération passe à « faite » : le temps et le coût sont répartis entre
    # les cultures concernées. Les rapports de rentabilité (phase 5) ne lisent que ces lignes.

    operation_id = fields.Many2one(
        'garden.operation', string='Opération', required=True, index=True, ondelete='cascade',
    )
    crop_id = fields.Many2one(
        'garden.crop', string='Culture', required=True, index=True, ondelete='cascade',
    )
    company_id = fields.Many2one(
        'res.company', string='Société', related='operation_id.company_id', store=True, index=True,
    )
    date = fields.Date(
        'Date', related='operation_id.date', store=True, index=True,
        help="Date de réalisation de l'opération.",
    )
    type_id = fields.Many2one(
        'garden.operation.type', string="Type d'opération", related='operation_id.type_id', store=True, index=True,
    )
    category = fields.Selection(related='operation_id.category', string='Catégorie', store=True)
    bed_id = fields.Many2one('garden.bed', string='Planche', related='crop_id.bed_id', store=True, index=True)
    template_id = fields.Many2one(
        'garden.crop.template', string='Itinéraire', related='crop_id.template_id', store=True, index=True,
    )
    variety_id = fields.Many2one('garden.variety', string='Variété', related='crop_id.variety_id', store=True)
    share = fields.Float(
        'Part (%)',
        help="Part de l'opération attribuée à la culture, au prorata de sa surface occupée.",
    )
    hours = fields.Float(
        'Heures', compute='_compute_amounts', store=True,
        help="Temps total de l'opération × part de la culture.",
    )
    labour_cost = fields.Float(
        'Coût main-d\'œuvre', compute='_compute_labour_cost', store=True, digits='Product Price',
        groups='odoo_garden.group_garden_chef',
        help="Coût de main-d'œuvre de l'opération × part de la culture.",
    )
    input_cost = fields.Float(
        'Coût des intrants', compute='_compute_input_cost', store=True, digits='Product Price',
        groups='odoo_garden.group_garden_chef',
        help="Coût des intrants de l'opération × part de la culture.",
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
