from odoo import models, fields

class GardenFarm(models.Model):
    _name = 'garden.farm'
    _description = 'Ferme'

    name = fields.Char('Nom de la ferme', required=True)
    site_ids = fields.One2many('garden.site', 'farm_id', string='Sites')
