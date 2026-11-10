from odoo import api, fields, models

# Icône (classe Font Awesome) proposée par défaut selon la catégorie
CATEGORY_ICONS = {
    'soil_preparation': 'fa-tractor',
    'sowing': 'fa-circle-o',
    'transplanting': 'fa-exchange',
    'planting': 'fa-leaf',
    'irrigation': 'fa-tint',
    'weeding': 'fa-scissors',
    'fertilization': 'fa-flask',
    'treatment': 'fa-medkit',
    'mulching': 'fa-th',
    'harvest': 'fa-shopping-basket',
    'post_harvest': 'fa-archive',
    'other': 'fa-wrench',
}


class GardenOperationType(models.Model):
    _name = 'garden.operation.type'
    _description = 'Operation Type'
    _order = 'sequence, id'
    # Remplace l'ancien « type d'action » : le catalogue des types sert aux opérations réalisées
    # comme aux étapes des itinéraires techniques.

    name = fields.Char('Name', required=True, translate=True)
    category = fields.Selection(
        [
            ('soil_preparation', 'Soil Preparation'),
            ('sowing', 'Sowing'),
            ('transplanting', 'Transplanting'),
            ('planting', 'Planting'),
            ('irrigation', 'Irrigation'),
            ('weeding', 'Weeding'),
            ('fertilization', 'Fertilization'),
            ('treatment', 'Treatment'),
            ('mulching', 'Mulching'),
            ('harvest', 'Harvest'),
            ('post_harvest', 'Post-harvest (washing, packing)'),
            ('other', 'Other'),
        ],
        string='Category', required=True, default='other',
        help='Work category: it determines the specific fields of the operation (harvest, irrigation, treatment).',
    )
    default_scope = fields.Selection(
        [('crop', 'Crop'), ('bed', 'Bed'), ('garden', 'Block')],
        string='Default Scope', required=True, default='crop',
        help='Scope suggested when creating an operation of this type.',
    )
    requires_quantity = fields.Boolean(
        'Quantity Required', compute='_compute_requires_quantity', store=True, readonly=False,
        help='Ticked for harvest: the operation cannot be completed without a harvested quantity.',
    )
    icon = fields.Char(
        'Icon', compute='_compute_icon', store=True, readonly=False,
        help='Font Awesome class displayed on the "My Day" card (e.g. fa-tint).',
    )
    description = fields.Text('Description')
    sequence = fields.Integer('Sequence', default=10)
    active = fields.Boolean('Active', default=True)

    @api.depends('category')
    def _compute_requires_quantity(self):
        for operation_type in self:
            operation_type.requires_quantity = operation_type.category == 'harvest'

    @api.depends('category')
    def _compute_icon(self):
        for operation_type in self:
            operation_type.icon = CATEGORY_ICONS.get(operation_type.category, 'fa-wrench')
