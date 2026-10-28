from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    garden_seed_margin = fields.Float(
        'Marge de semis (%)', config_parameter='odoo_garden.seed_margin', default=20.0,
        help="Surplus de graines prévu pour compenser les pertes au semis, en plus du taux de germination.",
    )
    garden_default_hourly_rate = fields.Float(
        'Taux horaire par défaut', config_parameter='odoo_garden.default_hourly_rate', default=15.0,
        help="Coût horaire appliqué au temps de travail quand l'employé n'a pas de coût horaire "
             "renseigné ou qu'aucun employé n'est affecté à l'opération.",
    )

    garden_stock_location_id = fields.Many2one(
        'stock.location', string='Emplacement de stockage', domain="[('usage', '=', 'internal')]",
        related='company_id.garden_stock_location_id', readonly=False, check_company=True,
        help="Emplacement où entrent les récoltes et d'où sortent les intrants. "
             "Vide : stock principal de l'entrepôt de la société.",
    )
    garden_production_location_id = fields.Many2one(
        'stock.location', string='Emplacement « Production maraîchage »', domain="[('usage', '=', 'production')]",
        related='company_id.garden_production_location_id', readonly=False, check_company=True,
        help="Emplacement virtuel d'où sortent les récoltes (créé à l'installation).",
    )
    garden_consumption_location_id = fields.Many2one(
        'stock.location', string='Emplacement « Consommation maraîchage »', domain="[('usage', '=', 'production')]",
        related='company_id.garden_consumption_location_id', readonly=False, check_company=True,
        help="Emplacement virtuel où partent les intrants consommés (créé à l'installation).",
    )

    def set_values(self):
        params = self.env['ir.config_parameter'].sudo()
        previous_margin = float(params.get_param('odoo_garden.seed_margin', 20.0))
        previous_rate = float(params.get_param('odoo_garden.default_hourly_rate', 15.0))
        super().set_values()
        if self.garden_seed_margin != previous_margin:
            # les besoins en semences stockés sur les cultures dépendent de ce paramètre système
            self.env['garden.crop'].sudo().search([])._recompute_seed_needs()
        if self.garden_default_hourly_rate != previous_rate:
            # idem pour le coût de main-d'œuvre des opérations
            self.env['garden.operation'].sudo().search([])._recompute_labour_cost()
