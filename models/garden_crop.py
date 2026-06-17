from odoo import models, fields

class GardenCrop(models.Model):
    _name = 'garden.crop'
    _description = 'Culture sur planche'

    catalog_id = fields.Many2one('garden.crop.catalog', string='Catalogue de culture', required=True)
    sowing_quantity = fields.Float('Nombre de plants semés')
    planted_quantity = fields.Float('Nombre de plants plantés')
    bed_id = fields.Many2one('garden.bed', string='Planche', required=True)
    notes = fields.Text('Notes')
    date_start = fields.Date('Date de début')
    date_end = fields.Date('Date de fin')
    quantity_harvested = fields.Float('Quantité récoltée (kg)')
    value_harvested = fields.Float('Valeur récoltée (€)')
    action_ids = fields.One2many('garden.action', 'crop_id', string='Actions')
    # autres champs pertinents
