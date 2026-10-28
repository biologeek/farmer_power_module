from odoo import api, fields, models


class GardenGarden(models.Model):
    _name = 'garden.garden'
    _description = 'Îlot (secteur d\'irrigation)'
    _order = 'site_id, code, name'

    name = fields.Char('Nom de l\'îlot', required=True)
    code = fields.Char('Code')
    site_id = fields.Many2one('garden.site', string='Site', required=True, index=True, ondelete='cascade')
    company_id = fields.Many2one(
        'res.company', string='Société', related='site_id.company_id', store=True, index=True,
    )
    bed_ids = fields.One2many('garden.bed', 'garden_id', string='Planches')
    culture_type = fields.Selection(
        [('open_air', 'Plein air'), ('sheltered', 'Sous abri (serre, tunnel)')],
        string='Type de culture', default='open_air',
    )
    irrigation_type = fields.Selection(
        [
            ('drip', 'Goutte-à-goutte'),
            ('sprinkler', 'Aspersion'),
            ('manual', 'Manuel'),
            ('none', 'Aucun'),
        ],
        string="Type d'irrigation", default='none',
    )
    irrigation_flow = fields.Float('Débit d\'irrigation (L/h)')
    area = fields.Float('Surface (m²)', compute='_compute_area', store=True)
    active = fields.Boolean('Actif', default=True)

    @api.depends('bed_ids.area')
    def _compute_area(self):
        for garden in self:
            garden.area = sum(garden.bed_ids.mapped('area'))
