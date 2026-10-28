import re
import unicodedata
import math
from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models


class GardenCrop(models.Model):
    _name = 'garden.crop'
    _description = 'Culture sur planche'
    # Culture d'une variété sur (une part d') une planche pendant une saison : porte le plan (dates
    # prévues, surface, prévisionnel, besoins en semences, avertissements) et l'état d'avancement.
    # Le réalisé calculé (heures, marge...) arrivera aux phases 3 à 5.
    _inherit = ['mail.thread']
    _order = 'planned_sowing_date, id'
    _rec_names_search = ['name', 'template_id']

    name = fields.Char(
        'Référence', default='/', copy=False, readonly=True, index=True,
        help="Générée à la création : initiale de l'espèce, année, code de la planche et numéro d'ordre "
             "(ex. T-2027-P12-01). Servira de nom de lot de traçabilité.",
    )
    season_id = fields.Many2one(
        'garden.season', string='Saison', index=True, ondelete='restrict', tracking=True,
        help="Plan de culture annuel auquel appartient la culture.",
    )
    template_id = fields.Many2one(
        'garden.crop.template', string='Itinéraire technique', required=True, index=True, tracking=True,
        help="Itinéraire qui fournit la variété, la densité, les délais et le rendement attendus.",
    )
    variety_id = fields.Many2one(
        'garden.variety', string='Variété', related='template_id.variety_id', store=True, index=True,
    )
    species_id = fields.Many2one(
        'garden.species', string='Espèce', related='template_id.species_id', store=True, index=True,
    )
    family = fields.Selection(related='species_id.family', string='Famille botanique', store=True)
    bed_id = fields.Many2one(
        'garden.bed', string='Planche', required=True, index=True, tracking=True,
        help="Planche sur laquelle la culture est installée.",
    )
    bed_area = fields.Float('Surface de la planche (m²)', related='bed_id.area', help="Surface totale de la planche.")
    bed_share = fields.Float(
        'Part de la planche (%)', default=100.0, tracking=True,
        help="Part de la planche occupée par cette culture (100 = toute la planche).",
    )
    area = fields.Float(
        'Surface occupée (m²)', compute='_compute_area', store=True,
        help="Surface de la planche × part occupée.",
    )
    company_id = fields.Many2one(
        'res.company', string='Société', related='bed_id.company_id', store=True, index=True,
    )
    state = fields.Selection(
        [
            ('planned', 'Planifiée'),
            ('sown', 'Semée'),
            ('in_place', 'En place'),
            ('harvesting', 'En récolte'),
            ('done', 'Terminée'),
            ('cancelled', 'Annulée'),
        ],
        string='État', required=True, default='planned', copy=False, tracking=True, index=True,
        help="Avancement : planifiée, semée, en place, en récolte, terminée ou annulée. "
             "Une culture annulée n'est plus prise en compte dans les contrôles ni les besoins en semences.",
    )

    # Dates prévues
    planned_sowing_date = fields.Date(
        'Semis prévu', tracking=True,
        help="Date de semis visée. La modifier recalcule repiquage, début et fin de récolte.",
    )
    planned_transplant_date = fields.Date(
        'Repiquage prévu', help="Date de mise en place des plants en planche (semis direct : vide).",
    )
    planned_harvest_start = fields.Date(
        'Début de récolte prévu', tracking=True,
        help="Date de première récolte visée. La modifier recalcule le semis (rétro-planning).",
    )
    planned_harvest_end = fields.Date(
        'Fin de récolte prévue', help="Fin de la fenêtre de récolte (début de récolte + fenêtre de l'itinéraire).",
    )
    # Dates réelles (alimentées par les opérations réalisées à partir de la phase 3)
    date_start = fields.Date('Début réel', help="Date réelle du premier semis ou de la mise en place.")
    date_end = fields.Date('Fin réelle', help="Date réelle de fin de la culture (planche libérée).")
    occupation_start = fields.Date(
        'Début d\'occupation', compute='_compute_occupation', store=True,
        help="Date d'arrivée en planche : repiquage prévu pour les plants, sinon début réel ou semis prévu.",
    )
    occupation_end = fields.Date(
        'Fin d\'occupation', compute='_compute_occupation', store=True,
        help="Fin réelle, à défaut fin de récolte prévue.",
    )

    # Prévisionnel
    planned_plant_qty = fields.Float(
        'Plants prévus', compute='_compute_forecast', store=True, readonly=False,
        help="Surface occupée × densité de l'itinéraire.",
    )
    expected_yield_qty = fields.Float(
        'Récolte attendue (kg)', compute='_compute_forecast', store=True, readonly=False,
        help="Surface occupée × rendement attendu de l'itinéraire.",
    )
    expected_revenue = fields.Float(
        'Chiffre d\'affaires attendu', compute='_compute_forecast', store=True, readonly=False,
        help="Récolte attendue × prix de vente attendu.",
    )
    planned_seed_count = fields.Integer(
        'Graines à semer', compute='_compute_seed_needs', store=True,
        help="Plants prévus / taux de germination × (1 + marge de semis). Nul pour des plants achetés.",
    )
    planned_seed_qty = fields.Float(
        'Semences prévues (g)', compute='_compute_seed_needs', store=True, digits=(16, 2),
        help="Graines à semer / nombre de graines par gramme de la variété.",
    )

    # Avertissements (jamais bloquants)
    overlap_share = fields.Float(
        'Occupation maximale (%)', compute='_compute_warnings',
        help="Somme maximale des parts de planche occupées simultanément, cette culture comprise.",
    )
    has_overlap = fields.Boolean(
        'Chevauchement', compute='_compute_warnings',
        help="Vrai si la planche est occupée à plus de 100 % pendant la période de la culture.",
    )
    overlap_warning = fields.Text(
        'Avertissement de chevauchement', compute='_compute_warnings',
        help="Détail du chevauchement avec les autres cultures de la planche.",
    )
    has_rotation_conflict = fields.Boolean(
        'Rotation non respectée', compute='_compute_warnings',
        help="Vrai si la même famille botanique a été cultivée sur la planche depuis moins que le délai de rotation.",
    )
    rotation_warning = fields.Text(
        'Avertissement de rotation', compute='_compute_warnings',
        help="Détail des cultures précédentes de la même famille sur la planche.",
    )

    sowing_quantity = fields.Float('Nombre de plants semés', help="Nombre de plants effectivement semés.")
    planted_quantity = fields.Float('Nombre de plants plantés', help="Nombre de plants effectivement plantés.")
    notes = fields.Text('Notes', help="Observations libres sur la culture.")
    harvest_move_ids = fields.One2many(
        'stock.move', 'garden_crop_id', string='Mouvements de récolte', readonly=True,
        domain=[('garden_kind', 'in', ('harvest', 'harvest_return'))], groups='odoo_garden.group_garden_chef',
        help="Entrées en stock créées par les opérations de récolte, et leurs annulations.",
    )
    harvested_qty = fields.Float(
        'Quantité récoltée (kg)', compute='_compute_harvested_qty', store=True, digits='Product Unit',
        help="Somme des mouvements de stock de récolte terminés (annulations déduites), dans l'unité du "
             "produit récolté (supposée être le kg). Source de vérité des statistiques de production.",
    )
    loss_ids = fields.One2many('garden.loss', 'crop_id', string='Pertes', help="Pertes déclarées sur la culture.")
    loss_count = fields.Integer('Nombre de pertes', compute='_compute_loss_count')
    loss_qty = fields.Float(
        'Quantité perdue', compute='_compute_loss_rate', store=True, digits='Product Unit',
        help="Somme des pertes de la culture (avant et après récolte), dans l'unité du produit récolté.",
    )
    loss_rate = fields.Float(
        'Taux de perte', compute='_compute_loss_rate', store=True, digits=(16, 4),
        help="Pertes / (récolte + pertes). Les pertes et la récolte sont supposées dans la même unité (kg).",
    )
    lot_ids = fields.One2many(
        'stock.lot', 'garden_crop_id', string='Lots de récolte', readonly=True,
        help="Lots de stock créés par les récoltes de la culture (nommés d'après sa référence).",
    )
    lot_count = fields.Integer('Nombre de lots', compute='_compute_lot_count')
    allocation_ids = fields.One2many(
        'garden.operation.allocation', 'crop_id', string='Travail réparti',
        help="Part des opérations faites (sur cette culture, des planches ou un îlot) attribuée à la culture.",
    )
    labour_hours = fields.Float(
        'Heures de travail', compute='_compute_labour', store=True,
        help="Somme des heures réparties sur la culture par les opérations faites.",
    )
    labour_cost = fields.Float(
        'Coût main-d\'œuvre', compute='_compute_labour', store=True, digits='Product Price',
        groups='odoo_garden.group_garden_chef',
        help="Somme du coût de main-d'œuvre réparti sur la culture par les opérations faites.",
    )
    input_cost = fields.Float(
        'Coût des intrants', compute='_compute_labour', store=True, digits='Product Price',
        groups='odoo_garden.group_garden_chef',
        help="Somme du coût des intrants réparti sur la culture par les opérations faites.",
    )
    expected_hours = fields.Float(
        'Heures attendues', compute='_compute_expected_hours', store=True,
        help="Somme des durées attendues (h/m²) des étapes de l'itinéraire × surface occupée.",
    )
    occupation_days = fields.Integer(
        "Jours d'occupation", compute='_compute_occupation_days', store=True,
        help="Nombre de jours entre le début et la fin d'occupation (bornes comprises) ; sert aux charges fixes.",
    )

    # Rentabilité (phase 5). Champs non stockés : le chiffre d'affaires vient des factures clients
    # (autre modèle, modifiable à tout moment), il est donc recalculé à chaque lecture. Le rapport
    # `garden.crop.profitability` en garde une copie, actualisée à la demande et chaque nuit. Les calculs
    # tournent en ``sudo`` (comptabilité inaccessible au chef de culture), mais la lecture reste réservée
    # au chef de culture et au gérant.
    revenue = fields.Float(
        "Chiffre d'affaires", compute='_compute_revenue', digits='Product Price', compute_sudo=True,
        groups='odoo_garden.group_garden_chef',
        help="Montant HT des factures clients comptabilisées attribué à la culture, selon la méthode choisie "
             "dans les paramètres (par lot ou au prorata des récoltes du mois).",
    )
    sale_line_count = fields.Integer(
        'Lignes de vente', compute='_compute_revenue', compute_sudo=True, groups='odoo_garden.group_garden_chef',
        help="Nombre de lignes de factures clients attribuées (en tout ou partie) à la culture.",
    )
    fixed_cost = fields.Float(
        'Charges fixes', compute='_compute_margin', digits='Product Price', compute_sudo=True,
        groups='odoo_garden.group_garden_chef',
        help="Option : coût annuel par m² (paramètres) × surface × jours d'occupation / 365. Nul si le coût "
             "par m² est à zéro.",
    )
    margin = fields.Float(
        'Marge', compute='_compute_margin', digits='Product Price', compute_sudo=True,
        groups='odoo_garden.group_garden_chef',
        help="Chiffre d'affaires - coût de main-d'œuvre - coût des intrants - charges fixes.",
    )
    margin_per_hour = fields.Float(
        'Marge par heure', compute='_compute_margin', digits='Product Price', compute_sudo=True,
        groups='odoo_garden.group_garden_chef', help="Marge / heures de travail (0 sans heures).",
    )
    margin_per_m2 = fields.Float(
        'Marge par m²', compute='_compute_margin', digits='Product Price', compute_sudo=True,
        groups='odoo_garden.group_garden_chef', help="Marge / surface occupée (0 sans surface).",
    )
    yield_gap = fields.Float(
        'Écart de récolte (kg)', compute='_compute_gaps', digits='Product Unit',
        help="Quantité récoltée - récolte attendue.",
    )
    hours_gap = fields.Float(
        'Écart d\'heures', compute='_compute_gaps', help="Heures de travail - heures attendues.",
    )
    revenue_gap = fields.Float(
        "Écart de chiffre d'affaires", compute='_compute_revenue_gap', digits='Product Price', compute_sudo=True,
        groups='odoo_garden.group_garden_chef', help="Chiffre d'affaires - chiffre d'affaires attendu.",
    )
    operation_count = fields.Integer(
        'Nombre d\'opérations', compute='_compute_operation_count',
        help="Opérations qui visent la culture ou qui lui sont réparties (planche, îlot).",
    )
    operation_ids = fields.Many2many(
        'garden.operation', 'garden_operation_crop_rel', 'crop_id', 'operation_id', string='Opérations',
        help="Opérations dont la cible est directement cette culture (périmètre « Culture »).",
    )

    _bed_share_range = models.Constraint(
        'CHECK (bed_share > 0 AND bed_share <= 100)',
        'La part de la planche doit être comprise entre 0 (exclu) et 100 %.',
    )

    @api.depends('name', 'template_id.name')
    def _compute_display_name(self):
        for crop in self:
            crop.display_name = "%s - %s" % (crop.name, crop.template_id.name) if crop.template_id else crop.name

    @api.depends('bed_id.area', 'bed_share')
    def _compute_area(self):
        for crop in self:
            crop.area = crop.bed_id.area * crop.bed_share / 100.0

    @api.depends(
        'date_start', 'date_end', 'planned_sowing_date', 'planned_transplant_date',
        'planned_harvest_start', 'planned_harvest_end', 'template_id.propagation',
    )
    def _compute_occupation(self):
        for crop in self:
            nursery = crop.template_id.propagation != 'direct_sowing'
            crop.occupation_start = (
                (nursery and crop.planned_transplant_date)
                or crop.date_start or crop.planned_sowing_date or crop.planned_transplant_date
            )
            crop.occupation_end = crop.date_end or crop.planned_harvest_end or crop.planned_harvest_start

    @api.depends('area', 'template_id.step_ids.expected_duration')
    def _compute_expected_hours(self):
        for crop in self:
            crop.expected_hours = crop.area * sum(crop.template_id.step_ids.mapped('expected_duration'))

    @api.depends('occupation_start', 'occupation_end')
    def _compute_occupation_days(self):
        for crop in self:
            if crop.occupation_start and crop.occupation_end:
                crop.occupation_days = max((crop.occupation_end - crop.occupation_start).days + 1, 0)
            else:
                crop.occupation_days = 0

    @api.model
    def _get_fixed_cost_per_m2(self):
        """Charges fixes annuelles par m² (paramètre système ``odoo_garden.fixed_cost_per_m2``, défaut 0)."""
        value = self.env['ir.config_parameter'].sudo().get_param('odoo_garden.fixed_cost_per_m2', '0')
        try:
            return max(float(value), 0.0)
        except ValueError:
            return 0.0

    @api.depends('harvested_qty', 'lot_ids')
    def _compute_revenue(self):
        attribution = self.env['garden.revenue'].get_attribution(self)
        for crop in self:
            lines = attribution.get(crop.id, {})
            crop.revenue = sum(lines.values())
            crop.sale_line_count = len(lines)

    @api.depends('revenue', 'labour_cost', 'input_cost', 'labour_hours', 'area', 'occupation_days')
    def _compute_margin(self):
        rate = self._get_fixed_cost_per_m2()
        for crop in self:
            crop.fixed_cost = rate * crop.area * crop.occupation_days / 365.0 if rate > 0 else 0.0
            crop.margin = crop.revenue - crop.labour_cost - crop.input_cost - crop.fixed_cost
            crop.margin_per_hour = crop.margin / crop.labour_hours if crop.labour_hours > 0 else 0.0
            crop.margin_per_m2 = crop.margin / crop.area if crop.area > 0 else 0.0

    @api.depends('harvested_qty', 'expected_yield_qty', 'labour_hours', 'expected_hours')
    def _compute_gaps(self):
        for crop in self:
            crop.yield_gap = crop.harvested_qty - crop.expected_yield_qty
            crop.hours_gap = crop.labour_hours - crop.expected_hours

    @api.depends('revenue', 'expected_revenue')
    def _compute_revenue_gap(self):
        for crop in self:
            crop.revenue_gap = crop.revenue - crop.expected_revenue

    @api.depends('allocation_ids.hours', 'allocation_ids.labour_cost', 'allocation_ids.input_cost')
    def _compute_labour(self):
        for crop in self:
            crop.labour_hours = sum(crop.allocation_ids.mapped('hours'))
            crop.labour_cost = sum(crop.allocation_ids.mapped('labour_cost'))
            crop.input_cost = sum(crop.allocation_ids.mapped('input_cost'))

    @api.depends('harvest_move_ids.state', 'harvest_move_ids.product_qty', 'harvest_move_ids.garden_kind')
    def _compute_harvested_qty(self):
        for crop in self:
            moves = crop.harvest_move_ids.filtered(lambda m: m.state == 'done')
            crop.harvested_qty = sum(
                m.product_qty if m.garden_kind == 'harvest' else -m.product_qty for m in moves
            )

    @api.depends('loss_ids.quantity_ref', 'harvested_qty')
    def _compute_loss_rate(self):
        for crop in self:
            lost = sum(crop.loss_ids.mapped('quantity_ref'))
            total = crop.harvested_qty + lost
            crop.loss_qty = lost
            crop.loss_rate = lost / total if total > 0 else 0.0

    @api.depends('loss_ids')
    def _compute_loss_count(self):
        counts = dict(self.env['garden.loss']._read_group(
            [('crop_id', 'in', self.ids)], ['crop_id'], ['__count'],
        ))
        for crop in self:
            crop.loss_count = counts.get(crop, 0)

    def action_view_losses(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('odoo_garden.action_garden_loss')
        action['domain'] = [('crop_id', '=', self.id)]
        action['context'] = {'default_crop_id': self.id}
        return action

    @api.depends('lot_ids')
    def _compute_lot_count(self):
        counts = dict(self.env['stock.lot']._read_group(
            [('garden_crop_id', 'in', self.ids)], ['garden_crop_id'], ['__count'],
        ))
        for crop in self:
            crop.lot_count = counts.get(crop, 0)

    def action_view_harvests(self):
        """Lignes de mouvement de stock des récoltes de la culture."""
        self.ensure_one()
        moves = self.env['stock.move'].sudo().search([
            ('garden_crop_id', '=', self.id), ('garden_kind', 'in', ('harvest', 'harvest_return')),
        ])
        action = self.env['ir.actions.act_window']._for_xml_id('stock.stock_move_line_action')
        action['domain'] = [('move_id', 'in', moves.ids)]
        action['context'] = {}
        action['name'] = self.env._("Récoltes : %s", self.name)
        return action

    def action_garden_traceability(self):
        """Bouton « Traçabilité » de la culture : amont (opérations, intrants, semences) et aval (sorties)."""
        self.ensure_one()
        return self.env['garden.traceability']._open(crop=self)

    def action_view_lots(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('stock.action_production_lot_form')
        action['domain'] = [('garden_crop_id', '=', self.id)]
        action['context'] = {'default_garden_crop_id': self.id, 'create': False}
        action['name'] = self.env._("Lots : %s", self.name)
        return action

    def _get_operations_domain(self):
        self.ensure_one()
        return ['|', ('crop_ids', 'in', self.ids), ('allocation_ids.crop_id', 'in', self.ids)]

    def _compute_operation_count(self):
        for crop in self:
            crop.operation_count = self.env['garden.operation'].search_count(crop._get_operations_domain())

    def action_view_operations(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('odoo_garden.action_garden_operation')
        action['domain'] = self._get_operations_domain()
        action['context'] = {'default_scope': 'crop', 'default_crop_ids': [(6, 0, self.ids)]}
        return action

    def action_new_operation(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._("Nouvelle opération"),
            'res_model': 'garden.operation',
            'view_mode': 'form',
            'target': 'current',
            'context': {'default_scope': 'crop', 'default_crop_ids': [(6, 0, self.ids)]},
        }

    @api.depends('area', 'template_id.density', 'template_id.expected_yield', 'template_id.expected_price')
    def _compute_forecast(self):
        for crop in self:
            template = crop.template_id
            crop.planned_plant_qty = crop.area * template.density
            crop.expected_yield_qty = crop.area * template.expected_yield
            crop.expected_revenue = crop.expected_yield_qty * template.expected_price

    @api.model
    def _get_seed_margin(self):
        """Marge de semis en pourcentage (paramètre système ``odoo_garden.seed_margin``, défaut 20)."""
        value = self.env['ir.config_parameter'].sudo().get_param('odoo_garden.seed_margin', '20')
        try:
            return float(value)
        except ValueError:
            return 20.0

    @api.depends(
        'planned_plant_qty', 'template_id.propagation',
        'variety_id.germination_rate', 'variety_id.seeds_per_gram',
    )
    def _compute_seed_needs(self):
        margin = self._get_seed_margin()
        for crop in self:
            variety = crop.variety_id
            germination = variety.germination_rate / 100.0
            if crop.template_id.propagation == 'bought_plants' or germination <= 0:
                crop.planned_seed_count = 0
                crop.planned_seed_qty = 0.0
                continue
            seeds = crop.planned_plant_qty / germination * (1 + margin / 100.0)
            crop.planned_seed_count = math.ceil(seeds - 1e-9)
            crop.planned_seed_qty = seeds / variety.seeds_per_gram if variety.seeds_per_gram > 0 else 0.0

    def _recompute_seed_needs(self):
        for fname in ('planned_seed_count', 'planned_seed_qty'):
            self.env.add_to_compute(self._fields[fname], self)

    @api.model
    def get_seed_needs(self, domain=None):
        """Besoins en semences par variété (cultures non annulées du domaine).

        Retourne une liste de dicts triés par variété : ``variety``, ``area`` (m²), ``plants``,
        ``seeds`` (graines à semer) et ``grams`` (semences en g).
        """
        groups = self._read_group(
            (domain or []) + [('state', '!=', 'cancelled')], ['variety_id'],
            ['area:sum', 'planned_plant_qty:sum', 'planned_seed_count:sum', 'planned_seed_qty:sum'],
        )
        result = [
            {'variety': variety, 'area': area, 'plants': plants, 'seeds': seeds, 'grams': grams}
            for variety, area, plants, seeds, grams in groups
        ]
        return sorted(result, key=lambda line: line['variety'].display_name or '')

    # ------------------------------------------------------------------
    # Avancement piloté par les opérations faites
    # ------------------------------------------------------------------
    # Quand une opération passe à « faite », la culture avance : le premier semis la passe en « semée »,
    # la plantation ou le repiquage en « en place », la première récolte en « en récolte ». L'état ne
    # recule jamais (rouvrir une opération ne défait rien) et une culture terminée ou annulée n'est pas
    # touchée. Le début réel (``date_start``) est la date du premier semis, repiquage ou plantation fait,
    # renseigné seulement s'il est vide (une saisie manuelle n'est jamais écrasée). La fin réelle
    # (``date_end``) n'est pas modifiée par les récoltes, la culture occupant la planche jusqu'à sa fin :
    # elle est renseignée quand la culture passe à « terminée » (date de la dernière récolte faite, à défaut
    # le jour même), si elle est vide.
    _PROGRESS_STATE_BY_CATEGORY = {
        'sowing': 'sown', 'transplanting': 'in_place', 'planting': 'in_place', 'harvest': 'harvesting',
    }
    _PROGRESS_RANK = {'planned': 0, 'sown': 1, 'in_place': 2, 'harvesting': 3, 'done': 4}
    _START_CATEGORIES = ('sowing', 'transplanting', 'planting')

    def _update_progress(self):
        """Fait avancer l'état et le début réel des cultures d'après leurs opérations faites (jamais en arrière)."""
        Allocation = self.env['garden.operation.allocation'].sudo()
        for crop in self.sudo().filtered(lambda c: c.state not in ('done', 'cancelled')):
            allocations = Allocation.search([
                ('crop_id', '=', crop.id), ('category', 'in', list(self._PROGRESS_STATE_BY_CATEGORY)),
            ])
            if not allocations:
                continue
            vals = {}
            target = max(
                (self._PROGRESS_STATE_BY_CATEGORY[a.category] for a in allocations),
                key=self._PROGRESS_RANK.get,
            )
            if self._PROGRESS_RANK[target] > self._PROGRESS_RANK[crop.state]:
                vals['state'] = target
            start_dates = [a.date for a in allocations if a.category in self._START_CATEGORIES and a.date]
            if start_dates and not crop.date_start:
                vals['date_start'] = min(start_dates)
            if vals:
                crop.write(vals)

    def _get_last_harvest_date(self):
        self.ensure_one()
        allocations = self.env['garden.operation.allocation'].sudo().search([
            ('crop_id', '=', self.id), ('category', '=', 'harvest'), ('date', '!=', False),
        ], order='date desc', limit=1)
        return allocations.date

    # ------------------------------------------------------------------
    # Contrôles : chevauchement et rotation
    # ------------------------------------------------------------------
    def _get_bed_neighbours(self):
        """Autres cultures (non annulées) de la même planche, avec une période d'occupation."""
        self.ensure_one()
        origin_id = self._origin.id
        return self.bed_id.crop_ids.filtered(
            lambda c: c.id != origin_id and c.state != 'cancelled' and c.occupation_start
        )

    def _get_overlap_info(self):
        """Retourne ``(part maximale occupée en %, cultures concurrentes)``.

        Deux cultures se chevauchent si leurs périodes d'occupation se recoupent. La part est
        évaluée à chaque début de période (cette culture comprise), pour ne pas additionner des
        cultures concurrentes qui ne sont jamais présentes en même temps.
        """
        self.ensure_one()
        start = self.occupation_start
        end = self.occupation_end or start
        rivals = self._get_bed_neighbours().filtered(
            lambda c: c.occupation_start <= end and (c.occupation_end or c.occupation_start) >= start
        )
        checkpoints = {start} | {c.occupation_start for c in rivals if c.occupation_start > start}
        peak = max(
            self.bed_share + sum(
                c.bed_share for c in rivals
                if c.occupation_start <= day <= (c.occupation_end or c.occupation_start)
            )
            for day in checkpoints
        )
        return peak, rivals

    def _get_rotation_conflicts(self):
        """Cultures antérieures de la même famille botanique sur la planche, revenues trop tôt.

        Le délai est ``rotation_years`` de l'espèce de cette culture, compté entre la fin de
        l'occupation précédente et le début de celle-ci. La famille « Autre » n'est pas contrôlée.
        """
        self.ensure_one()
        years = self.species_id.rotation_years
        if not years or not self.family or self.family == 'other':
            return self.browse()
        limit = self.occupation_start - relativedelta(years=years)
        return self._get_bed_neighbours().filtered(
            lambda c: c.family == self.family and c.occupation_start < self.occupation_start
            and (c.occupation_end or c.occupation_start) > limit
        )

    @api.depends(
        'bed_id', 'bed_share', 'state', 'occupation_start', 'occupation_end', 'species_id.rotation_years', 'family',
        'bed_id.crop_ids.occupation_start', 'bed_id.crop_ids.occupation_end', 'bed_id.crop_ids.bed_share',
        'bed_id.crop_ids.state', 'bed_id.crop_ids.family',
    )
    def _compute_warnings(self):
        for crop in self:
            crop.overlap_share = 0.0
            crop.has_overlap = crop.has_rotation_conflict = False
            crop.overlap_warning = crop.rotation_warning = False
            if not crop.bed_id or crop.state == 'cancelled' or not crop.occupation_start:
                continue
            peak, rivals = crop._get_overlap_info()
            if rivals and peak > 100.0 + 1e-6:
                crop.overlap_share = peak
                crop.has_overlap = True
                crop.overlap_warning = self.env._(
                    "Chevauchement sur la planche %(bed)s : %(share).0f %% de la planche occupés en même temps "
                    "(avec %(crops)s).",
                    bed=crop.bed_id.display_name, share=peak, crops=", ".join(rivals.mapped('name')),
                )
            conflicts = crop._get_rotation_conflicts()
            if conflicts:
                crop.has_rotation_conflict = True
                crop.rotation_warning = self.env._(
                    "Rotation : la famille %(family)s a déjà été cultivée sur cette planche moins de "
                    "%(years)s an(s) avant (%(crops)s).",
                    family=dict(crop.species_id._fields['family'].selection).get(crop.family),
                    years=crop.species_id.rotation_years, crops=", ".join(conflicts.mapped('name')),
                )

    # ------------------------------------------------------------------
    # Rétro-planning
    # ------------------------------------------------------------------
    # UX : saisir (ou modifier) le semis prévu recalcule repiquage, début et fin de récolte ;
    # saisir (ou modifier) le début de récolte visé recalcule le semis et les autres dates.
    # Le repiquage et la fin de récolte restent libres (ajustement manuel sans cascade).
    # Changer d'itinéraire recalcule à partir du semis s'il est saisi, sinon de la récolte.
    # Les boutons « Recalculer depuis le semis / la récolte » appliquent la même logique.
    def _plan_from_sowing(self):
        for crop in self:
            if crop.planned_sowing_date:
                crop.update(crop.template_id._plan_dates(sowing_date=crop.planned_sowing_date))

    def _plan_from_harvest(self):
        for crop in self:
            if crop.planned_harvest_start:
                crop.update(crop.template_id._plan_dates(harvest_start=crop.planned_harvest_start))

    def action_plan_from_sowing(self):
        self._plan_from_sowing()

    def action_plan_from_harvest(self):
        self._plan_from_harvest()

    @api.onchange('planned_sowing_date')
    def _onchange_planned_sowing_date(self):
        self._plan_from_sowing()

    @api.onchange('planned_harvest_start')
    def _onchange_planned_harvest_start(self):
        self._plan_from_harvest()

    @api.onchange('template_id')
    def _onchange_template_id_dates(self):
        if self.planned_sowing_date:
            self._plan_from_sowing()
        else:
            self._plan_from_harvest()

    @api.model
    def _complete_planned_dates(self, vals):
        """Complète à la création les dates prévues manquantes depuis le semis ou la récolte fournis."""
        template = self.env['garden.crop.template'].browse(vals.get('template_id'))
        if template and (vals.get('planned_sowing_date') or vals.get('planned_harvest_start')):
            computed = template._plan_dates(vals.get('planned_sowing_date'), vals.get('planned_harvest_start'))
            for key, value in computed.items():
                vals.setdefault(key, value)
        return vals

    # ------------------------------------------------------------------
    # Étapes prévues de l'itinéraire
    # ------------------------------------------------------------------
    def _get_planned_steps(self):
        """Étapes planifiées de la culture, d'après l'itinéraire et le semis prévu.

        Retourne une liste de dicts triés par date : ``step`` (étape d'itinéraire),
        ``operation_type`` (``garden.operation.type``), ``date`` (semis prévu + ``day_offset``) et
        ``duration`` (heures : durée attendue par m² × surface occupée). Voir
        ``_generate_operations`` pour la création des ``garden.operation`` correspondantes.
        """
        self.ensure_one()
        if not self.planned_sowing_date:
            return []
        steps = [
            {
                'step': step,
                'operation_type': step.operation_type_id,
                'date': self.planned_sowing_date + timedelta(days=step.day_offset),
                'duration': step.expected_duration * self.area,
            }
            for step in self.template_id.step_ids
        ]
        return sorted(steps, key=lambda s: (s['date'], s['step'].sequence, s['step'].id))

    def _generate_operations(self):
        """Crée une opération planifiée par étape de l'itinéraire (``_get_planned_steps``).

        Idempotent : une étape déjà générée pour la culture (même annulée ou faite) n'est pas recréée.
        Les cultures terminées, annulées ou sans semis prévu sont ignorées. Retourne les opérations créées.
        """
        Operation = self.env['garden.operation']
        vals_list = []
        for crop in self.filtered(lambda c: c.state not in ('done', 'cancelled') and c.planned_sowing_date):
            done_steps = Operation.search([
                ('crop_ids', 'in', crop.id), ('template_step_id', '!=', False),
            ]).template_step_id
            for planned in crop._get_planned_steps():
                if planned['step'] in done_steps:
                    continue
                vals_list.append({
                    'type_id': planned['operation_type'].id,
                    'scope': 'crop',
                    'crop_ids': [(6, 0, crop.ids)],
                    'planned_date': planned['date'],
                    'duration': planned['duration'],
                    'company_id': crop.company_id.id,
                    'template_step_id': planned['step'].id,
                })
        return Operation.create(vals_list)

    def action_generate_operations(self):
        """Bouton « Générer les opérations » : crée les opérations manquantes puis les affiche."""
        self._generate_operations()
        if len(self) == 1:
            return self.action_view_operations()
        action = self.env['ir.actions.act_window']._for_xml_id('odoo_garden.action_garden_operation')
        action['domain'] = [('crop_ids', 'in', self.ids)]
        return action

    # ------------------------------------------------------------------
    # Référence (nom de culture / de lot)
    # ------------------------------------------------------------------
    def _get_name_prefix(self):
        """Préfixe de la référence : ``<initiale espèce>-<année>-<code planche>``."""
        self.ensure_one()
        species = unicodedata.normalize('NFD', self.species_id.name or 'X')
        initial = next((c for c in species if c.isalpha() and c.isascii()), 'X').upper()
        date = (
            self.season_id.date_start or self.planned_sowing_date
            or self.planned_harvest_start or fields.Date.context_today(self)
        )
        bed_ref = re.sub(r'[^A-Za-z0-9]+', '', self.bed_id.code or self.bed_id.name or '') or 'PL'
        return '%s-%s-%s' % (initial, date.year, bed_ref)

    def _assign_names(self):
        for crop in self:
            prefix = crop._get_name_prefix()
            taken = self.search_fetch(
                [('name', '=like', prefix + '-%'), ('id', '!=', crop.id)], ['name'],
            ).mapped('name')
            numbers = [
                int(name[len(prefix) + 1:]) for name in taken
                if name[len(prefix) + 1:].isdigit()
            ]
            crop.name = '%s-%02d' % (prefix, max(numbers, default=0) + 1)

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [self._complete_planned_dates(dict(vals)) for vals in vals_list]
        crops = super().create(vals_list)
        crops.filtered(lambda c: c.name == '/')._assign_names()
        return crops

    def write(self, vals):
        closing = self.browse()
        if vals.get('state') == 'done' and 'date_end' not in vals:
            closing = self.filtered(lambda c: c.state != 'done' and not c.date_end)
        result = super().write(vals)
        for crop in closing.filtered(lambda c: not c.date_end):
            crop.date_end = crop._get_last_harvest_date() or fields.Date.context_today(crop)
        if {'bed_id', 'template_id', 'season_id', 'planned_sowing_date'} & vals.keys():
            for crop in self:
                if not crop.name.startswith(crop._get_name_prefix() + '-'):
                    crop._assign_names()
        return result
