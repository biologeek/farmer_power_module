from odoo import models, fields

class GardenPostProcess(models.Model):
    _name = 'garden.postprocess'
    _description = 'Post-process (lavage, stockage)'

    name = fields.Char('Type de post-process', required=True)
    date = fields.Date('Date')
    action_id = fields.Many2one('garden.action', string='Action liée')
    description = fields.Text('Description')
