from odoo import models, fields

class GardenSite(models.Model):
    _name = 'garden.site'
    _description = 'Site de la ferme'

    name = fields.Char('Nom du site', required=True)
    farm_id = fields.Many2one('garden.farm', string='Ferme', required=True)
    garden_ids = fields.One2many('garden.garden', 'site_id', string='Jardins')
