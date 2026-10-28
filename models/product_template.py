from odoo import api, fields, models
from odoo.exceptions import ValidationError


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
    amm_number = fields.Char(
        "N° AMM", copy=False,
        help="Numéro d'autorisation de mise sur le marché du produit phytosanitaire (mention obligatoire "
             "du registre phytosanitaire).",
    )
    pre_harvest_interval_days = fields.Integer(
        'Délai avant récolte (jours)',
        help="DAR : nombre de jours à respecter entre le dernier traitement avec ce produit et la récolte. "
             "0 : aucun délai. Une récolte plus proche du traitement est bloquée (levée possible par le gérant).",
    )
    is_organic_allowed = fields.Boolean(
        'Autorisé en agriculture biologique',
        help="Coché si le produit peut être utilisé sur une culture certifiée bio. Les intrants non cochés "
             "utilisés sur une culture bio sont signalés dans l'export de certification.",
    )
    nitrogen_content = fields.Float(
        'Teneur en azote (%)', digits=(5, 2),
        help="Pourcentage d'azote (N) en masse de l'engrais. Sert au registre de fertilisation : "
             "azote apporté = quantité (kg) × teneur / 100.",
    )
    garden_variety_ids = fields.Many2many(
        'garden.variety', string='Variétés maraîchères', compute='_compute_garden_variety_ids',
        help="Variétés dont ce produit est la semence ou le produit récolté.",
    )
    is_garden_product = fields.Boolean(
        'Produit maraîcher', compute='_compute_garden_variety_ids', search='_search_is_garden_product',
    )

    _pre_harvest_interval_positive = models.Constraint(
        'CHECK (pre_harvest_interval_days >= 0)', "Le délai avant récolte ne peut pas être négatif.",
    )

    @api.constrains('nitrogen_content')
    def _check_nitrogen_content(self):
        if any(not 0 <= template.nitrogen_content <= 100 for template in self):
            raise ValidationError(self.env._("La teneur en azote est un pourcentage compris entre 0 et 100."))

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
            and self.env.user.has_group('odoo_garden.group_garden_chef')
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
            raise NotImplementedError("Opérateur non supporté : %s" % operator)
        positive = (operator == '=') == bool(value)
        varieties = self.env['garden.variety'].sudo().with_context(active_test=False).search([])
        template_ids = (varieties.seed_product_id | varieties.harvest_product_id).product_tmpl_id.ids
        domain = ['|', ('id', 'in', template_ids), ('garden_input_type', '!=', False)]
        return domain if positive else ['!', *domain]
