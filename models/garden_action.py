from odoo import models, fields


class GardenAction(models.Model):
    _name = 'garden.action'
    _description = 'Action sur planche'

    type_id = fields.Many2one('garden.action.type', string='Type', required=True)
    date = fields.Date('Date')
    duration = fields.Integer('Durée (minutes)')
    crop_id = fields.Many2one('garden.crop', string='Culture', required=True)
    bed_id = fields.Many2one(
        'garden.bed',
        string='Planche',
        related='crop_id.bed_id',
        store=True,
        readonly=False,
    )
    description = fields.Text('Description')
