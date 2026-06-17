from odoo import models, fields


class GardenActionType(models.Model):
    _name = 'garden.action.type'
    _description = 'Type d\'action'

    name = fields.Char('Nom', required=True)
    description = fields.Text('Description')
