from odoo import fields, models


class GardenSpecies(models.Model):
    _name = 'garden.species'
    _description = 'Espèce'
    _order = 'name'

    name = fields.Char('Espèce', required=True)
    family = fields.Selection(
        [
            ('solanaceae', 'Solanacées'),
            ('brassicaceae', 'Brassicacées'),
            ('cucurbitaceae', 'Cucurbitacées'),
            ('apiaceae', 'Apiacées'),
            ('asteraceae', 'Astéracées'),
            ('fabaceae', 'Fabacées'),
            ('amaryllidaceae', 'Amaryllidacées'),
            ('chenopodiaceae', 'Chénopodiacées'),
            ('poaceae', 'Poacées'),
            ('other', 'Autre'),
        ],
        string='Famille botanique', required=True, default='other',
    )
    rotation_years = fields.Integer(
        'Délai de rotation (années)', default=3,
        help="Délai minimal de retour de la famille sur une même planche.",
    )
    variety_ids = fields.One2many('garden.variety', 'species_id', string='Variétés')
    active = fields.Boolean('Actif', default=True)

    _name_uniq = models.Constraint('UNIQUE (name)', "Cette espèce existe déjà.")
    _rotation_years_positive = models.Constraint(
        'CHECK (rotation_years >= 0)', 'Le délai de rotation ne peut pas être négatif.',
    )
