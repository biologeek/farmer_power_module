from odoo import api, fields, models


class GardenCropTemplate(models.Model):
    _name = 'garden.crop.template'
    _description = 'Itinéraire technique'
    _order = 'name'

    name = fields.Char('Nom', required=True)
    variety_id = fields.Many2one('garden.variety', string='Variété', required=True, index=True)
    species_id = fields.Many2one(
        'garden.species', string='Espèce', related='variety_id.species_id', store=True, index=True,
    )
    culture_type = fields.Selection(
        [('open_air', 'Plein air'), ('sheltered', 'Sous abri (serre, tunnel)')],
        string='Type de culture', required=True, default='open_air',
    )
    propagation = fields.Selection(
        [
            ('direct_sowing', 'Semis direct'),
            ('own_plants', 'Plants autoproduits'),
            ('bought_plants', 'Plants achetés'),
        ],
        string='Mode de plantation', required=True, default='direct_sowing',
    )
    plant_product_id = fields.Many2one('product.product', string='Produit plant')
    row_count = fields.Integer('Nombre de rangs')
    row_spacing = fields.Float('Écartement entre rangs (cm)')
    plant_spacing = fields.Float('Écartement sur le rang (cm)')
    density = fields.Float(
        'Densité (plants/m²)', compute='_compute_density', store=True,
        help="10 000 / (écartement entre rangs × écartement sur le rang), en cm.",
    )
    days_to_transplant = fields.Integer('Jours avant repiquage')
    days_to_maturity = fields.Integer('Jours avant récolte')
    harvest_window_days = fields.Integer('Fenêtre de récolte (jours)')
    expected_yield = fields.Float('Rendement attendu (kg/m²)')
    expected_price = fields.Float(
        'Prix de vente attendu (€/kg)', compute='_compute_expected_price', store=True,
        readonly=False, digits='Product Price',
    )
    step_ids = fields.One2many('garden.crop.template.step', 'template_id', string='Étapes', copy=True)
    notes = fields.Text('Notes')
    active = fields.Boolean('Actif', default=True)

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


class GardenCropTemplateStep(models.Model):
    _name = 'garden.crop.template.step'
    _description = "Étape d'itinéraire technique"
    _order = 'template_id, sequence, day_offset, id'

    template_id = fields.Many2one(
        'garden.crop.template', string='Itinéraire', required=True, index=True, ondelete='cascade',
    )
    sequence = fields.Integer('Séquence', default=10)
    operation_type_id = fields.Many2one(
        'garden.operation.type', string="Type d'opération", required=True, ondelete='restrict',
    )
    category = fields.Selection(related='operation_type_id.category', string='Catégorie')
    day_offset = fields.Integer('Décalage (jours depuis le semis)')
    expected_duration = fields.Float('Durée attendue (h/m²)', digits=(10, 4))
