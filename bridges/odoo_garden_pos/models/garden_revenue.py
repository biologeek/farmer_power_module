from collections import defaultdict

from odoo import api, fields, models


class GardenRevenue(models.AbstractModel):
    _inherit = 'garden.revenue'
    # Ventes de marché du point de vente (pont ``odoo_garden_pos``).
    #
    # Lignes retenues : lignes de commandes PdV payées ou comptabilisées (états ``paid`` et ``done``), hors
    # commandes annulées ou en cours. Montant : ``price_subtotal`` (HT) converti en monnaie de la société à la
    # date de la commande ; un remboursement (quantité négative) donne un montant négatif.
    #
    # Double comptage avec les factures clients :
    # - méthode « au prorata » : le chiffre d'affaires facturé est déjà compté par les lignes de factures
    #   comptabilisées (une commande PdV facturée crée une facture client). Une commande qui possède une
    #   facture comptabilisée est donc ignorée ici ;
    # - méthode « par lot » : l'attribution par facture passe par la commande de vente et les mouvements de
    #   livraison, ce qu'une facture issue du PdV n'a pas ; les lots saisis sur la ligne PdV sont donc la seule
    #   source, et la commande est comptée même si elle est facturée (sans risque de double comptage).
    #
    # Par lot : les lots saisis sur la ligne (``pack_lot_ids``, ``pos.pack.operation.lot.lot_name``) sont
    # rapprochés des lots de culture par (produit, nom de lot). Le montant de la ligne est réparti à parts
    # égales entre les lots saisis ; la part des lots qui ne sont pas des lots de culture n'est attribuée à
    # aucune culture.

    @api.model
    def _get_pos_line_domain(self, method):
        domain = [
            ('order_id.state', 'in', ('paid', 'done')),
            ('product_id', '!=', False),
        ]
        if method != 'lot':
            domain += [
                '|', ('order_id.account_move', '=', False), ('order_id.account_move.state', '!=', 'posted'),
            ]
        return domain

    @api.model
    def _pos_entry(self, line, amount):
        order = line.order_id
        company = order.company_id
        line_amount = order.currency_id._convert(
            line.price_subtotal, company.currency_id, company, order.date_order.date(),
        )
        date = fields.Datetime.context_timestamp(order, order.date_order).date()
        return {
            'key': ('pos.order.line', line.id),
            'date': date,
            'document': order.pos_reference or order.name,
            'is_refund': line.qty < 0 or line_amount < 0,
            'partner_id': order.partner_id.id,
            'product_id': line.product_id.id,
            'quantity': line.qty,
            'line_amount': line_amount,
            'amount': amount * line_amount,
        }

    @api.model
    def get_extra_entries(self, crops, method=None):
        result = super().get_extra_entries(crops, method)
        crops = crops.sudo()
        method = method or self._get_method()
        if method == 'lot':
            shares = self._pos_shares_by_lot(crops)
        else:
            shares = self._pos_shares_prorata(crops)
        Line = self.env['pos.order.line'].sudo()
        lines = Line.browse({line_id for by_line in shares.values() for line_id in by_line})
        lines = lines.sorted(lambda line: (line.order_id.date_order, line.id))
        for line in lines:
            for crop_id, by_line in shares.items():
                share = by_line.get(line.id)
                if share:
                    result.setdefault(crop_id, []).append(self._pos_entry(line, share))
        return result

    @api.model
    def _pos_shares_by_lot(self, crops):
        """``{id de culture: {id de ligne PdV: part (0-1) du montant de la ligne}}``."""
        result = {crop.id: {} for crop in crops}
        lot_to_crop = {(lot.product_id.id, lot.name): lot.garden_crop_id.id for lot in crops.lot_ids}
        if not lot_to_crop:
            return result
        lines = self.env['pos.order.line'].sudo().search(self._get_pos_line_domain('lot') + [
            ('product_id', 'in', list({product_id for product_id, _name in lot_to_crop})),
            ('pack_lot_ids', '!=', False),
        ])
        for line in lines:
            lots = line.pack_lot_ids
            counts = defaultdict(int)
            for lot in lots:
                crop_id = lot_to_crop.get((line.product_id.id, lot.lot_name))
                if crop_id:
                    counts[crop_id] += 1
            for crop_id, count in counts.items():
                result[crop_id][line.id] = count / len(lots)
        return result

    @api.model
    def _pos_shares_prorata(self, crops):
        """``{id de culture: {id de ligne PdV: part (0-1) du montant de la ligne}}`` au prorata des récoltes du mois."""
        result = {crop.id: {} for crop in crops}
        harvests = {
            key: by_crop for key, by_crop in self._get_monthly_harvests().items()
            if any(crop_id in result for crop_id in by_crop)
        }
        if not harvests:
            return result
        products = {key[0] for key in harvests}
        lines = self.env['pos.order.line'].sudo().search(
            self._get_pos_line_domain('prorata') + [('product_id', 'in', list(products))],
        )
        for line in lines:
            order = line.order_id
            date = fields.Datetime.context_timestamp(order, order.date_order)
            by_crop = harvests.get((line.product_id.id, order.company_id.id, date.year, date.month))
            if not by_crop:
                continue  # mois sans récolte de ce produit : chiffre d'affaires non attribué
            total = sum(quantity for quantity in by_crop.values() if quantity > 0)
            if total <= 0:
                continue
            for crop_id, quantity in by_crop.items():
                if quantity > 0 and crop_id in result:
                    result[crop_id][line.id] = quantity / total
        return result
