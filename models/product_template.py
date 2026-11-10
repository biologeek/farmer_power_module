from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    garden_input_type = fields.Selection(
        [
            ('seed', 'Seed'),
            ('plant', 'Plant'),
            ('fertilizer', 'Fertilizer'),
            ('amendment', 'Soil Amendment'),
            ('phytosanitary', 'Plant Protection'),
            ('substrate', 'Growing Medium'),
            ('other', 'Other'),
        ],
        string='Market Gardening Input Type', index='btree_not_null',
        help='Set for products consumed by operations (seeds, plants, fertilizers, treatments...): only these '
             'products are suggested as operation inputs.',
    )
    amm_number = fields.Char(
        'MA No.', copy=False,
        help='Marketing authorization number of the plant protection product (mandatory entry of the plant '
             'protection register).',
    )
    pre_harvest_interval_days = fields.Integer(
        'Pre-Harvest Interval (days)',
        help='PHI: number of days to respect between the last treatment with this product and the harvest. 0: '
             'no interval. A harvest closer to the treatment is blocked (can be waived by the manager).',
    )
    is_organic_allowed = fields.Boolean(
        'Allowed in organic farming',
        help='Ticked if the product can be used on an organic-certified crop. Non-ticked inputs used on an '
             'organic crop are flagged in the certification export.',
    )
    nitrogen_content = fields.Float(
        'Nitrogen Content (%)', digits=(5, 2),
        help='Percentage of nitrogen (N) by mass of the fertilizer. Used for the fertilization register: '
             'nitrogen applied = quantity (kg) × content / 100.',
    )
    garden_variety_ids = fields.Many2many(
        'garden.variety', string='Market Gardening Varieties', compute='_compute_garden_variety_ids',
        help='Varieties whose seed or harvested product is this product.',
    )
    is_garden_product = fields.Boolean(
        'Market Gardening Product', compute='_compute_garden_variety_ids', search='_search_is_garden_product',
    )

    _pre_harvest_interval_positive = models.Constraint(
        'CHECK (pre_harvest_interval_days >= 0)', 'The pre-harvest interval cannot be negative.',
    )

    @api.constrains('nitrogen_content')
    def _check_nitrogen_content(self):
        if any(not 0 <= template.nitrogen_content <= 100 for template in self):
            raise ValidationError(self.env._('The nitrogen content is a percentage between 0 and 100.'))

    # Champs réglementaires : le chef de culture et le gérant les modifient sans disposer des droits
    # d'écriture sur les produits (Ventes, Inventaire). Une écriture qui ne touche que ces champs est
    # exécutée en sudo ; toute autre modification suit les droits habituels.
    _GARDEN_FIELDS = {
        'garden_input_type', 'amm_number', 'pre_harvest_interval_days', 'is_organic_allowed', 'nitrogen_content',
    }

    def write(self, vals):
        if (
            vals and self._GARDEN_FIELDS.issuperset(vals)
            and not self.env.su
            and self.env.user.has_group('farmer_power.group_garden_chef')
            and not self.has_access('write')
        ):
            self = self.sudo()
        return super().write(vals)

    @api.depends('garden_input_type')
    def _compute_garden_variety_ids(self):
        varieties = self.env['garden.variety'].sudo().with_context(active_test=False).search([
            '|',
            ('seed_product_id.product_tmpl_id', 'in', self.ids),
            ('harvest_product_id.product_tmpl_id', 'in', self.ids),
        ])
        by_template = {}
        for variety in varieties:
            for product in variety.seed_product_id | variety.harvest_product_id:
                by_template.setdefault(product.product_tmpl_id.id, set()).add(variety.id)
        for template in self:
            ids = by_template.get(template.id, ())
            template.garden_variety_ids = [(6, 0, list(ids))]
            template.is_garden_product = bool(ids) or bool(template.garden_input_type)

    def _search_is_garden_product(self, operator, value):
        if operator not in ('=', '!='):
            raise NotImplementedError("Unsupported operator: %s" % operator)
        positive = (operator == '=') == bool(value)
        varieties = self.env['garden.variety'].sudo().with_context(active_test=False).search([])
        template_ids = (varieties.seed_product_id | varieties.harvest_product_id).product_tmpl_id.ids
        domain = ['|', ('id', 'in', template_ids), ('garden_input_type', '!=', False)]
        return domain if positive else ['!', *domain]
