from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import tagged

from odoo.addons.farmer_power.tests.test_revenue import GardenRevenueCase


class GardenPosCase(GardenRevenueCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.pos_config = cls.env['pos.config'].create({'name': 'Market'})
        cls.session = cls.env['pos.session'].create({'config_id': cls.pos_config.id})
        cls.session.action_pos_session_open()

    def _pos_order(self, lines, date='2027-07-20 10:00:00', state='paid', partner=None, **vals):
        """Order with lines ``(product, qty, unit price[, [lot names]])``; ``state`` is forced (paid / done / draft...)."""
        order_lines, total = [], 0.0
        for product, qty, price, *lots in lines:
            subtotal = qty * price
            total += subtotal
            order_lines.append(Command.create({
                'name': product.name, 'product_id': product.id, 'qty': qty, 'price_unit': price,
                'price_subtotal': subtotal, 'price_subtotal_incl': subtotal,
                'pack_lot_ids': [Command.create({'lot_name': name}) for name in (lots[0] if lots else [])],
            }))
        order = self.env['pos.order'].create(dict({
            'session_id': self.session.id, 'config_id': self.pos_config.id, 'company_id': self.env.company.id,
            'partner_id': partner.id if partner else False, 'date_order': date,
            'amount_tax': 0.0, 'amount_total': total, 'amount_paid': total, 'amount_return': 0.0,
            'lines': order_lines,
        }, **vals))
        order.state = state
        return order


@tagged('post_install', '-at_install')
class TestGardenPosProrata(GardenPosCase):

    def test_pos_sale_is_split_by_monthly_harvest(self):
        self._harvest(self.big, 30.0, date='2027-07-05')
        self._harvest(self.small, 10.0, date='2027-07-25')
        self._pos_order([(self.tomato, 8, 5.0)])  # 40.00 at the July market
        revenue = self._revenue(self.big, self.small)
        self.assertAlmostEqual(revenue[self.big], 30.0)
        self.assertAlmostEqual(revenue[self.small], 10.0)
        self.assertEqual(self.big.sale_line_count, 1)

    def test_invoice_and_pos_add_up(self):
        self._harvest(self.big, 30.0, date='2027-07-05')
        self._invoice(self.tomato, 10, 5.0, '2027-07-31')
        self._pos_order([(self.tomato, 4, 5.0)])
        self.assertAlmostEqual(self._revenue(self.big)[self.big], 70.0)
        self.assertEqual(self.big.sale_line_count, 2)

    def test_month_without_harvest_is_not_attributed(self):
        self._harvest(self.big, 30.0, date='2027-07-05')
        self._pos_order([(self.tomato, 4, 5.0)], date='2027-08-10 10:00:00')
        self.assertAlmostEqual(self._revenue(self.big)[self.big], 0.0)

    def test_only_paid_or_posted_orders(self):
        self._harvest(self.big, 30.0, date='2027-07-05')
        self._pos_order([(self.tomato, 1, 5.0)], state='draft')
        self._pos_order([(self.tomato, 1, 7.0)], state='cancel')
        self.assertAlmostEqual(self._revenue(self.big)[self.big], 0.0)
        self._pos_order([(self.tomato, 1, 3.0)], state='paid')
        self._pos_order([(self.tomato, 1, 2.0)], state='done')
        self.assertAlmostEqual(self._revenue(self.big)[self.big], 5.0)

    def test_refund_is_negative(self):
        self._harvest(self.big, 30.0, date='2027-07-05')
        self._pos_order([(self.tomato, 4, 5.0)])
        refund = self._pos_order([(self.tomato, -1, 5.0)], date='2027-07-22 10:00:00')
        self.assertAlmostEqual(self._revenue(self.big)[self.big], 15.0)
        crop_sale = self.env['garden.crop.sale']
        action = crop_sale._open_for(self.big)
        rows = crop_sale.search(action['domain'])
        self.assertEqual(sorted(rows.mapped('amount')), [-5.0, 20.0])
        self.assertTrue(rows.filtered('is_refund').invoice_name == (refund.pos_reference or refund.name))

    def test_invoiced_pos_order_is_not_counted_twice(self):
        """A POS order with a posted invoice is counted by the invoice line only (pro rata method)."""
        self._harvest(self.big, 30.0, date='2027-07-05')
        invoice = self._invoice(self.tomato, 4, 5.0, '2027-07-20')
        order = self._pos_order([(self.tomato, 4, 5.0)], state='done', account_move=invoice.id)
        self.assertAlmostEqual(self._revenue(self.big)[self.big], 20.0)  # not 40
        self.assertEqual(self.big.sale_line_count, 1)
        # an order whose invoice is only a draft is still counted by the POS bridge
        draft_invoice = self._invoice(self.tomato, 1, 1.0, '2027-07-21', post=False)
        order.account_move = draft_invoice
        self.assertAlmostEqual(self._revenue(self.big)[self.big], 40.0)

    def test_company_currency_amount(self):
        self._harvest(self.big, 30.0, date='2027-07-05')
        self._pos_order([(self.tomato, 2, 5.0)])
        self.assertAlmostEqual(self._revenue(self.big)[self.big], 10.0)


@tagged('post_install', '-at_install')
class TestGardenPosTotals(GardenPosCase):
    """The aggregated totals (used to compute the revenue of thousands of crops) must equal the entries."""

    def _assert_totals_match_entries(self, crops, method):
        Revenue = self.env['garden.revenue']
        totals = Revenue.get_extra_totals(crops, method)
        entries = Revenue.get_extra_entries(crops, method)
        for crop in crops:
            amount, count = totals.get(crop.id, (0.0, 0))
            crop_entries = entries.get(crop.id, [])
            self.assertEqual(count, len(crop_entries))
            self.assertAlmostEqual(amount, sum(entry['amount'] for entry in crop_entries))

    def test_prorata_totals_match_entries(self):
        self._harvest(self.big, 30.0, date='2027-07-05')
        self._harvest(self.small, 10.0, date='2027-07-25')
        self._pos_order([(self.tomato, 8, 5.0)])
        self._pos_order([(self.tomato, 3, 4.0), (self.tomato, -1, 4.0)], date='2027-07-22 10:00:00')
        self._pos_order([(self.tomato, 5, 3.0)], date='2027-08-02 10:00:00')  # month without harvest
        crops = self.big | self.small
        self._assert_totals_match_entries(crops, 'prorata')
        self.assertAlmostEqual(self.env['garden.revenue'].get_revenue(crops, 'prorata')[self.big.id], 48.0 * 0.75)

    def test_lot_totals_match_entries(self):
        self._harvest(self.big, 20.0, date='2027-07-05')
        self._harvest(self.small, 5.0, date='2027-07-05')
        self._pos_order([(self.tomato, 4, 5.0, [self.big.lot_ids.name, self.small.lot_ids.name, 'UNKNOWN'])])
        self._assert_totals_match_entries(self.big | self.small, 'lot')


@tagged('post_install', '-at_install')
class TestGardenPosLot(GardenPosCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.set_method('lot')

    def _crop_lot_name(self, crop, qty=20.0):
        self._harvest(crop, qty, date='2027-07-05')
        return crop.lot_ids.name

    def test_lot_entered_on_pos_line(self):
        small_harvest = self._harvest(self.small, 5.0, date='2027-07-05')
        lot_big = self._crop_lot_name(self.big)
        lot_small = self.small.lot_ids.name
        self.assertTrue(small_harvest)
        self._pos_order([(self.tomato, 3, 6.0, [lot_big])])
        self._pos_order([(self.tomato, 2, 6.0, [lot_small])])
        revenue = self._revenue(self.big, self.small)
        self.assertAlmostEqual(revenue[self.big], 18.0)
        self.assertAlmostEqual(revenue[self.small], 12.0)

    def test_lot_split_and_unknown_lot(self):
        lot_big = self._crop_lot_name(self.big)
        self._pos_order([(self.tomato, 4, 5.0, [lot_big, 'UNKNOWN-LOT'])])  # 20.00, half to the crop
        self.assertAlmostEqual(self._revenue(self.big)[self.big], 10.0)
        self._pos_order([(self.tomato, 1, 5.0)])  # no lot: not attributed
        self.assertAlmostEqual(self._revenue(self.big)[self.big], 10.0)

    def test_refund_by_lot_is_negative(self):
        lot_big = self._crop_lot_name(self.big)
        self._pos_order([(self.tomato, 3, 6.0, [lot_big])])
        self._pos_order([(self.tomato, -1, 6.0, [lot_big])], date='2027-07-22 10:00:00')
        self.assertAlmostEqual(self._revenue(self.big)[self.big], 12.0)

    def test_invoiced_pos_order_by_lot_is_counted_once(self):
        lot_big = self._crop_lot_name(self.big)
        invoice = self._invoice(self.tomato, 3, 6.0, '2027-07-20')  # no sale order: not attributable by lot
        self._pos_order([(self.tomato, 3, 6.0, [lot_big])], state='done', account_move=invoice.id)
        self.assertAlmostEqual(self._revenue(self.big)[self.big], 18.0)
        self.assertEqual(self.big.sale_line_count, 1)

    def test_lot_of_another_product_is_ignored(self):
        lot_big = self._crop_lot_name(self.big)
        self._pos_order([(self.carrot, 3, 6.0, [lot_big])])
        self.assertAlmostEqual(self._revenue(self.big)[self.big], 0.0)


@tagged('post_install', '-at_install')
class TestGardenPosReports(GardenPosCase):

    def _july_revenue(self):
        data = self.env['garden.crop.profitability'].get_dashboard_data()
        return {row['label']: row['value'] for row in data['monthly_revenue']}.get('2027-07', 0.0)

    def test_profitability_and_sales_button(self):
        self._harvest(self.big, 30.0, date='2027-07-05')
        before = self._july_revenue()  # the demo data, if installed, already has July revenue
        self._pos_order([(self.tomato, 8, 5.0)])
        self.env['garden.crop.profitability'].refresh()
        line = self.env['garden.crop.profitability'].search([('crop_id', '=', self.big.id)])
        self.assertAlmostEqual(line.revenue, 40.0)
        self.assertAlmostEqual(line.margin, 40.0 - self.big.labour_cost - self.big.input_cost)
        self.assertAlmostEqual(self._july_revenue() - before, 40.0)
        action = self.env['garden.crop.sale']._open_for(self.big)
        rows = self.env['garden.crop.sale'].search(action['domain'])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows.product_id, self.tomato)
        self.assertAlmostEqual(rows.amount, 40.0)
        self.assertAlmostEqual(rows.share, 100.0)

    def test_crop_manager_sees_amounts_not_orders(self):
        chef = self.chef
        self._harvest(self.big, 30.0, date='2027-07-05')
        self._pos_order([(self.tomato, 8, 5.0)])
        crop = self.big.with_user(chef)
        crop.invalidate_recordset()
        self.assertAlmostEqual(crop.revenue, 40.0)
        action = crop.action_view_sales()
        rows = self.env['garden.crop.sale'].with_user(chef).search(action['domain'])
        self.assertEqual(len(rows), 1)
        with self.assertRaises(AccessError):
            self.env['pos.order'].with_user(chef).search([])
        with self.assertRaises(AccessError):
            self.env['pos.order.line'].with_user(chef).search([])
