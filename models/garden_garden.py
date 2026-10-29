from odoo import api, fields, models


class GardenGarden(models.Model):
    _name = 'garden.garden'
    _description = 'Block (irrigation sector)'
    _order = 'site_id, code, name'

    name = fields.Char('Block name', required=True)
    code = fields.Char('Code')
    site_id = fields.Many2one('garden.site', string='Site', required=True, index=True, ondelete='cascade')
    company_id = fields.Many2one(
        'res.company', string='Company', related='site_id.company_id', store=True, index=True,
    )
    bed_ids = fields.One2many('garden.bed', 'garden_id', string='Beds')
    culture_type = fields.Selection(
        [('open_air', 'Open Field'), ('sheltered', 'Sheltered (greenhouse, tunnel)')],
        string='Crop Type', default='open_air',
    )
    irrigation_type = fields.Selection(
        [
            ('drip', 'Drip'),
            ('sprinkler', 'Sprinkler'),
            ('manual', 'Manual'),
            ('none', 'None'),
        ],
        string='Irrigation Type', default='none',
    )
    irrigation_flow = fields.Float('Irrigation Flow (L/h)')
    area = fields.Float('Area (m²)', compute='_compute_area', store=True)
    active = fields.Boolean('Active', default=True)

    @api.depends('bed_ids.area')
    def _compute_area(self):
        for garden in self:
            garden.area = sum(garden.bed_ids.mapped('area'))
