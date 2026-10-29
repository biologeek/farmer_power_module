from datetime import timedelta

from odoo import api, fields, models


class GardenCropTemplate(models.Model):
    _name = 'garden.crop.template'
    _description = 'Crop Template'
    _order = 'name'

    name = fields.Char('Name', required=True)
    variety_id = fields.Many2one('garden.variety', string='Variety', required=True, index=True)
    species_id = fields.Many2one(
        'garden.species', string='Species', related='variety_id.species_id', store=True, index=True,
    )
    culture_type = fields.Selection(
        [('open_air', 'Open Field'), ('sheltered', 'Sheltered (greenhouse, tunnel)')],
        string='Crop Type', required=True, default='open_air',
    )
    propagation = fields.Selection(
        [
            ('direct_sowing', 'Direct Sowing'),
            ('own_plants', 'Own Plants'),
            ('bought_plants', 'Bought Plants'),
        ],
        string='Planting Method', required=True, default='direct_sowing',
    )
    plant_product_id = fields.Many2one('product.product', string='Plant Product')
    row_count = fields.Integer('Number of Rows')
    row_spacing = fields.Float('Row Spacing (cm)')
    plant_spacing = fields.Float('Plant Spacing (cm)')
    density = fields.Float(
        'Density (plants/m²)', compute='_compute_density', store=True,
        help='10,000 / (row spacing × plant spacing), in cm.',
    )
    days_to_transplant = fields.Integer('Days before Transplanting')
    days_to_maturity = fields.Integer('Days before Harvest')
    harvest_window_days = fields.Integer('Harvest Window (days)')
    expected_yield = fields.Float('Expected Yield (kg/m²)')
    expected_price = fields.Float(
        'Expected Sale Price (€/kg)', compute='_compute_expected_price', store=True,
        readonly=False, digits='Product Price',
    )
    step_ids = fields.One2many('garden.crop.template.step', 'template_id', string='Steps', copy=True)
    notes = fields.Text('Notes')
    active = fields.Boolean('Active', default=True)

    @api.depends('row_spacing', 'plant_spacing')
    def _compute_density(self):
        for template in self:
            if template.row_spacing > 0 and template.plant_spacing > 0:
                template.density = 10000.0 / (template.row_spacing * template.plant_spacing)
            else:
                template.density = 0.0

    @api.depends('variety_id.harvest_product_id.lst_price')
    def _compute_expected_price(self):
        for template in self:
            template.expected_price = template.variety_id.harvest_product_id.lst_price

    def _plan_dates(self, sowing_date=False, harvest_start=False):
        """Rétro-planning : calcule les dates prévues d'une culture suivant cet itinéraire.

        - depuis la date de semis : repiquage = semis + ``days_to_transplant`` (plants uniquement),
          début de récolte = semis + ``days_to_maturity``, fin = début + ``harvest_window_days`` ;
        - depuis la date de début de récolte : semis = récolte − ``days_to_maturity``, puis idem.

        Si les deux dates sont fournies, le semis fait foi. Retourne un dict de valeurs pour les
        champs ``planned_*`` de ``garden.crop`` (vide si aucune date n'est fournie).
        """
        self.ensure_one()
        sowing_date = fields.Date.to_date(sowing_date)
        harvest_start = fields.Date.to_date(harvest_start)
        if not sowing_date and not harvest_start:
            return {}
        if not sowing_date:
            sowing_date = harvest_start - timedelta(days=self.days_to_maturity)
        harvest_start = sowing_date + timedelta(days=self.days_to_maturity)
        has_transplant = self.propagation != 'direct_sowing'
        return {
            'planned_sowing_date': sowing_date,
            'planned_transplant_date': sowing_date + timedelta(days=self.days_to_transplant) if has_transplant else False,
            'planned_harvest_start': harvest_start,
            'planned_harvest_end': harvest_start + timedelta(days=self.harvest_window_days),
        }


class GardenCropTemplateStep(models.Model):
    _name = 'garden.crop.template.step'
    _description = 'Crop Template Step'
    _order = 'template_id, sequence, day_offset, id'

    template_id = fields.Many2one(
        'garden.crop.template', string='Template', required=True, index=True, ondelete='cascade',
    )
    sequence = fields.Integer('Sequence', default=10)
    operation_type_id = fields.Many2one(
        'garden.operation.type', string='Operation Type', required=True, ondelete='restrict',
    )
    category = fields.Selection(related='operation_type_id.category', string='Category')
    day_offset = fields.Integer('Offset (days from sowing)')
    expected_duration = fields.Float('Expected Duration (h/m²)', digits=(10, 4))
