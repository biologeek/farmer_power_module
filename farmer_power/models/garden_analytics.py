import calendar
from collections import defaultdict
from datetime import date

from odoo import api, models
from odoo.exceptions import AccessError
from odoo.tools.misc import format_date


class GardenAnalytics(models.AbstractModel):
    _name = 'garden.analytics'
    _description = 'Farm Dashboards'
    # Tableaux de bord thématiques (occupation, cultures, travail, finances, comparatif annuel). Chaque thème
    # renvoie des chiffres clés (``kpis``) et des graphiques décrits de façon neutre (``charts``) : le client
    # (composant OWL ``garden_analytics``) les dessine sans connaître le métier. Un graphique est un dict
    # ``{id, type, title, labels, series: [{name, values}], unit, wide}`` ; ``type`` vaut ``bar``, ``stacked``,
    # ``line``, ``hbar`` ou ``donut``. Les calculs passent par l'ORM : les droits et les règles
    # multi-sociétés de l'utilisateur s'appliquent, sauf le chiffre d'affaires (``garden.revenue``, sudo).

    _THEME_GROUPS = {
        'occupation': 'farmer_power.group_garden_chef',
        'crops': 'farmer_power.group_garden_chef',
        'work': 'farmer_power.group_garden_chef',
        'finance': 'farmer_power.group_garden_manager',
        'years': 'farmer_power.group_garden_manager',
    }

    # ------------------------------------------------------------------
    # Point d'entrée
    # ------------------------------------------------------------------
    @api.model
    def get_data(self, theme, year=None, refresh=False):
        """Données d'un thème pour une année : ``{theme, year, years, currency, kpis, charts}``."""
        group = self._THEME_GROUPS.get(theme)
        if not group:
            raise ValueError("Unknown dashboard: %s" % theme)
        if not self.env.user.has_group(group):
            raise AccessError(self.env._("You are not allowed to open this dashboard."))
        if theme in ('finance', 'years') and refresh:
            self.env['garden.crop.profitability'].refresh()
        counts = self._get_years(theme)
        years = sorted(counts) or [date.today().year]
        year = year if year in years else self._default_year(counts)
        build = getattr(self, '_get_%s_data' % theme)
        kpis, charts = build(year, years)
        return {
            'theme': theme,
            'year': year,
            'years': years,
            'has_year_filter': theme != 'years',
            'currency': self.env.company.currency_id.symbol or '',
            'kpis': kpis,
            'charts': [chart for chart in charts if chart],
        }

    # ------------------------------------------------------------------
    # Outils
    # ------------------------------------------------------------------
    @api.model
    def _get_years(self, theme):
        """Années ayant des données : ``{année: nombre d'enregistrements}``."""
        counts = defaultdict(int)

        def count(model, field, domain=()):
            for year_start, number in self.env[model]._read_group(list(domain), [f'{field}:year'], ['__count']):
                if year_start:
                    counts[year_start.year] += number

        if theme in ('occupation', 'crops'):
            count('garden.crop', 'occupation_start', [('state', '!=', 'cancelled')])
        elif theme == 'work':
            count('garden.operation', 'planned_date')
            count('garden.operation', 'date')
            count('garden.loss', 'date')
        else:
            count('garden.crop.profitability', 'date')
        return counts

    @api.model
    def _default_year(self, counts):
        """Année la mieux fournie en données (la plus récente à égalité), sinon l'année en cours."""
        if not counts:
            return date.today().year
        return max(counts, key=lambda year: (counts[year], year))

    @api.model
    def _kpi(self, label, value, unit='', digits=0):
        if not isinstance(value, str):
            value = round(value, digits) if digits else int(round(value))
        return {'label': label, 'value': value, 'unit': unit}

    @api.model
    def _chart(self, chart_id, chart_type, title, labels, series, unit='', wide=False):
        """Graphique, ou ``None`` quand il n'y a rien à afficher (il est alors omis)."""
        # ``series``: ``(nom, valeurs)`` ou ``(nom, valeurs, couleur)`` ; la couleur est l'indice dans la palette
        # du client (0 vert, 1 bleu, 2 orange, 3 violet, 4 or, 5 rouge, 6 turquoise, 7 gris).
        series = [
            {'name': serie[0], 'values': [round(v, 2) for v in serie[1]], 'color': serie[2] if len(serie) > 2 else None}
            for serie in series
        ]
        if not labels or not any(abs(v) > 1e-9 for s in series for v in s['values']):
            return None
        return {
            'id': chart_id, 'type': chart_type, 'title': title, 'labels': labels, 'series': series,
            'unit': unit, 'wide': wide,
        }

    @api.model
    def _month_labels(self, year):
        return [format_date(self.env, date(year, month, 1), date_format='MMM') for month in range(1, 13)]

    @api.model
    def _overlap_days(self, start, end, low, high):
        """Nombre de jours (bornes incluses) communs à ``[start, end]`` et ``[low, high]``."""
        return max((min(end, high) - max(start, low)).days + 1, 0)

    @api.model
    def _ranked(self, totals, limit=10, others=None):
        """``[(libellé, valeur)]`` triés par valeur décroissante, regroupés en « Autres » au-delà de ``limit``."""
        rows = sorted(((k, v) for k, v in totals.items() if abs(v) > 1e-9), key=lambda item: (-item[1], item[0]))
        if others and len(rows) > limit:
            rest = sum(value for _label, value in rows[limit - 1:])
            rows = rows[:limit - 1] + [(others, rest)]
        else:
            rows = rows[:limit]
        return rows

    @api.model
    def _selection_labels(self, model, field):
        return dict(self.env[model]._fields[field]._description_selection(self.env))

    @api.model
    def _species_name(self, species):
        return species.display_name or self.env._("No species")

    @api.model
    def _crop_spans(self, domain=None):
        """Cultures non annulées avec une période d'occupation : ``[(culture, début, fin)]``."""
        crops = self.env['garden.crop'].search([('state', '!=', 'cancelled'), ('occupation_start', '!=', False)] + (domain or []))
        return [(crop, crop.occupation_start, crop.occupation_end or crop.occupation_start) for crop in crops]

    # ------------------------------------------------------------------
    # Occupation des planches
    # ------------------------------------------------------------------
    @api.model
    def _get_occupation_data(self, year, years):
        beds = self.env['garden.bed'].search([])
        total_area = sum(beds.mapped('area'))
        families = self._selection_labels('garden.species', 'family')
        today = date.today()
        year_start, year_end = date(year, 1, 1), date(year, 12, 31)
        days_in_year = (year_end - year_start).days + 1
        spans = self._crop_spans()

        month_days = [calendar.monthrange(year, m)[1] for m in range(1, 13)]
        month_area = [0.0] * 12  # m² × jours occupés, par mois
        family_area = defaultdict(lambda: [0.0] * 12)
        bed_area_days = defaultdict(float)
        garden_area_days = defaultdict(float)
        for crop, start, end in spans:
            for month in range(1, 13):
                days = self._overlap_days(start, end, date(year, month, 1), date(year, month, month_days[month - 1]))
                if days:
                    month_area[month - 1] += crop.area * days
                    family_area[crop.family or 'other'][month - 1] += crop.area * days / month_days[month - 1]
            days_year = self._overlap_days(start, end, year_start, year_end)
            if days_year:
                bed_area_days[crop.bed_id.id] += crop.area * days_year
                garden_area_days[crop.bed_id.garden_id.id] += crop.area * days_year

        rates = [
            min(month_area[m] / (total_area * month_days[m]) * 100, 100.0) if total_area else 0.0 for m in range(12)
        ]
        year_rate = (
            min(sum(month_area) / (total_area * days_in_year) * 100, 100.0) if total_area else 0.0
        )

        busy_beds = {crop.bed_id.id for crop, start, end in spans if start <= today <= end}
        today_area = sum(crop.area for crop, start, end in spans if start <= today <= end)
        free_beds = len(beds.filtered(lambda bed: bed.id not in busy_beds))

        gardens = defaultdict(float)
        for bed in beds:
            gardens[bed.garden_id] += bed.area
        by_block = {
            garden.display_name or self.env._("No block"): min(garden_area_days[garden.id] / (area * days_in_year) * 100, 100.0)
            for garden, area in gardens.items() if area
        }
        bed_rates = {
            bed.display_name: min(bed_area_days[bed.id] / (bed.area * days_in_year) * 100, 100.0)
            for bed in beds if bed.area
        }
        least_used = sorted(bed_rates.items(), key=lambda item: (item[1], item[0]))[:10]

        kpis = [
            self._kpi(self.env._("Beds"), len(beds)),
            self._kpi(self.env._("Total area"), total_area, 'm²'),
            self._kpi(self.env._("Cultivated today"), today_area, 'm²'),
            self._kpi(self.env._("Free beds today"), free_beds),
            self._kpi(self.env._("Average occupation of %s", year), year_rate, '%', 1),
        ]
        family_series = [
            (families.get(family, family), values) for family, values in sorted(family_area.items())
        ]
        charts = [
            self._chart(
                'occupation_rate', 'line', self.env._("Occupation rate per month"), self._month_labels(year),
                [(self.env._("Occupied share of the area"), rates)], '%', wide=True,
            ),
            self._chart(
                'occupation_family', 'stacked', self.env._("Occupied area per month, by botanical family"),
                self._month_labels(year), family_series, 'm²', wide=True,
            ),
            self._chart(
                'occupation_block', 'hbar', self.env._("Occupation per block over the year"),
                [label for label, _v in self._ranked(by_block, 12)], [(self.env._("Occupation"), [v for _l, v in self._ranked(by_block, 12)])], '%',
            ),
            self._chart(
                'occupation_least', 'hbar', self.env._("Least used beds over the year"),
                [label for label, _v in least_used], [(self.env._("Occupation"), [v for _l, v in least_used])], '%',
            ),
        ]
        return kpis, charts

    # ------------------------------------------------------------------
    # Répartition des cultures
    # ------------------------------------------------------------------
    @api.model
    def _get_crops_data(self, year, years):
        crops = self.env['garden.crop'].search([
            ('state', '!=', 'cancelled'),
            ('occupation_start', '>=', date(year, 1, 1)), ('occupation_start', '<=', date(year, 12, 31)),
        ])
        families = self._selection_labels('garden.species', 'family')
        states = self._selection_labels('garden.crop', 'state')
        by_family, by_species, by_block = defaultdict(float), defaultdict(float), defaultdict(float)
        harvest, area_by_species = defaultdict(float), defaultdict(float)
        by_state, by_month = defaultdict(int), [0.0] * 12
        for crop in crops:
            by_family[families.get(crop.family, crop.family or '')] += crop.area
            name = self._species_name(crop.species_id)
            by_species[name] += crop.area
            by_block[crop.bed_id.garden_id.display_name or self.env._("No block")] += crop.area
            by_state[crop.state] += 1
            by_month[crop.occupation_start.month - 1] += crop.area
            if crop.harvested_qty:
                harvest[name] += crop.harvested_qty
                area_by_species[name] += crop.area
        yields = {name: harvest[name] / area_by_species[name] for name in harvest if area_by_species[name]}
        order = ['planned', 'sown', 'in_place', 'harvesting', 'done']
        state_labels = [states[s] for s in order if by_state.get(s)]
        state_values = [by_state[s] for s in order if by_state.get(s)]

        top_species = self._ranked(by_species, 8, self.env._("Other species"))
        top_harvest = self._ranked(harvest, 10)
        top_yield = self._ranked(yields, 10)
        blocks = self._ranked(by_block, 10)
        family_rows = self._ranked(by_family, 10)
        kpis = [
            self._kpi(self.env._("Crops"), len(crops)),
            self._kpi(self.env._("Species"), len(by_species)),
            self._kpi(self.env._("Cultivated area"), sum(crops.mapped('area')), 'm²'),
            self._kpi(self.env._("Harvested"), sum(crops.mapped('harvested_qty')), 'kg'),
        ]
        charts = [
            self._chart('crops_family', 'donut', self.env._("Area per botanical family"),
                        [l for l, _v in family_rows], [(self.env._("Area"), [v for _l, v in family_rows])], 'm²'),
            self._chart('crops_species', 'donut', self.env._("Area per species"),
                        [l for l, _v in top_species], [(self.env._("Area"), [v for _l, v in top_species])], 'm²'),
            self._chart('crops_start', 'bar', self.env._("Area put in place per month"),
                        self._month_labels(year), [(self.env._("Area"), by_month)], 'm²', wide=True),
            self._chart('crops_harvest', 'hbar', self.env._("Harvest per species"),
                        [l for l, _v in top_harvest], [(self.env._("Harvest"), [v for _l, v in top_harvest])], 'kg'),
            self._chart('crops_yield', 'hbar', self.env._("Yield per species"),
                        [l for l, _v in top_yield], [(self.env._("Yield"), [v for _l, v in top_yield])], 'kg/m²'),
            self._chart('crops_state', 'bar', self.env._("Crops per status"),
                        state_labels, [(self.env._("Crops"), state_values)]),
            self._chart('crops_block', 'hbar', self.env._("Area per block"),
                        [l for l, _v in blocks], [(self.env._("Area"), [v for _l, v in blocks])], 'm²'),
        ]
        return kpis, charts

    # ------------------------------------------------------------------
    # Travail, opérations et pertes
    # ------------------------------------------------------------------
    @api.model
    def _get_work_data(self, year, years):
        low, high = date(year, 1, 1), date(year, 12, 31)
        today = date.today()
        Operation = self.env['garden.operation']
        categories = self._selection_labels('garden.operation.type', 'category')
        done = Operation.search([('state', '=', 'done'), ('date', '>=', low), ('date', '<=', high)])
        hours_by_category = defaultdict(lambda: [0.0] * 12)
        by_type = defaultdict(float)
        for operation in done:
            hours_by_category[operation.category][operation.date.month - 1] += operation.total_hours
            by_type[operation.type_id.display_name or self.env._("Other")] += operation.total_hours
        # Temps par employé : lignes de temps détaillées si elles existent, sinon la durée de chaque employé.
        by_employee = defaultdict(float)
        for operation in done.sudo():  # les noms des employés sont lisibles sans droit RH
            if operation.worker_ids:
                for worker in operation.worker_ids:
                    by_employee[worker.employee_id.display_name or self.env._("Unassigned")] += worker.duration
            elif operation.employee_ids:
                for employee in operation.employee_ids:
                    by_employee[employee.display_name] += operation.duration
            else:
                by_employee[self.env._("Unassigned")] += operation.duration

        # Une opération faite compte dans le mois où elle a été réalisée, les autres dans celui prévu.
        scheduled = Operation.search([
            ('state', 'not in', ('cancelled', 'done')), ('planned_date', '>=', low), ('planned_date', '<=', high),
        ])
        statuses = {'done': [0] * 12, 'late': [0] * 12, 'upcoming': [0] * 12}
        for operation in done:
            statuses['done'][operation.date.month - 1] += 1
        for operation in scheduled:
            month = operation.planned_date.month - 1
            statuses['late' if operation.planned_date < today else 'upcoming'][month] += 1
        planned_total = sum(sum(values) for values in statuses.values())
        done_rate = sum(statuses['done']) / planned_total * 100 if planned_total else 0.0

        losses = self.env['garden.loss'].search([('date', '>=', low), ('date', '<=', high)])
        causes = self._selection_labels('garden.loss', 'cause')
        stages = self._selection_labels('garden.loss', 'stage')
        by_cause, loss_species = defaultdict(float), defaultdict(float)
        loss_month = defaultdict(lambda: [0.0] * 12)
        for loss in losses:
            by_cause[causes.get(loss.cause, loss.cause)] += loss.quantity_ref
            loss_species[self._species_name(loss.crop_id.species_id)] += loss.quantity_ref
            loss_month[loss.stage][loss.date.month - 1] += loss.quantity_ref

        kpis = [
            self._kpi(self.env._("Hours worked"), sum(done.mapped('total_hours')), 'h', 1),
            self._kpi(self.env._("Operations done"), len(done)),
            self._kpi(self.env._("Plan completion"), done_rate, '%', 1),
            self._kpi(self.env._("Lost quantity"), sum(losses.mapped('quantity_ref')), 'kg'),
        ]
        top_types = self._ranked(by_type, 10)
        top_employees = self._ranked(by_employee, 10)
        causes_rows = self._ranked(by_cause, 10)
        loss_rows = self._ranked(loss_species, 10)
        charts = [
            self._chart(
                'work_hours', 'stacked', self.env._("Hours per month, by operation category"),
                self._month_labels(year),
                [(categories.get(c, c), values) for c, values in sorted(hours_by_category.items())], 'h', wide=True,
            ),
            self._chart(
                'work_status', 'stacked', self.env._("Operations of the plan, by month"), self._month_labels(year),
                [(self.env._("Done"), statuses['done'], 0), (self.env._("Late"), statuses['late'], 5),
                 (self.env._("Upcoming"), statuses['upcoming'], 7)], wide=True,
            ),
            self._chart('work_type', 'hbar', self.env._("Hours per operation type"),
                        [l for l, _v in top_types], [(self.env._("Hours"), [v for _l, v in top_types])], 'h'),
            self._chart('work_employee', 'hbar', self.env._("Hours per employee"),
                        [l for l, _v in top_employees], [(self.env._("Hours"), [v for _l, v in top_employees])], 'h'),
            self._chart('loss_cause', 'donut', self.env._("Losses per cause"),
                        [l for l, _v in causes_rows], [(self.env._("Losses"), [v for _l, v in causes_rows])], 'kg'),
            self._chart('loss_species', 'hbar', self.env._("Losses per species"),
                        [l for l, _v in loss_rows], [(self.env._("Losses"), [v for _l, v in loss_rows])], 'kg'),
            self._chart(
                'loss_month', 'stacked', self.env._("Losses per month"), self._month_labels(year),
                [(stages.get(stage, stage), values) for stage, values in sorted(loss_month.items())], 'kg', wide=True,
            ),
        ]
        return kpis, charts

    # ------------------------------------------------------------------
    # Chiffre d'affaires et marge
    # ------------------------------------------------------------------
    @api.model
    def _monthly_revenue(self, crops):
        """Chiffre d'affaires attribué aux cultures : ``{(année, mois): montant}`` (factures et passerelles)."""
        Revenue = self.env['garden.revenue']
        amounts = defaultdict(float)
        for by_line in Revenue.get_attribution(crops).values():
            for line_id, amount in by_line.items():
                amounts[line_id] += amount
        months = defaultdict(float)
        for move_line in self.env['account.move.line'].sudo().browse(list(amounts)):
            months[(move_line.date.year, move_line.date.month)] += amounts[move_line.id]
        for entries in Revenue.get_extra_entries(crops).values():
            for entry in entries:
                months[(entry['date'].year, entry['date'].month)] += entry['amount']
        return months

    @api.model
    def _get_finance_data(self, year, years):
        Profit = self.env['garden.crop.profitability']
        lines = Profit.search([('date', '>=', date(year, 1, 1)), ('date', '<=', date(year, 12, 31))])
        currency = self.env.company.currency_id.symbol or ''
        revenue = sum(lines.mapped('revenue'))
        labour, inputs, fixed = (sum(lines.mapped(f)) for f in ('labour_cost', 'input_cost', 'fixed_cost'))
        margin = sum(lines.mapped('margin'))

        month_revenue = [0.0] * 12
        for (rev_year, month), amount in self._monthly_revenue(lines.crop_id).items():
            if rev_year == year:
                month_revenue[month - 1] += amount
        month_cost = [0.0] * 12
        allocations = self.env['garden.operation.allocation'].search([
            ('crop_id', 'in', lines.crop_id.ids), ('date', '>=', date(year, 1, 1)), ('date', '<=', date(year, 12, 31)),
        ])
        for allocation in allocations:
            month_cost[allocation.date.month - 1] += allocation.labour_cost + allocation.input_cost
        cumulative, running = [], 0.0
        for month in range(12):
            running += month_revenue[month] - month_cost[month]
            cumulative.append(running)

        species = defaultdict(lambda: defaultdict(float))
        for line in lines:
            row = species[self._species_name(line.species_id)]
            for field in ('revenue', 'margin', 'area', 'hours'):
                row[field] += line[field]
        margin_rows = self._ranked({k: v['margin'] for k, v in species.items()}, 12)
        per_m2 = self._ranked({k: v['margin'] / v['area'] for k, v in species.items() if v['area']}, 12)
        per_hour = self._ranked({k: v['margin'] / v['hours'] for k, v in species.items() if v['hours']}, 12)
        revenue_rows = self._ranked({k: v['revenue'] for k, v in species.items()}, 8, self.env._("Other species"))
        total_area = sum(v['area'] for v in species.values())
        top = [label for label, _v in self._ranked({k: v['revenue'] for k, v in species.items()}, 8)]

        kpis = [
            self._kpi(self.env._("Revenue"), revenue, currency),
            self._kpi(self.env._("Costs"), labour + inputs + fixed, currency),
            self._kpi(self.env._("Margin"), margin, currency),
            self._kpi(self.env._("Margin rate"), margin / revenue * 100 if revenue else 0.0, '%', 1),
        ]
        charts = [
            self._chart(
                'finance_monthly', 'bar', self.env._("Monthly revenue and costs (work and inputs)"),
                self._month_labels(year),
                [(self.env._("Revenue"), month_revenue, 0), (self.env._("Costs"), month_cost, 5)], currency, wide=True,
            ),
            self._chart(
                'finance_cumulative', 'line', self.env._("Cumulative margin (revenue minus work and inputs)"),
                self._month_labels(year), [(self.env._("Cumulative margin"), cumulative)], currency, wide=True,
            ),
            self._chart('finance_margin', 'hbar', self.env._("Margin per species"),
                        [l for l, _v in margin_rows], [(self.env._("Margin"), [v for _l, v in margin_rows])], currency),
            self._chart('finance_per_m2', 'hbar', self.env._("Margin per m² and per species"),
                        [l for l, _v in per_m2], [(self.env._("Margin"), [v for _l, v in per_m2])], f'{currency}/m²'),
            self._chart('finance_per_hour', 'hbar', self.env._("Margin per hour and per species"),
                        [l for l, _v in per_hour], [(self.env._("Margin"), [v for _l, v in per_hour])], f'{currency}/h'),
            self._chart('finance_costs', 'donut', self.env._("Cost structure"),
                        [self.env._("Labor"), self.env._("Inputs"), self.env._("Fixed costs")],
                        [(self.env._("Costs"), [labour, inputs, fixed])], currency),
            self._chart('finance_revenue', 'donut', self.env._("Revenue per species"),
                        [l for l, _v in revenue_rows if _v > 0],
                        [(self.env._("Revenue"), [v for _l, v in revenue_rows if v > 0])], currency),
            self._chart(
                'finance_share', 'bar', self.env._("Share of revenue and share of area, per species"), top,
                [(self.env._("Share of revenue"), [species[s]['revenue'] / revenue * 100 if revenue else 0 for s in top], 0),
                 (self.env._("Share of area"), [species[s]['area'] / total_area * 100 if total_area else 0 for s in top], 7)],
                '%', wide=True,
            ),
        ]
        return kpis, charts

    # ------------------------------------------------------------------
    # Comparatif année par année
    # ------------------------------------------------------------------
    @api.model
    def _get_years_data(self, year, years):
        lines = self.env['garden.crop.profitability'].search([])
        currency = self.env.company.currency_id.symbol or ''
        families = self._selection_labels('garden.species', 'family')
        totals = {y: defaultdict(float) for y in years}
        species = defaultdict(lambda: {y: defaultdict(float) for y in years})
        family_area = defaultdict(lambda: defaultdict(float))
        for line in lines:
            if not line.date or line.date.year not in totals:
                continue
            y = line.date.year
            costs = line.labour_cost + line.input_cost + line.fixed_cost
            for key, value in (
                ('revenue', line.revenue), ('costs', costs), ('margin', line.margin), ('hours', line.hours),
                ('area', line.area), ('harvest', line.harvested_qty),
            ):
                totals[y][key] += value
            row = species[self._species_name(line.species_id)][y]
            row['margin'] += line.margin
            row['harvest'] += line.harvested_qty
            row['area'] += line.area
            family_area[line.family or 'other'][y] += line.area
        labels = [str(y) for y in years]

        def per_year(key):
            return [totals[y][key] for y in years]

        def ratio(numerator, denominator):
            return [totals[y][numerator] / totals[y][denominator] if totals[y][denominator] else 0.0 for y in years]

        revenue_by_year = defaultdict(lambda: [0.0] * 12)
        for (rev_year, month), amount in self._monthly_revenue(lines.crop_id).items():
            if rev_year in totals:
                revenue_by_year[rev_year][month - 1] += amount
        harvest_by_year = defaultdict(lambda: [0.0] * 12)
        moves = self.env['stock.move'].sudo()._read_group(
            [('garden_kind', 'in', ('harvest', 'harvest_return')), ('state', '=', 'done'),
             ('garden_crop_id', '!=', False)],
            ['date:month', 'garden_kind'], ['product_qty:sum'],
        )
        for month, kind, quantity in moves:
            if month.year in totals:
                harvest_by_year[month.year][month.month - 1] += quantity if kind == 'harvest' else -quantity

        top = [
            label for label, _v in self._ranked(
                {name: sum(abs(row[y]['margin']) for y in years) for name, row in species.items()}, 8,
            )
        ]
        best = max(years, key=lambda y: totals[y]['margin'])
        last, before = years[-1], years[-2] if len(years) > 1 else None
        growth = (
            (totals[last]['revenue'] - totals[before]['revenue']) / totals[before]['revenue'] * 100
            if before and totals[before]['revenue'] else None
        )
        kpis = [
            self._kpi(self.env._("Years with data"), len(years)),
            self._kpi(self.env._("Best margin year"), str(best)),
            self._kpi(self.env._("Revenue %s vs previous year", last), '-' if growth is None else growth,
                      '' if growth is None else '%', 1),
        ]
        month_labels = self._month_labels(date.today().year)
        charts = [
            self._chart(
                'years_totals', 'bar', self.env._("Revenue, costs and margin per year"), labels,
                [(self.env._("Revenue"), per_year('revenue'), 0), (self.env._("Costs"), per_year('costs'), 5),
                 (self.env._("Margin"), per_year('margin'), 1)], currency, wide=True,
            ),
            self._chart('years_revenue_month', 'line', self.env._("Monthly revenue, year over year"), month_labels,
                        [(str(y), revenue_by_year[y]) for y in years if y in revenue_by_year], currency, wide=True),
            self._chart('years_harvest_month', 'line', self.env._("Monthly harvest, year over year"), month_labels,
                        [(str(y), harvest_by_year[y]) for y in years if y in harvest_by_year], 'kg', wide=True),
            self._chart('years_yield', 'bar', self.env._("Yield per year"), labels,
                        [(self.env._("Yield"), ratio('harvest', 'area'))], 'kg/m²'),
            self._chart('years_hours', 'bar', self.env._("Work hours per year"), labels,
                        [(self.env._("Hours"), per_year('hours'))], 'h'),
            self._chart('years_area', 'stacked', self.env._("Cultivated area per year, by botanical family"), labels,
                        [(families.get(f, f), [family_area[f][y] for y in years]) for f in sorted(family_area)], 'm²'),
            self._chart('years_species_margin', 'bar', self.env._("Margin per species, year over year"), top,
                        [(str(y), [species[s][y]['margin'] for s in top]) for y in years], currency, wide=True),
            self._chart('years_species_yield', 'bar', self.env._("Yield per species, year over year"), top,
                        [(str(y), [species[s][y]['harvest'] / species[s][y]['area'] if species[s][y]['area'] else 0.0
                                   for s in top]) for y in years], 'kg/m²', wide=True),
        ]
        return kpis, charts
