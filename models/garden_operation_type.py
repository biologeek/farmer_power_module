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
    _description = "Type d'opération"
    _order = 'sequence, id'
    # Remplace l'ancien « type d'action » : le catalogue des types sert aux opérations réalisées
    # comme aux étapes des itinéraires techniques.

    name = fields.Char('Nom', required=True, translate=True)
    category = fields.Selection(
        [
            ('soil_preparation', 'Préparation du sol'),
            ('sowing', 'Semis'),
            ('transplanting', 'Repiquage'),
            ('planting', 'Plantation'),
            ('irrigation', 'Irrigation'),
            ('weeding', 'Désherbage'),
            ('fertilization', 'Fertilisation'),
            ('treatment', 'Traitement'),
            ('mulching', 'Paillage'),
            ('harvest', 'Récolte'),
            ('post_harvest', 'Après récolte (lavage, conditionnement)'),
            ('other', 'Autre'),
        ],
        string='Catégorie', required=True, default='other',
        help="Catégorie de travail : elle conditionne les champs spécifiques de l'opération "
             "(récolte, irrigation, traitement).",
    )
    default_scope = fields.Selection(
        [('crop', 'Culture'), ('bed', 'Planche'), ('garden', 'Îlot')],
        string='Périmètre par défaut', required=True, default='crop',
        help="Périmètre proposé à la création d'une opération de ce type.",
    )
    requires_quantity = fields.Boolean(
        'Quantité obligatoire', compute='_compute_requires_quantity', store=True, readonly=False,
        help="Cochée pour la récolte : l'opération ne peut pas être terminée sans quantité récoltée.",
    )
    icon = fields.Char(
        'Icône', compute='_compute_icon', store=True, readonly=False,
        help="Classe Font Awesome affichée sur la carte « Ma journée » (ex. fa-tint).",
    )
    description = fields.Text('Description')
    sequence = fields.Integer('Séquence', default=10)
    active = fields.Boolean('Actif', default=True)

    @api.depends('category')
    def _compute_requires_quantity(self):
        for operation_type in self:
            operation_type.requires_quantity = operation_type.category == 'harvest'

    @api.depends('category')
    def _compute_icon(self):
        for operation_type in self:
            operation_type.icon = CATEGORY_ICONS.get(operation_type.category, 'fa-wrench')
