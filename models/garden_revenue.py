from collections import defaultdict

from odoo import api, models


class GardenRevenue(models.AbstractModel):
    _name = 'garden.revenue'
    _description = 'Revenue Attribution to Crops'
    # Service (pas de table) : calcule, à la demande, quelle part des lignes de factures clients
    # comptabilisées revient à chaque culture. Rien n'est stocké : la facture reste la source de vérité.
    #
    # Règles communes :
    # - seules comptent les lignes de produit des factures et avoirs clients comptabilisés ;
    # - le montant d'une ligne est son montant HT en monnaie de la société, tel que l'a converti la
    #   comptabilité à la date de la facture (``-balance`` : positif pour une facture, négatif pour un avoir) ;
    # - les factures sont lues en ``sudo()`` : ni l'ouvrier ni le chef de culture n'ont accès à la comptabilité,
    #   seul le montant attribué (agrégé, par culture) leur est exposé par les champs de la culture.
    #
    # Méthode « par lot » : ligne de facture -> ligne de commande -> mouvements de livraison -> lots de culture.
    # Le montant de la ligne est réparti au prorata des quantités livrées (retours déduits) sur la ligne de
    # commande. La part livrée sur un lot qui n'est pas un lot de culture, ou sans lot, n'est attribuée à
    # aucune culture. Une facture sans commande de vente ne peut pas être attribuée par lot.
    #
    # Méthode « au prorata » : pour un produit récolté et un mois (mois de la facture), le chiffre d'affaires
    # est réparti entre les cultures au prorata des quantités récoltées ce mois-là (mouvements de récolte
    # terminés, annulations déduites). Un mois sans récolte du produit n'attribue rien : le chiffre d'affaires
    # n'est pas inventé. Un avoir réduit le chiffre d'affaires du mois selon la même répartition.

    @api.model
    def _get_method(self):
        """Méthode d'attribution (paramètre système ``odoo_garden.revenue_method``, défaut « prorata »)."""
        value = self.env['ir.config_parameter'].sudo().get_param('odoo_garden.revenue_method', 'prorata')
        return value if value in ('lot', 'prorata') else 'prorata'

    @api.model
    def _get_line_domain(self):
        return [
            ('parent_state', '=', 'posted'),
            ('move_id.move_type', 'in', ('out_invoice', 'out_refund')),
            ('display_type', '=', 'product'),
            ('product_id', '!=', False),
        ]

    @api.model
    def get_attribution(self, crops, method=None):
        """Chiffre d'affaires attribué aux cultures.

        Retourne ``{id de culture: {id de ligne de facture: montant attribué}}`` (une entrée par culture,
        éventuellement vide), en monnaie de la société.
        """
        crops = crops.sudo()
        method = method or self._get_method()
        if method == 'lot':
            return self._attribute_by_lot(crops)
        return self._attribute_prorata(crops)

    @api.model
    def get_extra_entries(self, crops, method=None):
        """Point d'extension des modules passerelles (par exemple ``odoo_garden_pos``).

        Retourne ``{id de culture: [entrée, ...]}`` pour les ventes qui ne passent pas par une ligne de facture
        client comptabilisée. Chaque entrée est un dict : ``key`` (tuple ``(modèle, id)``), ``date``,
        ``document`` (référence affichée), ``is_refund``, ``partner_id``, ``product_id``, ``quantity``,
        ``line_amount`` (montant HT de la ligne) et ``amount`` (montant attribué à la culture). Ici : aucune.
        """
        return {crop.id: [] for crop in crops}

    @api.model
    def get_extra_totals(self, crops, method=None):
        """Version agrégée de ``get_extra_entries`` : ``{id de culture: (montant total, nombre de lignes)}``.

        Les passerelles peuvent la surcharger pour éviter de construire le détail de chaque entrée quand
        seuls les totaux sont utiles (calcul du chiffre d'affaires de milliers de cultures). Une passerelle qui
        surcharge ``get_extra_entries`` doit donc aussi surcharger cette méthode, sans quoi le défaut ci-dessous
        reconstruit les totaux à partir des entrées (correct, mais lent).
        """
        extra = self.get_extra_entries(crops, method)
        return {
            crop_id: (sum(entry['amount'] for entry in entries), len(entries))
            for crop_id, entries in extra.items()
        }

    @api.model
    def get_revenue(self, crops, method=None):
        """Chiffre d'affaires par culture : ``{id de culture: montant}`` (factures et ventes des passerelles)."""
        extra = self.get_extra_totals(crops, method)
        return {
            crop_id: sum(lines.values()) + extra.get(crop_id, (0.0, 0))[0]
            for crop_id, lines in self.get_attribution(crops, method).items()
        }

    # ------------------------------------------------------------------
    # Par lot
    # ------------------------------------------------------------------
    @api.model
    def _attribute_by_lot(self, crops):
        result = {crop.id: {} for crop in crops}
        lot_to_crop = {lot.id: lot.garden_crop_id.id for lot in crops.lot_ids}
        if not lot_to_crop:
            return result
        MoveLine = self.env['stock.move.line'].sudo()
        sale_lines = MoveLine.search([
            ('lot_id', 'in', list(lot_to_crop)), ('state', '=', 'done'), ('move_id.sale_line_id', '!=', False),
        ]).move_id.sale_line_id
        if not sale_lines:
            return result
        totals = defaultdict(float)
        per_crop = defaultdict(lambda: defaultdict(float))
        for line in MoveLine.search([('move_id.sale_line_id', 'in', sale_lines.ids), ('state', '=', 'done')]):
            if line.location_dest_usage == 'customer':
                sign = 1
            elif line.location_usage == 'customer':
                sign = -1  # retour client
            else:
                continue
            sale_line_id = line.move_id.sale_line_id.id
            quantity = sign * line.quantity_product_uom
            totals[sale_line_id] += quantity
            crop_id = lot_to_crop.get(line.lot_id.id)
            if crop_id:
                per_crop[sale_line_id][crop_id] += quantity
        domain = self._get_line_domain()
        for sale_line in sale_lines:
            total = totals[sale_line.id]
            if total <= 0:
                continue
            for invoice_line in sale_line.invoice_lines.filtered_domain(domain):
                for crop_id, quantity in per_crop[sale_line.id].items():
                    if quantity:
                        lines = result[crop_id]
                        lines[invoice_line.id] = lines.get(invoice_line.id, 0.0) - invoice_line.balance * quantity / total
        return result

    # ------------------------------------------------------------------
    # Au prorata des récoltes du mois
    # ------------------------------------------------------------------
    @api.model
    def _get_monthly_harvests(self):
        """Quantités récoltées : ``{(produit, société, année, mois): {id de culture: quantité}}``."""
        groups = self.env['stock.move'].sudo()._read_group(
            [
                ('garden_kind', 'in', ('harvest', 'harvest_return')), ('state', '=', 'done'),
                ('garden_crop_id', '!=', False),
            ],
            ['product_id', 'company_id', 'date:month', 'garden_crop_id', 'garden_kind'],
            ['product_qty:sum'],
        )
        harvests = defaultdict(lambda: defaultdict(float))
        for product, company, month, crop, kind, quantity in groups:
            key = (product.id, company.id, month.year, month.month)
            harvests[key][crop.id] += quantity if kind == 'harvest' else -quantity
        return harvests

    @api.model
    def _attribute_prorata(self, crops):
        result = {crop.id: {} for crop in crops}
        harvests = {
            key: by_crop for key, by_crop in self._get_monthly_harvests().items()
            if any(crop_id in result for crop_id in by_crop)
        }
        if not harvests:
            return result
        products = {key[0] for key in harvests}
        lines = self.env['account.move.line'].sudo().search(
            self._get_line_domain() + [('product_id', 'in', list(products))],
        )
        for line in lines:
            by_crop = harvests.get((line.product_id.id, line.company_id.id, line.date.year, line.date.month))
            if not by_crop:
                continue  # mois sans récolte de ce produit : chiffre d'affaires non attribué
            total = sum(quantity for quantity in by_crop.values() if quantity > 0)
            if total <= 0:
                continue
            for crop_id, quantity in by_crop.items():
                if quantity > 0 and crop_id in result:
                    result[crop_id][line.id] = -line.balance * quantity / total
        return result

    # ------------------------------------------------------------------
    # Données de démonstration
    # ------------------------------------------------------------------
    @api.model
    def _create_demo_lot_sale(self):
        """Démo : commande de tomates livrée sur le lot de la culture, facturée et comptabilisée (méthode par lot)."""
        crop = self.env.ref('odoo_garden.demo_crop_2027_tomato_coeur_s1_01', raise_if_not_found=False)
        partner = self.env.ref('odoo_garden.demo_customer_market', raise_if_not_found=False)
        if not crop or not partner or not crop.lot_ids:
            return
        lot = crop.lot_ids[:1]
        product = lot.product_id
        order = self.env['sale.order'].create({
            'partner_id': partner.id,
            'order_line': [(0, 0, {
                'product_id': product.id, 'product_uom_qty': 6, 'price_unit': 6.0, 'tax_ids': [(5, 0, 0)],
            })],
        })
        order.action_confirm()
        picking = order.picking_ids
        picking.action_assign()
        move = picking.move_ids
        move.move_line_ids.unlink()
        self.env['stock.move.line'].create({
            'move_id': move.id, 'picking_id': picking.id, 'product_id': product.id,
            'product_uom_id': product.uom_id.id, 'quantity': 6, 'lot_id': lot.id,
            'location_id': picking.location_id.id, 'location_dest_id': picking.location_dest_id.id, 'picked': True,
        })
        move.picked = True
        picking.with_context(skip_backorder=True).button_validate()
        invoice = order._create_invoices()
        invoice.invoice_date = '2027-07-28'
        invoice.action_post()
