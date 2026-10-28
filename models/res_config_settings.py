from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    garden_seed_margin = fields.Float(
        'Marge de semis (%)', config_parameter='odoo_garden.seed_margin', default=20.0,
        help="Surplus de graines prévu pour compenser les pertes au semis, en plus du taux de germination.",
    )

    def set_values(self):
        previous = float(self.env['ir.config_parameter'].sudo().get_param('odoo_garden.seed_margin', 20.0))
        super().set_values()
        if self.garden_seed_margin != previous:
            # les besoins en semences stockés sur les cultures dépendent de ce paramètre système
            self.env['garden.crop'].sudo().search([])._recompute_seed_needs()
