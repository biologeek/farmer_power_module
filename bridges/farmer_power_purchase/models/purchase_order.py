from odoo import fields, models


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    garden_season_id = fields.Many2one(
        'garden.season', string='Garden Season', index='btree_not_null', copy=False,
        help="Season whose seed needs generated this request for quotation.",
    )


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    garden_season_id = fields.Many2one(
        'garden.season', string='Garden Season', related='order_id.garden_season_id', store=True, index='btree_not_null',
    )
    garden_variety_id = fields.Many2one(
        'garden.variety', string='Garden Variety', index='btree_not_null', copy=False,
        help="Variety whose seeds or plants this line covers. Used to avoid ordering the same need twice.",
    )
