from odoo import models, fields


class GardenPlot(models.Model):
    _name = 'garden.plot'
    _description = 'Parcelle (temporaire)'

    name = fields.Char('Nom de la parcelle', required=True)
    bed_id = fields.Many2one('garden.bed', string='Planche', required=True)
