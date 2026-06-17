from odoo import models, fields

class GardenGarden(models.Model):
    _name = 'garden.garden'
    _description = 'Jardin (regroupement de parcelles)'

    name = fields.Char('Nom du jardin', required=True)
    site_id = fields.Many2one('garden.site', string='Site', required=True)
    bed_ids = fields.One2many('garden.bed', 'garden_id', string='Planches')
