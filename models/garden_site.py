from odoo import fields, models


class GardenSite(models.Model):
    _name = 'garden.site'
    _description = 'Site de la ferme'
    _order = 'farm_id, name'

    name = fields.Char('Nom du site', required=True)
    farm_id = fields.Many2one('garden.farm', string='Ferme', required=True, index=True, ondelete='cascade')
    company_id = fields.Many2one(
        'res.company', string='Société', related='farm_id.company_id', store=True, index=True,
    )
    partner_id = fields.Many2one('res.partner', string='Adresse')
    latitude = fields.Float('Latitude', digits=(10, 7))
    longitude = fields.Float('Longitude', digits=(10, 7))
    garden_ids = fields.One2many('garden.garden', 'site_id', string='Îlots')
    active = fields.Boolean('Actif', default=True)
