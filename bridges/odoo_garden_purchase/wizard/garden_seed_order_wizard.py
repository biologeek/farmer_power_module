import math
from collections import defaultdict

from odoo import Command, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare, float_round


class GardenSeedOrderWizard(models.TransientModel):
    """Turns the seed (and bought plant) needs of a season into draft requests for quotation.

    Rules:
    - one draft ``purchase.order`` per supplier (``garden.variety.supplier_id``), one line per variety and product;
    - seeds: quantity from ``garden.crop.get_seed_needs`` (grams). A seed product in a weight unit is ordered
      in that unit (converted from grams); a product in the reference "Units" category is ordered in seeds
      (rounded up); any other unit of measure is skipped with a warning;
    - plants: crops whose route is "bought plants" are ordered through the plant product of the route, in plants;
    - varieties without a supplier or without product are skipped and listed as warnings;
    - idempotent: what was already ordered for the same season, variety and product by a previous run
      (lines of non-cancelled orders carrying ``garden_season_id`` and ``garden_variety_id``) is deducted;
      only the missing quantity is ordered.
    Orders are created with ``sudo()`` (the crop manager may have no access to Purchase), and only the
    result message is returned to the user.
    """
    _name = 'garden.seed.order.wizard'
    _description = 'Seed Request for Quotation Wizard'

    season_id = fields.Many2one(
        'garden.season', string='Season', required=True, default=lambda self: self._default_season(),
        help="Season whose seed needs are ordered.",
    )
    include_plants = fields.Boolean(
        'Include Bought Plants', default=True,
        help="Also order the plants of crops whose route is 'bought plants'.",
    )
    preview = fields.Text('Preview', compute='_compute_preview', help="What would be ordered and what is skipped.")
    state = fields.Selection([('draft', 'Draft'), ('done', 'Done')], default='draft', readonly=True)
    result = fields.Text('Result', readonly=True)
    purchase_order_ids = fields.Many2many(
        'purchase.order', string='Requests for Quotation', readonly=True, groups='purchase.group_purchase_user',
    )

    @api.model
    def _default_season(self):
        return self.env['garden.season'].search([('state', '!=', 'closed')], order='date_start desc', limit=1)

    # ------------------------------------------------------------------
    # Needs
    # ------------------------------------------------------------------
    def _get_unit_category_uom(self):
        return self.env.ref('uom.product_uom_unit')

    def _get_product_quantity(self, product, grams, count):
        """Quantity to order in the unit of measure of the seed product, or ``None`` if not possible."""
        uom = product.uom_id
        if uom._has_common_reference(self.env.ref('uom.product_uom_gram')):
            return self.env.ref('uom.product_uom_gram')._compute_quantity(grams, uom, round=False)
        if uom._has_common_reference(self._get_unit_category_uom()):
            return float(count)
        return None

    def _get_requirements(self):
        """Return ``(items, warnings)``.

        Each item is a dict: ``variety``, ``product``, ``supplier``, ``needed`` and ``ordered`` (both in the
        unit of the product), ``to_order`` and ``kind`` ('seed' or 'plant').
        """
        self.ensure_one()
        season = self.season_id
        items, warnings = [], []
        raw = []  # (variety, product, kind, grams, count)
        for need in self.env['garden.crop'].get_seed_needs([('season_id', '=', season.id)]):
            variety = need['variety']
            if need['seeds'] <= 0 and need['grams'] <= 0:
                continue  # only bought plants, or no seed data
            if not variety.seed_product_id:
                warnings.append(self.env._("%s: no seed product on the variety, skipped.", variety.display_name))
                continue
            raw.append((variety, variety.seed_product_id, 'seed', need['grams'], need['seeds']))
        if self.include_plants:
            plants = defaultdict(float)
            crops = self.env['garden.crop'].search([
                ('season_id', '=', season.id), ('state', '!=', 'cancelled'),
                ('template_id.propagation', '=', 'bought_plants'),
            ])
            for crop in crops:
                if not crop.template_id.plant_product_id:
                    warnings.append(self.env._(
                        "%(crop)s: no plant product on the route %(route)s, skipped.",
                        crop=crop.display_name, route=crop.template_id.display_name,
                    ))
                    continue
                plants[(crop.variety_id, crop.template_id.plant_product_id)] += crop.planned_plant_qty
            for (variety, product), quantity in plants.items():
                if quantity > 0:
                    raw.append((variety, product, 'plant', 0.0, math.ceil(quantity - 1e-9)))
        for variety, product, kind, grams, count in raw:
            if not variety.supplier_id:
                warnings.append(self.env._("%s: no supplier on the variety, skipped.", variety.display_name))
                continue
            if kind == 'plant':
                needed = float(count) if product.uom_id._has_common_reference(self._get_unit_category_uom()) else None
            else:
                needed = self._get_product_quantity(product, grams, count)
            if needed is None:
                warnings.append(self.env._(
                    "%(variety)s: the unit of measure %(uom)s of %(product)s is neither a weight nor a unit, skipped.",
                    variety=variety.display_name, uom=product.uom_id.display_name, product=product.display_name,
                ))
                continue
            if needed <= 0:
                warnings.append(self.env._(
                    "%s: quantity cannot be computed (seeds per gram missing?), skipped.", variety.display_name,
                ))
                continue
            needed = float_round(needed, precision_rounding=product.uom_id.rounding, rounding_method='UP')
            ordered = self._get_already_ordered(variety, product)
            to_order = float_round(
                max(needed - ordered, 0.0), precision_rounding=product.uom_id.rounding, rounding_method='UP',
            )
            items.append({
                'variety': variety, 'product': product, 'supplier': variety.supplier_id, 'kind': kind,
                'needed': needed, 'ordered': ordered, 'to_order': to_order,
            })
        return items, warnings

    def _get_already_ordered(self, variety, product):
        """Quantity (unit of the product) already requested for the season, variety and product."""
        lines = self.env['purchase.order.line'].sudo().search([
            ('garden_season_id', '=', self.season_id.id), ('garden_variety_id', '=', variety.id),
            ('product_id', '=', product.id), ('order_id.state', '!=', 'cancel'),
        ])
        return sum(line.product_uom_id._compute_quantity(line.product_qty, product.uom_id) for line in lines)

    @api.depends('season_id', 'include_plants')
    def _compute_preview(self):
        for wizard in self:
            if not wizard.season_id:
                wizard.preview = False
                continue
            items, warnings = wizard._get_requirements()
            rows = []
            for item in items:
                uom = item['product'].uom_id.display_name
                if item['to_order'] > 0:
                    rows.append(self.env._(
                        "%(supplier)s - %(variety)s: %(qty)s %(uom)s (needed %(needed)s, already requested %(ordered)s)",
                        supplier=item['supplier'].display_name, variety=item['variety'].display_name,
                        qty=item['to_order'], uom=uom, needed=item['needed'], ordered=item['ordered'],
                    ))
                else:
                    rows.append(self.env._(
                        "%(supplier)s - %(variety)s: already requested (%(ordered)s %(uom)s)",
                        supplier=item['supplier'].display_name, variety=item['variety'].display_name,
                        ordered=item['ordered'], uom=uom,
                    ))
            rows.extend(self.env._("Warning - %s", warning) for warning in warnings)
            wizard.preview = '\n'.join(rows) or self.env._("Nothing to order for this season.")

    # ------------------------------------------------------------------
    # Creation
    # ------------------------------------------------------------------
    def action_create_rfq(self):
        self.ensure_one()
        if self.state == 'done':
            raise UserError(self.env._("The requests for quotation were already created."))
        items, warnings = self._get_requirements()
        by_supplier = defaultdict(list)
        skipped = []
        for item in items:
            if float_compare(item['to_order'], 0.0, precision_rounding=item['product'].uom_id.rounding) > 0:
                by_supplier[item['supplier']].append(item)
            else:
                skipped.append(item)
        # Purchase access is not required from the crop manager: orders are created in sudo, as that user.
        Order = self.env['purchase.order'].sudo().with_company(self.season_id.company_id)
        orders = Order
        for supplier, supplier_items in by_supplier.items():
            orders |= Order.create({
                'partner_id': supplier.id,
                'company_id': self.season_id.company_id.id,
                'garden_season_id': self.season_id.id,
                'origin': self.season_id.name,
                'order_line': [Command.create({
                    'product_id': item['product'].id,
                    'product_qty': item['to_order'],
                    'product_uom_id': item['product'].uom_id.id,
                    'garden_variety_id': item['variety'].id,
                }) for item in supplier_items],
            })
        lines = [self.env._("%(count)s request(s) for quotation created: %(names)s", count=len(orders), names=', '.join(orders.mapped('name')))]
        lines.extend(self.env._("Already requested, nothing to order: %s", item['variety'].display_name) for item in skipped)
        lines.extend(self.env._("Warning - %s", warning) for warning in warnings)
        vals = {'state': 'done', 'result': '\n'.join(lines)}
        if self.env.user.has_group('purchase.group_purchase_user'):
            vals['purchase_order_ids'] = [Command.set(orders.ids)]
        self.write(vals)
        return {
            'type': 'ir.actions.act_window', 'res_model': self._name, 'res_id': self.id,
            'view_mode': 'form', 'target': 'new',
        }

    def action_view_orders(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('purchase.purchase_rfq')
        action['domain'] = [('id', 'in', self.purchase_order_ids.ids)]
        return action
