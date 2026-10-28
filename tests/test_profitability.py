from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tests.common import new_test_user

from .test_revenue import GardenRevenueCase


@tagged('post_install', '-at_install')
class TestGardenProfitability(GardenRevenueCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.manager = new_test_user(cls.env, login='garden_profit_manager', groups='odoo_garden.group_garden_manager')
        cls.Profit = cls.env['garden.crop.profitability']
        cls.Profit.search([]).unlink()

    def _scenario(self):
        """Grande culture : 2 h à 20 €, 30 kg vendus 150 €. Petite : 1 h à 12 €, 10 kg vendus 50 €."""
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
        self.Profit.refresh()
        return self.Profit.search([('crop_id', 'in', (self.big | self.small).ids)])

    def test_one_line_per_crop_with_expected_content(self):
        lines = self._scenario()
        by_crop = {line.crop_id: line for line in lines}
        big, small = by_crop[self.big], by_crop[self.small]
        self.assertEqual(len(lines), 2)
        self.assertEqual((big.site_id, big.garden_id, big.bed_id), (self.site, self.garden, self.bed))
        self.assertEqual((big.species_id, big.variety_id, big.family), (self.solanaceae, self.variety, 'solanaceae'))
        self.assertEqual(big.season_id, self.season)
        self.assertAlmostEqual(big.area, 36.0)
        self.assertAlmostEqual(big.hours, 2.0)
        self.assertAlmostEqual(big.labour_cost, 40.0)
        self.assertAlmostEqual(big.input_cost, 10.0)
        self.assertAlmostEqual(big.harvested_qty, 30.0)
        self.assertAlmostEqual(big.revenue, 150.0)
        self.assertAlmostEqual(big.margin, 100.0)
        self.assertAlmostEqual(big.margin_per_hour, 50.0)
        self.assertAlmostEqual(big.margin_per_m2, 100.0 / 36.0, places=2)
        self.assertAlmostEqual(big.yield_per_m2, 30.0 / 36.0)
        self.assertAlmostEqual(big.expected_yield_qty, 36 * 8)
        self.assertAlmostEqual(big.expected_revenue, 36 * 8 * 5)
        self.assertAlmostEqual(big.yield_gap, 30.0 - 288.0)
        self.assertAlmostEqual(big.hours_gap, 2.0 - big.expected_hours)
        self.assertAlmostEqual(small.revenue, 50.0)
        self.assertAlmostEqual(small.margin, 50.0 - 12.0)
        self.assertEqual(big.occupation_days, self.big.occupation_days)

    def test_refresh_is_idempotent_and_follows_changes(self):
        self._scenario()
        count = self.Profit.search_count([])
        self.Profit.refresh()
        self.assertEqual(self.Profit.search_count([]), count)
        # une nouvelle facture change le chiffre d'affaires de la ligne
        self._invoice(self.tomato, 4, 5.0, '2027-07-31')  # 20 de plus, répartis 3/4 - 1/4
        self.Profit.refresh()
        line = self.Profit.search([('crop_id', '=', self.big.id)])
        self.assertAlmostEqual(line.revenue, 165.0)
        # une culture annulée sort du rapport, une nouvelle culture y entre
        self.small.state = 'cancelled'
        extra = self._crop(bed_id=self.bed2.id, planned_sowing_date='2028-03-01')
        self.Profit.refresh()
        self.assertFalse(self.Profit.search([('crop_id', '=', self.small.id)]))
        self.assertTrue(self.Profit.search([('crop_id', '=', extra.id)]))
        # supprimer la culture supprime la ligne
        extra.unlink()
        self.assertFalse(self.Profit.search([('crop_id', '=', extra.id)]))

    def test_ratios_are_weighted_in_groups(self):
        self._scenario()
        domain = [('crop_id', 'in', (self.big | self.small).ids)]
        total = self.Profit._read_group(
            domain, [], ['margin:sum', 'hours:sum', 'area:sum', 'harvested_qty:sum', 'margin_per_hour:avg',
                         'margin_per_m2:avg', 'yield_per_m2:avg', 'loss_rate:avg'],
        )[0]
        margin, hours, area, harvested, per_hour, per_m2, per_area, loss = total
        self.assertAlmostEqual(per_hour, margin / hours)
        self.assertAlmostEqual(per_m2, margin / area)
        self.assertAlmostEqual(per_area, harvested / area)
        self.assertAlmostEqual(loss, 0.0)
        # moyenne simple des ratios (50 et 38) différente du ratio pondéré (138 / 3)
        self.assertAlmostEqual(per_hour, 138.0 / 3.0)

    def test_loss_rate(self):
        self._harvest(self.big, 30.0, date='2027-07-05')
        self.env['garden.loss'].create({'crop_id': self.big.id, 'quantity': 10.0, 'date': '2027-07-06'})
        self.Profit.refresh()
        line = self.Profit.search([('crop_id', '=', self.big.id)])
        self.assertAlmostEqual(line.loss_rate, 0.25)
        grouped = self.Profit._read_group([('crop_id', '=', self.big.id)], [], ['loss_rate:avg'])
        self.assertAlmostEqual(grouped[0][0], 0.25)

    def test_access_is_manager_read_only(self):
        self._scenario()
        line = self.Profit.search([('crop_id', '=', self.big.id)])
        self.assertTrue(line.with_user(self.manager).read(['margin']))
        for user in (self.worker, self.chef):
            with self.assertRaises(AccessError):
                line.with_user(user).read(['margin'])
            with self.assertRaises(AccessError):
                self.Profit.with_user(user).search([])
        with self.assertRaises(AccessError):
            line.with_user(self.manager).write({'margin': 1})
        with self.assertRaises(AccessError):
            line.with_user(self.manager).unlink()
        with self.assertRaises(AccessError):
            self.Profit.with_user(self.manager).create({'crop_id': self.big.id})

    def test_multi_company_rule(self):
        rule = self.env.ref('odoo_garden.garden_crop_profitability_company_rule')
        self.assertEqual(rule.model_id.model, 'garden.crop.profitability')
        self.assertIn('company_ids', rule.domain_force)

    def test_open_action_refreshes(self):
        action = self.Profit.with_user(self.manager).action_open()
        self.assertEqual(action['res_model'], 'garden.crop.profitability')
        self.assertTrue(self.Profit.search([('crop_id', '=', self.big.id)]))
        server_action = self.env.ref('odoo_garden.action_garden_profitability_open')
        self.assertEqual(server_action.model_id.model, 'garden.crop.profitability')
        cron = self.env.ref('odoo_garden.ir_cron_garden_profitability')
        self.assertEqual(cron.interval_type, 'days')
        cron.method_direct_trigger()
