from odoo.exceptions import AccessError
from odoo.tests import HttpCase, tagged
from odoo.tests.common import new_test_user

from .test_revenue import GardenRevenueCase

THEMES = ('occupation', 'crops', 'work', 'finance', 'years')


@tagged('post_install', '-at_install')
class TestGardenAnalytics(GardenRevenueCase):
    """Données des tableaux de bord thématiques (``garden.analytics``)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.manager = new_test_user(cls.env, login='garden_analytics_manager', groups='odoo_garden.group_garden_manager')
        cls.chef = new_test_user(cls.env, login='garden_analytics_chef', groups='odoo_garden.group_garden_chef')
        cls.worker = new_test_user(cls.env, login='garden_analytics_worker', groups='odoo_garden.group_garden_worker')
        cls.Analytics = cls.env['garden.analytics']
        cls.Profit = cls.env['garden.crop.profitability']

    def setUp(self):
        super().setUp()
        self.Profit.search([]).unlink()
        self._operation(
            crop_ids=[(6, 0, self.big.ids)], employee_ids=[(6, 0, self.alice.ids)], duration=2.0, date='2027-04-15',
            input_ids=[(0, 0, {'product_id': self.fertilizer.id, 'quantity': 5})],
        ).action_done()
        self._operation(
            crop_ids=[(6, 0, self.small.ids)], employee_ids=[(6, 0, self.bob.ids)], duration=1.0, date='2027-04-15',
        ).action_done()
        self._harvest(self.big, 30.0, date='2027-07-05')
        self._harvest(self.small, 10.0, date='2027-07-25')
        self._invoice(self.tomato, 40, 5.0, '2027-07-31')

    def _chart(self, data, chart_id):
        return next(chart for chart in data['charts'] if chart['id'] == chart_id)

    def test_every_theme_returns_well_formed_data(self):
        for theme in THEMES:
            data = self.Analytics.with_user(self.manager).get_data(theme, year=2027, refresh=True)
            self.assertEqual((data['theme'], data['year']), (theme, 2027))
            self.assertIn(2027, data['years'])
            self.assertTrue(data['kpis'], theme)
            self.assertTrue(data['charts'], theme)
            for chart in data['charts']:
                self.assertIn(chart['type'], ('bar', 'stacked', 'line', 'hbar', 'donut'), chart['id'])
                for series in chart['series']:
                    self.assertEqual(len(series['values']), len(chart['labels']), chart['id'])
            ids = [chart['id'] for chart in data['charts']]
            self.assertEqual(len(ids), len(set(ids)), theme)

    def test_occupation_rate_follows_the_crops(self):
        data = self.Analytics.get_data('occupation', year=2027)
        rate = self._chart(data, 'occupation_rate')
        self.assertEqual(len(rate['labels']), 12)
        values = rate['series'][0]['values']
        self.assertTrue(all(0 <= value <= 100 for value in values))
        start = self.big.occupation_start
        self.assertEqual(start.year, 2027)
        self.assertGreater(values[start.month - 1], 0)
        self.assertEqual(values[start.month - 2] if start.month > 1 else 0, 0)

    def test_finance_totals_match_the_profitability_report(self):
        data = self.Analytics.with_user(self.manager).get_data('finance', year=2027, refresh=True)
        kpis = {kpi['label']: kpi['value'] for kpi in data['kpis']}
        lines = self.Profit.search([('crop_id', 'in', (self.big | self.small).ids)])
        self.assertTrue(lines)
        monthly = self._chart(data, 'finance_monthly')
        revenue = dict((s['name'], s['values']) for s in monthly['series'])['Revenue']
        self.assertAlmostEqual(revenue[6], 200.0, places=1)  # facture de juillet : 40 × 5
        margin = self._chart(data, 'finance_margin')
        self.assertTrue(margin['labels'])
        self.assertEqual(kpis['Revenue'], round(sum(self.Profit.search([('date', '>=', '2027-01-01'), ('date', '<=', '2027-12-31')]).mapped('revenue'))))

    def test_years_theme_compares_years(self):
        data = self.Analytics.with_user(self.manager).get_data('years', refresh=True)
        totals = self._chart(data, 'years_totals')
        self.assertIn('2027', totals['labels'])
        self.assertEqual({s['name'] for s in totals['series']}, {'Revenue', 'Costs', 'Margin'})
        harvest = self._chart(data, 'years_harvest_month')
        self.assertAlmostEqual(dict((s['name'], s['values']) for s in harvest['series'])['2027'][6], 40.0)

    def test_work_theme_counts_hours_and_status(self):
        data = self.Analytics.get_data('work', year=2027)
        hours = self._chart(data, 'work_hours')
        april = sum(series['values'][3] for series in hours['series'])
        self.assertAlmostEqual(april, 3.0)
        employees = self._chart(data, 'work_employee')
        self.assertEqual(sorted(employees['series'][0]['values']), [1.0, 2.0])

    def test_access_rights_per_theme(self):
        for theme in ('occupation', 'crops', 'work'):
            self.Analytics.with_user(self.chef).get_data(theme, year=2027)
            with self.assertRaises(AccessError):
                self.Analytics.with_user(self.worker).get_data(theme, year=2027)
        for theme in ('finance', 'years'):
            self.Analytics.with_user(self.manager).get_data(theme)
            with self.assertRaises(AccessError):
                self.Analytics.with_user(self.chef).get_data(theme)

    def test_unknown_theme_and_empty_database_year(self):
        with self.assertRaises(ValueError):
            self.Analytics.get_data('unknown')
        data = self.Analytics.get_data('occupation', year=1999)
        self.assertEqual(data['year'], data['years'][-1] if 1999 not in data['years'] else 1999)


@tagged('post_install', '-at_install')
class TestGardenAnalyticsTours(HttpCase):

    def test_dashboard_tours(self):
        farm = self.env['garden.farm'].create({'name': 'Ferme Analyse'})
        site = self.env['garden.site'].create({'name': 'Site Analyse', 'farm_id': farm.id})
        garden = self.env['garden.garden'].create({'name': 'Îlot Analyse', 'site_id': site.id})
        bed = self.env['garden.bed'].create({
            'name': 'Planche Analyse', 'code': 'ANA', 'garden_id': garden.id, 'length': 10, 'width': 1,
        })
        species = self.env['garden.species'].create({'name': 'Tomate analyse'})
        variety = self.env['garden.variety'].create({'name': 'Variété analyse', 'species_id': species.id})
        template = self.env['garden.crop.template'].create({'name': 'Tomate analyse', 'variety_id': variety.id})
        crop = self.env['garden.crop'].create({
            'template_id': template.id, 'bed_id': bed.id, 'planned_sowing_date': '2027-03-01',
        })
        self.env['garden.operation'].create({
            'type_id': self.env.ref('odoo_garden.operation_type_weeding').id,
            'crop_ids': [(6, 0, crop.ids)], 'duration': 2.0, 'date': '2027-04-01', 'state': 'done',
        })
        for theme in THEMES:
            self.start_tour(
                '/odoo/action-odoo_garden.action_garden_analytics_%s' % theme, 'garden_analytics_tour', login='admin',
            )
