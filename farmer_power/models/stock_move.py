from odoo import fields, models


class StockMove(models.Model):
    _inherit = 'stock.move'

    garden_operation_id = fields.Many2one(
        'garden.operation', string='Market Gardening Operation', index='btree_not_null', ondelete='set null', copy=False,
        help='Operation that created this move (input consumption or harvest).',
    )
    garden_crop_id = fields.Many2one(
        'garden.crop', string='Crop', index='btree_not_null', ondelete='set null', copy=False,
        help='Harvested crop (harvest moves).',
    )
    garden_kind = fields.Selection(
        [
            ('input', 'Input Consumption'),
            ('input_return', 'Consumption Cancellation'),
            ('harvest', 'Harvest'),
            ('harvest_return', 'Harvest Cancellation'),
        ],
        string='Market Gardening Move Type', index='btree_not_null', copy=False,
        help='Kind of the move created by the market gardening module; cancellations are reverse moves.',
    )
    garden_reverse_of_id = fields.Many2one(
        'stock.move', string='Cancels the move', index='btree_not_null', ondelete='set null', copy=False,
        help='Original move, for a move that cancels a consumption or a harvest.',
    )
    garden_reversal_ids = fields.One2many(
        'stock.move', 'garden_reverse_of_id', string='Cancellations',
        help='Reverse moves that cancel this one.',
    )


class StockLot(models.Model):
    _inherit = 'stock.lot'

    garden_crop_id = fields.Many2one(
        'garden.crop', string='Crop', index='btree_not_null', ondelete='set null', copy=False,
        help='Crop whose harvest produced this lot (upstream traceability).',
    )
