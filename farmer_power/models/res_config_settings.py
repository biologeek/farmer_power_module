from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    garden_seed_margin = fields.Float(
        'Sowing Margin (%)', config_parameter='farmer_power.seed_margin', default=20.0,
        help='Extra seeds planned to compensate sowing losses, on top of the germination rate.',
    )
    garden_default_hourly_rate = fields.Float(
        'Default Hourly Rate', config_parameter='farmer_power.default_hourly_rate', default=15.0,
        help='Hourly cost applied to work time when the employee has no hourly cost set or when no employee is '
             'assigned to the operation.',
    )
    garden_revenue_method = fields.Selection(
        [('prorata', "Pro rata of the month's harvests"), ('lot', 'By Delivery Lot')],
        string='Revenue Attribution', config_parameter='farmer_power.revenue_method',
        default='prorata',
        help='By lot: the revenue of an invoice goes to the crops whose lots were delivered (lot-tracked '
             'products, invoices from sales orders). Pro rata: for each product and each month, the revenue is '
             'split between the crops according to their harvests of the month.',
    )
    garden_fixed_cost_per_m2 = fields.Float(
        'Annual Fixed Costs per m²', config_parameter='farmer_power.fixed_cost_per_m2', default=0.0,
        help='Option: annual cost per m² charged to the crops (cost × area × days of occupation / 365). Leave '
             'at 0 to charge no fixed costs.',
    )

    garden_compliance_enabled = fields.Boolean(
        'Regulatory Registers (France)', config_parameter='farmer_power.compliance_enabled', default=True,
        help='Shows the "Compliance" menu (plant protection register, fertilization register, organic '
             'certification export) to the crop manager and the manager. Untick outside France: the menus and '
             'exports are then hidden and refused. The pre-harvest interval check stays active (it only blocks '
             'products that have an interval).',
    )

    garden_stock_location_id = fields.Many2one(
        'stock.location', string='Storage Location', domain="[('usage', '=', 'internal')]",
        related='company_id.garden_stock_location_id', readonly=False, check_company=True,
        help='Location where harvests enter and inputs leave. Empty: main stock of the warehouse of the company.',
    )
    garden_production_location_id = fields.Many2one(
        'stock.location', string='Market Gardening Production Location', domain="[('usage', '=', 'production')]",
        related='company_id.garden_production_location_id', readonly=False, check_company=True,
        help='Virtual location harvests come from (created at installation).',
    )
    garden_consumption_location_id = fields.Many2one(
        'stock.location', string='Market Gardening Consumption Location', domain="[('usage', '=', 'production')]",
        related='company_id.garden_consumption_location_id', readonly=False, check_company=True,
        help='Virtual location consumed inputs go to (created at installation).',
    )

    @api.model
    def _garden_set_compliance_group(self, enabled):
        """Ajoute ou retire le groupe des registres réglementaires au chef de culture (et donc au gérant)."""
        chef = self.env.ref('farmer_power.group_garden_chef')
        compliance = self.env.ref('farmer_power.group_garden_compliance')
        if enabled:
            chef._apply_group(compliance)
        else:
            chef._remove_group(compliance)

    @api.model
    def _garden_init_compliance(self):
        """À l'installation et à la mise à jour : active les registres tant que le paramètre n'a jamais été réglé."""
        params = self.env['ir.config_parameter'].sudo()
        if params.get_param('farmer_power.compliance_enabled') is False:
            params.set_param('farmer_power.compliance_enabled', 'True')
            self._garden_set_compliance_group(True)

    def set_values(self):
        params = self.env['ir.config_parameter'].sudo()
        previous_margin = float(params.get_param('farmer_power.seed_margin', 20.0))
        previous_rate = float(params.get_param('farmer_power.default_hourly_rate', 15.0))
        super().set_values()
        # set_param(False) supprimerait le paramètre, qui vaut « activé » par défaut : on stocke 'False' explicitement
        params.set_param('farmer_power.compliance_enabled', 'True' if self.garden_compliance_enabled else 'False')
        self._garden_set_compliance_group(self.garden_compliance_enabled)
        if self.garden_seed_margin != previous_margin:
            # les besoins en semences stockés sur les cultures dépendent de ce paramètre système
            self.env['garden.crop'].sudo().search([])._recompute_seed_needs()
        if self.garden_default_hourly_rate != previous_rate:
            # idem pour le coût de main-d'œuvre des opérations
            self.env['garden.operation'].sudo().search([])._recompute_labour_cost()
