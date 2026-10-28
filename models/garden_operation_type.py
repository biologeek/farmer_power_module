from odoo import fields, models


class GardenOperationType(models.Model):
    _name = 'garden.operation.type'
    _description = "Type d'opération"
    _order = 'sequence, id'

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
    )
    default_scope = fields.Selection(
        [('crop', 'Culture'), ('bed', 'Planche'), ('garden', 'Îlot')],
        string='Périmètre par défaut', required=True, default='crop',
    )
    sequence = fields.Integer('Séquence', default=10)
    active = fields.Boolean('Actif', default=True)
