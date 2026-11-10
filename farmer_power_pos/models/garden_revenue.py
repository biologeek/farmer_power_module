from collections import defaultdict

from odoo import api, fields, models


class GardenRevenue(models.AbstractModel):
    _inherit = 'garden.revenue'
    # Ventes de marché du point de vente (pont ``farmer_power_pos``).
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
    def _pos_line_entries(self, line_ids):
        """``{id de ligne PdV: entrée de chiffre d'affaires (montant = montant HT de la ligne)}``.

        Lecture groupée des lignes et des commandes (sans enregistrement ORM par ligne) : le coût reste
        proportionnel au nombre de lignes, avec une petite constante.
        """
        Order = self.env['pos.order'].sudo()
        lines = self.env['pos.order.line'].sudo().browse(line_ids).read(['order_id', 'product_id', 'qty', 'price_subtotal'])
        orders = {
            order['id']: order for order in Order.browse(list({line['order_id'][0] for line in lines})).read(
                ['date_order', 'company_id', 'currency_id', 'partner_id', 'pos_reference', 'name'])
        }
        companies = {company.id: company for company in self.env['res.company'].sudo().browse(
            list({order['company_id'][0] for order in orders.values()}))}
        currencies, days, entries = {}, {}, {}
        for line in lines:
            order = orders[line['order_id'][0]]
            company = companies[order['company_id'][0]]
            currency_id = order['currency_id'][0] if order['currency_id'] else company.currency_id.id
            currency = currencies.setdefault(currency_id, self.env['res.currency'].browse(currency_id))
            moment = order['date_order']
            line_amount = currency._convert(line['price_subtotal'], company.currency_id, company, moment.date())
            day = days.get(moment)
            if day is None:
                day = days[moment] = fields.Datetime.context_timestamp(Order, moment).date()
            entries[line['id']] = {
                'key': ('pos.order.line', line['id']),
                'date': day,
                'document': order['pos_reference'] or order['name'],
                'is_refund': line['qty'] < 0 or line_amount < 0,
                'partner_id': order['partner_id'][0] if order['partner_id'] else False,
                'product_id': line['product_id'][0],
                'quantity': line['qty'],
                'line_amount': line_amount,
                'amount': line_amount,
                '_moment': moment,  # clé de tri (retirée par l'appelant)
            }
        return entries

    @api.model
    def _pos_line_amounts(self, line_ids):
        """``{id de ligne PdV: montant HT en monnaie de la société}`` (lecture groupée, sans enregistrement par ligne)."""
        lines = self.env['pos.order.line'].sudo().browse(line_ids).read(['order_id', 'price_subtotal'])
        Order = self.env['pos.order'].sudo()
        orders = {
            order['id']: order for order in Order.browse(list({line['order_id'][0] for line in lines})).read(
                ['date_order', 'company_id', 'currency_id'])
        }
        companies = {company.id: company for company in self.env['res.company'].sudo().browse(
            list({order['company_id'][0] for order in orders.values()}))}
        currencies = {}
        amounts = {}
        for line in lines:
            order = orders[line['order_id'][0]]
            company = companies[order['company_id'][0]]
            currency_id = order['currency_id'][0] if order['currency_id'] else company.currency_id.id
            if currency_id == company.currency_id.id:
                amounts[line['id']] = line['price_subtotal']
            else:
                currency = currencies.setdefault(currency_id, self.env['res.currency'].browse(currency_id))
                amounts[line['id']] = currency._convert(
                    line['price_subtotal'], company.currency_id, company, order['date_order'].date(),
                )
        return amounts

    @api.model
    def get_extra_totals(self, crops, method=None):
        # Remplace le calcul par défaut (qui passerait par ``get_extra_entries``, donc par ce pont) : le pont PdV
        # est la seule source d'entrées supplémentaires ; un autre pont qui en ajoute doit surcharger aussi
        # ``get_extra_totals`` en appelant ``super()`` et en ajoutant sa part.
        result = {}
        crops = crops.sudo()
        method = method or self._get_method()
        shares = self._pos_shares_by_lot(crops) if method == 'lot' else self._pos_shares_prorata(crops)
        amounts = self._pos_line_amounts(list({line_id for by_line in shares.values() for line_id in by_line}))
        for crop_id, by_line in shares.items():
            kept = [(line_id, share) for line_id, share in by_line.items() if share]
            if kept:
                total, count = result.get(crop_id, (0.0, 0))
                result[crop_id] = (total + sum(share * amounts[line_id] for line_id, share in kept), count + len(kept))
        return result

    @api.model
    def get_extra_entries(self, crops, method=None):
        result = super().get_extra_entries(crops, method)
        crops = crops.sudo()
        method = method or self._get_method()
        if method == 'lot':
            shares = self._pos_shares_by_lot(crops)
        else:
            shares = self._pos_shares_prorata(crops)
        # part de chaque culture par ligne (index inversé : évite le produit lignes × cultures)
        line_shares = defaultdict(list)
        for crop_id, by_line in shares.items():
            for line_id, share in by_line.items():
                if share:
                    line_shares[line_id].append((crop_id, share))
        entries = self._pos_line_entries(list(line_shares))
        for line_id, entry in sorted(entries.items(), key=lambda item: (item[1]['_moment'], item[0])):
            entry = {key: value for key, value in entry.items() if key != '_moment'}
            for crop_id, share in line_shares[line_id]:
                result.setdefault(crop_id, []).append(dict(entry, amount=share * entry['line_amount']))
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
        lines = self.env['pos.order.line'].sudo().search_read(
            self._get_pos_line_domain('prorata') + [('product_id', 'in', list(products))], ['product_id', 'order_id'],
        )
        Order = self.env['pos.order'].sudo()
        orders = {
            order['id']: order for order in Order.browse(list({line['order_id'][0] for line in lines})).read(
                ['date_order', 'company_id'])
        }
        months = {}  # date de commande -> (année, mois) dans le fuseau de l'utilisateur
        for line in lines:
            order = orders[line['order_id'][0]]
            moment = months.get(order['date_order'])
            if moment is None:
                date = fields.Datetime.context_timestamp(Order, order['date_order'])
                moment = months[order['date_order']] = (date.year, date.month)
            by_crop = harvests.get((line['product_id'][0], order['company_id'][0]) + moment)
            if not by_crop:
                continue  # mois sans récolte de ce produit : chiffre d'affaires non attribué
            total = sum(quantity for quantity in by_crop.values() if quantity > 0)
            if total <= 0:
                continue
            for crop_id, quantity in by_crop.items():
                if quantity > 0 and crop_id in result:
                    result[crop_id][line['id']] = quantity / total
        return result
