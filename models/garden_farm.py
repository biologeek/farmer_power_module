from odoo import fields, models


class GardenFarm(models.Model):
    _name = 'garden.farm'
    _description = 'Farm'
    _order = 'name'

    name = fields.Char('Farm name', required=True)
    company_id = fields.Many2one(
        'res.company', string='Company', required=True, index=True,
        default=lambda self: self.env.company,
    )
    site_ids = fields.One2many('garden.site', 'farm_id', string='Sites')
    active = fields.Boolean('Active', default=True)
