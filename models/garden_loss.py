from odoo import models, fields

class GardenLoss(models.Model):
    _name = 'garden.loss'
    _description = 'Pertes'

    date = fields.Date('Date')
    bed_id = fields.Many2one('garden.bed', string='Planche')
    quantity = fields.Float('Quantité perdue')
    reason = fields.Char('Raison')
