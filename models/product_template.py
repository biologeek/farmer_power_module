from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    garden_input_type = fields.Selection(
        [
            ('seed', 'Semence'),
            ('plant', 'Plant'),
            ('fertilizer', 'Engrais'),
            ('amendment', 'Amendement'),
            ('phytosanitary', 'Phytosanitaire'),
            ('substrate', 'Substrat'),
            ('other', 'Autre'),
        ],
        string="Type d'intrant maraîcher", index='btree_not_null',
        help="Renseigné pour les produits consommés par les opérations (semences, plants, engrais, "
             "traitements...) : seuls ces produits sont proposés comme intrants d'une opération.",
    )
    garden_variety_ids = fields.Many2many(
        'garden.variety', string='Variétés maraîchères', compute='_compute_garden_variety_ids',
        help="Variétés dont ce produit est la semence ou le produit récolté.",
    )
    is_garden_product = fields.Boolean(
        'Produit maraîcher', compute='_compute_garden_variety_ids', search='_search_is_garden_product',
    )

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
            raise NotImplementedError("Opérateur non supporté : %s" % operator)
        positive = (operator == '=') == bool(value)
        varieties = self.env['garden.variety'].sudo().with_context(active_test=False).search([])
        template_ids = (varieties.seed_product_id | varieties.harvest_product_id).product_tmpl_id.ids
        domain = ['|', ('id', 'in', template_ids), ('garden_input_type', '!=', False)]
        return domain if positive else ['!', *domain]
