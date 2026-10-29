from odoo import api, models


class PosOrder(models.Model):
    _inherit = 'pos.order'

    def _invalidate_garden_revenue(self):
        """Le chiffre d'affaires des cultures (champs non stockés) dépend des commandes du point de vente."""
        self.env['garden.crop'].invalidate_model(['revenue', 'sale_line_count', 'margin', 'margin_per_hour', 'margin_per_m2'])

    @api.model_create_multi
    def create(self, vals_list):
        orders = super().create(vals_list)
        orders._invalidate_garden_revenue()
        return orders

    def write(self, vals):
        result = super().write(vals)
        if {'state', 'account_move', 'lines', 'date_order'} & set(vals):
            self._invalidate_garden_revenue()
        return result

    def unlink(self):
        self._invalidate_garden_revenue()
        return super().unlink()
