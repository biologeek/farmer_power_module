from odoo import fields, models


class GardenFarm(models.Model):
    _name = 'garden.farm'
    _description = 'Ferme'
    _order = 'name'

    name = fields.Char('Nom de la ferme', required=True)
    company_id = fields.Many2one(
        'res.company', string='Société', required=True, index=True,
        default=lambda self: self.env.company,
    )
    site_ids = fields.One2many('garden.site', 'farm_id', string='Sites')
    active = fields.Boolean('Actif', default=True)
