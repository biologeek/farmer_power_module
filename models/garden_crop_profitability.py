from odoo import api, fields, models
from odoo.tools import SQL


class GardenCropProfitability(models.Model):
    _name = 'garden.crop.profitability'
    _description = 'Profitability per Crop'
    _order = 'margin_per_hour desc, id'
    _rec_name = 'crop_id'
    # Modèle de reporting : une ligne par culture (non annulée), recalculée par ``refresh()`` à partir de
    # l'ORM (champs de rentabilité de ``garden.crop`` et service ``garden.revenue``).
    #
    # Choix de conception : le chiffre d'affaires dépend de l'attribution par lot (facture -> commande ->
    # livraison -> lot) ou au prorata mensuel des récoltes, ce qui est fragile et dupliqué en SQL pur. La
    # règle d'attribution reste donc écrite une seule fois, en Python (``garden.revenue``), et ce modèle
    # en garde une copie stockée, actualisée à l'ouverture du rapport et du tableau de bord, par le bouton
    # « Actualiser » et chaque nuit (cron). Le SQL n'est utilisé que pour agréger les ratios (moyennes
    # pondérées) dans les vues pivot et graphique.
    #
    # Les montants sont dans la monnaie de la société de chaque culture ; additionner des sociétés de
    # monnaies différentes n'a pas de sens (limite connue).

    crop_id = fields.Many2one(
        'garden.crop', string='Crop', required=True, index=True, ondelete='cascade', readonly=True,
    )
    company_id = fields.Many2one('res.company', string='Company', readonly=True, index=True)
    currency_id = fields.Many2one('res.currency', string='Currency', related='company_id.currency_id')
    season_id = fields.Many2one('garden.season', string='Season', readonly=True, index=True)
    site_id = fields.Many2one('garden.site', string='Site', readonly=True, index=True)
    garden_id = fields.Many2one('garden.garden', string='Block', readonly=True, index=True)
    bed_id = fields.Many2one('garden.bed', string='Bed', readonly=True, index=True)
    species_id = fields.Many2one('garden.species', string='Species', readonly=True, index=True)
    family = fields.Selection(
        related='species_id.family', string='Botanical Family', store=True, readonly=True,
    )
    variety_id = fields.Many2one('garden.variety', string='Variety', readonly=True, index=True)
    state = fields.Selection(
        related='crop_id.state', string='Status', store=True, readonly=True,
    )
    date = fields.Date(
        'Start Date', readonly=True, help='Start of the occupation of the bed (actual, otherwise planned).',
    )
    area = fields.Float('Area (m²)', readonly=True, aggregator='sum')
    occupation_days = fields.Integer('Days of Occupation', readonly=True, aggregator='sum')

    hours = fields.Float('Work Hours', readonly=True, aggregator='sum')
    labour_cost = fields.Float('Labor Cost', readonly=True, aggregator='sum')
    input_cost = fields.Float('Input Cost', readonly=True, aggregator='sum')
    fixed_cost = fields.Float('Fixed Costs', readonly=True, aggregator='sum')
    harvested_qty = fields.Float('Harvested Quantity (kg)', readonly=True, aggregator='sum')
    loss_qty = fields.Float('Lost Quantity (kg)', readonly=True, aggregator='sum')
    revenue = fields.Float('Revenue', readonly=True, aggregator='sum')
    margin = fields.Float('Margin', readonly=True, aggregator='sum')

    # Ratios : en vue pivot ou graphique, la valeur d'un groupe est le ratio des sommes (pondérée),
    # pas la moyenne des ratios (voir ``_read_group_select``).
    margin_per_hour = fields.Float(
        'Margin per Hour', readonly=True, aggregator='avg',
        help='Margin / work hours. On a group: sum of margins / sum of hours.',
    )
    margin_per_m2 = fields.Float(
        'Margin per m²', readonly=True, aggregator='avg',
        help='Margin / area. On a group: sum of margins / sum of areas.',
    )
    yield_per_m2 = fields.Float(
        'Yield (kg/m²)', readonly=True, aggregator='avg',
        help='Harvested quantity / area. On a group: sum of harvests / sum of areas.',
    )
    loss_rate = fields.Float(
        'Loss Rate', readonly=True, aggregator='avg', digits=(16, 4),
        help='Losses / (harvest + losses). On a group: computed on the sums.',
    )

    expected_yield_qty = fields.Float('Expected Harvest (kg)', readonly=True, aggregator='sum')
    expected_revenue = fields.Float('Expected Revenue', readonly=True, aggregator='sum')
    expected_hours = fields.Float('Expected Hours', readonly=True, aggregator='sum')
    yield_gap = fields.Float('Harvest Gap (kg)', readonly=True, aggregator='sum')
    revenue_gap = fields.Float('Revenue Gap', readonly=True, aggregator='sum')
    hours_gap = fields.Float('Hours Gap', readonly=True, aggregator='sum')

    _crop_unique = models.Constraint('UNIQUE (crop_id)', 'Only one profitability line per crop.')

    # ------------------------------------------------------------------
    # Agrégation des ratios (le seul endroit où du SQL est écrit)
    # ------------------------------------------------------------------
    def _read_group_select(self, aggregate_spec, query):
        ratios = {
            'margin_per_hour:avg': ('margin', 'hours'),
            'margin_per_m2:avg': ('margin', 'area'),
            'yield_per_m2:avg': ('harvested_qty', 'area'),
        }
        if aggregate_spec in ratios:
            numerator, denominator = ratios[aggregate_spec]
            return SQL(
                'SUM(%(num)s) / NULLIF(SUM(%(den)s), 0.0)',
                num=self._field_to_sql(self._table, numerator, query),
                den=self._field_to_sql(self._table, denominator, query),
            )
        if aggregate_spec == 'loss_rate:avg':
            lost = self._field_to_sql(self._table, 'loss_qty', query)
            harvested = self._field_to_sql(self._table, 'harvested_qty', query)
            return SQL('SUM(%(lost)s) / NULLIF(SUM(%(harvested)s) + SUM(%(lost)s), 0.0)', lost=lost, harvested=harvested)
        return super()._read_group_select(aggregate_spec, query)

    # ------------------------------------------------------------------
    # Actualisation
    # ------------------------------------------------------------------
    @api.model
    def _prepare_values(self, crops):
        """Valeurs des lignes de rentabilité des cultures (calculées en ``sudo``, en lot)."""
        values = {}
        crops = crops.sudo()
        # Le chiffre d'affaires est calculé en une seule passe pour toutes les cultures : l'ORM le calculerait sinon
        # par blocs de 1 000 cultures, et chaque bloc relit les ventes (factures et point de vente).
        stale = crops.filtered(lambda crop: not self.env.cache.contains(crop, crop._fields['revenue']))
        if len(stale) > 1000:
            revenue_fields = [crops._fields['revenue'], crops._fields['sale_line_count']]
            with self.env.protecting(revenue_fields, stale):
                stale._compute_revenue()
        for crop in crops:
            bed = crop.bed_id
            hours, area = crop.labour_hours, crop.area
            lost = crop.loss_qty
            total = crop.harvested_qty + lost
            values[crop.id] = {
                'crop_id': crop.id,
                'company_id': crop.company_id.id,
                'season_id': crop.season_id.id,
                'site_id': bed.site_id.id,
                'garden_id': bed.garden_id.id,
                'bed_id': bed.id,
                'species_id': crop.species_id.id,
                'variety_id': crop.variety_id.id,
                'date': crop.occupation_start,
                'area': area,
                'occupation_days': crop.occupation_days,
                'hours': hours,
                'labour_cost': crop.labour_cost,
                'input_cost': crop.input_cost,
                'fixed_cost': crop.fixed_cost,
                'harvested_qty': crop.harvested_qty,
                'loss_qty': lost,
                'revenue': crop.revenue,
                'margin': crop.margin,
                'margin_per_hour': crop.margin_per_hour,
                'margin_per_m2': crop.margin_per_m2,
                'yield_per_m2': crop.harvested_qty / area if area > 0 else 0.0,
                'loss_rate': lost / total if total > 0 else 0.0,
                'expected_yield_qty': crop.expected_yield_qty,
                'expected_revenue': crop.expected_revenue,
                'expected_hours': crop.expected_hours,
                'yield_gap': crop.yield_gap,
                'revenue_gap': crop.revenue_gap,
                'hours_gap': crop.hours_gap,
            }
        return values

    @api.model
    def refresh(self):
        """Recalcule le rapport : une ligne par culture non annulée (créée, mise à jour ou supprimée)."""
        self = self.sudo()
        Crop = self.env['garden.crop'].with_context(active_test=False)
        crops = Crop.search([('state', '!=', 'cancelled')])
        crops.invalidate_recordset(['revenue', 'sale_line_count', 'margin', 'margin_per_hour', 'margin_per_m2',
                                    'fixed_cost', 'revenue_gap'])
        values = self._prepare_values(crops)
        existing = {line.crop_id.id: line for line in self.search([])}
        stale = self.browse([line.id for crop_id, line in existing.items() if crop_id not in values])
        stale.unlink()
        to_create = []
        for crop_id, vals in values.items():
            line = existing.get(crop_id)
            if not line:
                to_create.append(vals)
                continue
            changed = {
                key: value for key, value in vals.items()
                if key != 'crop_id' and line._fields[key].convert_to_write(line[key], line) != value
            }
            if changed:
                line.write(changed)
        if to_create:
            self.create(to_create)
        return True

    @api.model
    def _cron_refresh(self):
        self.refresh()

    @api.model
    def action_open(self, xmlid='farmer_power.action_garden_profitability'):
        """Actualise le rapport puis ouvre l'action donnée (menus Rentabilité)."""
        self.refresh()
        return self.env['ir.actions.act_window']._for_xml_id(xmlid)

    @api.model
    def action_refresh(self):
        """Bouton « Actualiser » : recalcule puis recharge la vue."""
        self.refresh()
        return {'type': 'ir.actions.client', 'tag': 'soft_reload'}

    # ------------------------------------------------------------------
    # Tableau de bord
    # ------------------------------------------------------------------
    @api.model
    def get_dashboard_data(self):
        """Chiffres clés du tableau de bord (gérant) : actualise le rapport puis agrège.

        Retourne ``margin_by_species``, ``hours_by_category``, ``monthly_revenue`` (listes de
        ``{label, value}``), ``best`` et ``worst`` (10 cultures les plus et les moins rentables à l'heure,
        parmi celles qui ont des heures) et ``totals``.
        """
        self.check_access('read')
        self.refresh()
        lines = self.search([])
        species = {}
        for line in lines:
            label = line.species_id.display_name or self.env._('No species')
            species[label] = species.get(label, 0.0) + line.margin
        margin_by_species = sorted(
            ({'label': label, 'value': value} for label, value in species.items()),
            key=lambda row: -row['value'],
        )

        categories = dict(self.env['garden.operation.type']._fields['category']._description_selection(self.env))
        hours_by_category = sorted(
            (
                {'label': categories.get(category) or self.env._('Other'), 'value': hours}
                for category, hours in self.env['garden.operation.allocation']._read_group(
                    [], ['category'], ['hours:sum'],
                ) if hours
            ),
            key=lambda row: -row['value'],
        )

        crops = lines.crop_id
        attribution = self.env['garden.revenue'].get_attribution(crops)
        amounts = {}
        for by_line in attribution.values():
            for line_id, amount in by_line.items():
                amounts[line_id] = amounts.get(line_id, 0.0) + amount
        months = {}
        for move_line in self.env['account.move.line'].sudo().browse(list(amounts)):
            key = move_line.date.strftime('%Y-%m')
            months[key] = months.get(key, 0.0) + amounts[move_line.id]
        for entries in self.env['garden.revenue'].get_extra_entries(crops).values():
            for entry in entries:
                key = entry['date'].strftime('%Y-%m')
                months[key] = months.get(key, 0.0) + entry['amount']
        monthly_revenue = [{'label': key, 'value': months[key]} for key in sorted(months)]

        with_hours = lines.filtered(lambda line: line.hours > 0)
        ranked = with_hours.sorted(lambda line: (-line.margin_per_hour, line.id))

        def row(line):
            return {
                'id': line.crop_id.id, 'label': line.crop_id.display_name, 'value': line.margin_per_hour,
                'margin': line.margin, 'hours': line.hours,
            }

        return {
            'margin_by_species': margin_by_species,
            'hours_by_category': hours_by_category,
            'monthly_revenue': monthly_revenue,
            'best': [row(line) for line in ranked[:10]],
            'worst': [row(line) for line in reversed(ranked[-10:])] if len(ranked) else [],
            'totals': {
                'revenue': sum(lines.mapped('revenue')),
                'margin': sum(lines.mapped('margin')),
                'hours': sum(lines.mapped('hours')),
                'crops': len(lines),
            },
        }
