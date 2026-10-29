from odoo import fields, models


class GardenSite(models.Model):
    _name = 'garden.site'
    _description = 'Site of the farm'
    _order = 'farm_id, name'

    name = fields.Char('Site name', required=True)
    farm_id = fields.Many2one('garden.farm', string='Farm', required=True, index=True, ondelete='cascade')
    company_id = fields.Many2one(
        'res.company', string='Company', related='farm_id.company_id', store=True, index=True,
    )
    partner_id = fields.Many2one('res.partner', string='Address')
    latitude = fields.Float('Latitude', digits=(10, 7))
    longitude = fields.Float('Longitude', digits=(10, 7))
    garden_ids = fields.One2many('garden.garden', 'site_id', string='Blocks')
    active = fields.Boolean('Active', default=True)
