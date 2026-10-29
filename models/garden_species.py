from odoo import fields, models


class GardenSpecies(models.Model):
    _name = 'garden.species'
    _description = 'Species'
    _order = 'name'

    name = fields.Char('Species', required=True)
    family = fields.Selection(
        [
            ('solanaceae', 'Solanaceae'),
            ('brassicaceae', 'Brassicaceae'),
            ('cucurbitaceae', 'Cucurbitaceae'),
            ('apiaceae', 'Apiaceae'),
            ('asteraceae', 'Asteraceae'),
            ('fabaceae', 'Fabaceae'),
            ('amaryllidaceae', 'Amaryllidaceae'),
            ('chenopodiaceae', 'Chenopodiaceae'),
            ('poaceae', 'Poaceae'),
            ('other', 'Other'),
        ],
        string='Botanical Family', required=True, default='other',
    )
    rotation_years = fields.Integer(
        'Rotation Interval (years)', default=3,
        help='Minimum time before the family returns to the same bed.',
    )
    variety_ids = fields.One2many('garden.variety', 'species_id', string='Varieties')
    active = fields.Boolean('Active', default=True)

    _name_uniq = models.Constraint('UNIQUE (name)', 'This species already exists.')
    _rotation_years_positive = models.Constraint(
        'CHECK (rotation_years >= 0)', 'The rotation interval cannot be negative.',
    )
