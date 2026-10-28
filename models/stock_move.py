from odoo import fields, models


class StockMove(models.Model):
    _inherit = 'stock.move'

    garden_operation_id = fields.Many2one(
        'garden.operation', string='Opération maraîchage', index='btree_not_null', ondelete='set null', copy=False,
        help="Opération qui a créé ce mouvement (consommation d'intrants ou récolte).",
    )
    garden_crop_id = fields.Many2one(
        'garden.crop', string='Culture', index='btree_not_null', ondelete='set null', copy=False,
        help="Culture récoltée (mouvements de récolte).",
    )
    garden_kind = fields.Selection(
        [
            ('input', 'Consommation d\'intrant'),
            ('input_return', 'Annulation de consommation'),
            ('harvest', 'Récolte'),
            ('harvest_return', 'Annulation de récolte'),
        ],
        string='Type de mouvement maraîchage', index='btree_not_null', copy=False,
        help="Nature du mouvement créé par le module de maraîchage ; les annulations sont des mouvements inverses.",
    )
    garden_reverse_of_id = fields.Many2one(
        'stock.move', string='Annule le mouvement', index='btree_not_null', ondelete='set null', copy=False,
        help="Mouvement d'origine, pour un mouvement qui annule une consommation ou une récolte.",
    )
    garden_reversal_ids = fields.One2many(
        'stock.move', 'garden_reverse_of_id', string='Annulations',
        help="Mouvements inverses qui annulent celui-ci.",
    )


class StockLot(models.Model):
    _inherit = 'stock.lot'

    garden_crop_id = fields.Many2one(
        'garden.crop', string='Culture', index='btree_not_null', ondelete='set null', copy=False,
        help="Culture dont la récolte a produit ce lot (traçabilité amont).",
    )
