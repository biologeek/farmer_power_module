import re
import unicodedata

from odoo import api, fields, models


class GardenCrop(models.Model):
    _name = 'garden.crop'
    _description = 'Culture sur planche'
    _inherit = ['mail.thread']
    _order = 'planned_sowing_date, id'

    name = fields.Char(
        'Référence', default='/', copy=False, readonly=True, index=True,
        help="Générée à la création : initiale de l'espèce, année, code de la planche et numéro d'ordre "
             "(ex. T-2027-P12-01). Servira de nom de lot de traçabilité.",
    )
    season_id = fields.Many2one(
        'garden.season', string='Saison', index=True, ondelete='restrict', tracking=True,
    )
    template_id = fields.Many2one(
        'garden.crop.template', string='Itinéraire technique', required=True, index=True, tracking=True,
    )
    variety_id = fields.Many2one(
        'garden.variety', string='Variété', related='template_id.variety_id', store=True, index=True,
    )
    species_id = fields.Many2one(
        'garden.species', string='Espèce', related='template_id.species_id', store=True, index=True,
    )
    family = fields.Selection(related='species_id.family', string='Famille botanique', store=True)
    bed_id = fields.Many2one('garden.bed', string='Planche', required=True, index=True, tracking=True)
    bed_area = fields.Float('Surface de la planche (m²)', related='bed_id.area')
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
    )

    # Dates prévues
    planned_sowing_date = fields.Date('Semis prévu', tracking=True)
    planned_transplant_date = fields.Date('Repiquage prévu')
    planned_harvest_start = fields.Date('Début de récolte prévu', tracking=True)
    planned_harvest_end = fields.Date('Fin de récolte prévue')
    # Dates réelles (alimentées par les opérations réalisées à partir de la phase 3)
    date_start = fields.Date('Début réel')
    date_end = fields.Date('Fin réelle')
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

    sowing_quantity = fields.Float('Nombre de plants semés')
    planted_quantity = fields.Float('Nombre de plants plantés')
    notes = fields.Text('Notes')
    quantity_harvested = fields.Float('Quantité récoltée (kg)')
    value_harvested = fields.Float('Valeur récoltée (€)')
    action_ids = fields.One2many('garden.action', 'crop_id', string='Actions')

    _bed_share_range = models.Constraint(
        'CHECK (bed_share > 0 AND bed_share <= 100)',
        'La part de la planche doit être comprise entre 0 (exclu) et 100 %.',
    )

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

    @api.depends('area', 'template_id.density', 'template_id.expected_yield', 'template_id.expected_price')
    def _compute_forecast(self):
        for crop in self:
            template = crop.template_id
            crop.planned_plant_qty = crop.area * template.density
            crop.expected_yield_qty = crop.area * template.expected_yield
            crop.expected_revenue = crop.expected_yield_qty * template.expected_price

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
        crops = super().create(vals_list)
        crops.filtered(lambda c: c.name == '/')._assign_names()
        return crops

    def write(self, vals):
        result = super().write(vals)
        if {'bed_id', 'template_id', 'season_id', 'planned_sowing_date'} & vals.keys():
            for crop in self:
                if not crop.name.startswith(crop._get_name_prefix() + '-'):
                    crop._assign_names()
        return result

    @api.model
    def get_production_statistics_data(self, params=None):
        self.env.flush_all()
        self.env.cr.execute(
            """
            SELECT COALESCE(TO_CHAR(COALESCE(date_end, date_start), 'YYYY-MM'), 'Unknown') AS period,
                   COALESCE(SUM(quantity_harvested), 0) AS quantity,
                   COALESCE(SUM(value_harvested), 0) AS value
            FROM garden_crop
            GROUP BY period
            ORDER BY period
            """
        )
        month_rows = self.env.cr.fetchall()
        month_totals = [
            {
                'period': period or 'Unknown',
                'quantity': float(quantity or 0.0),
                'value': float(value or 0.0),
            }
            for period, quantity, value in month_rows
        ]

        self.env.cr.execute(
            """
            SELECT COALESCE(b.name, 'Sans planche') AS bed_name,
                   COALESCE(SUM(quantity_harvested), 0) AS quantity,
                   COALESCE(SUM(value_harvested), 0) AS value
            FROM garden_crop c
            LEFT JOIN garden_bed b ON c.bed_id = b.id
            GROUP BY b.name
            ORDER BY b.name
            """
        )
        bed_rows = self.env.cr.fetchall()
        bed_totals = [
            {
                'bed': bed_name,
                'quantity': float(quantity or 0.0),
                'value': float(value or 0.0),
            }
            for bed_name, quantity, value in bed_rows
        ]

        self.env.cr.execute(
            """
            SELECT COALESCE(cat.name, 'Sans culture') AS crop_name,
                   COALESCE(SUM(quantity_harvested), 0) AS quantity,
                   COALESCE(SUM(value_harvested), 0) AS value
            FROM garden_crop c
            LEFT JOIN garden_crop_template cat ON c.template_id = cat.id
            GROUP BY cat.name
            ORDER BY cat.name
            """
        )
        crop_rows = self.env.cr.fetchall()
        crop_totals = [
            {
                'crop': crop_name,
                'quantity': float(quantity or 0.0),
                'value': float(value or 0.0),
            }
            for crop_name, quantity, value in crop_rows
        ]

        return {
            'month_totals': month_totals,
            'bed_totals': bed_totals,
            'crop_totals': crop_totals,
        }
