from odoo import models


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _invalidate_garden_revenue(self):
        """Le chiffre d'affaires des cultures (champs non stockés) dépend des factures comptabilisées."""
        self.env['garden.crop'].invalidate_model(['revenue', 'margin', 'margin_per_hour', 'margin_per_m2'])

    def write(self, vals):
        result = super().write(vals)
        if 'state' in vals:
            self._invalidate_garden_revenue()
        return result

    def unlink(self):
        self._invalidate_garden_revenue()
        return super().unlink()
