from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import tagged

from .test_stock_harvest import GardenHarvestCase


class GardenRevenueCase(GardenHarvestCase):
    """Fixtures de ventes (phase 5) : clients, factures, commandes livrées par lot."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.customer = cls.env['res.partner'].create({'name': 'Client rentabilité'})
        cls.customer_location = cls.env.ref('stock.stock_location_customers')
        cls.tomato.list_price = 5.0
        cls.carrot.list_price = 2.0
        crop_vals = {'template_id': cls.template.id, 'season_id': cls.season.id, 'planned_sowing_date': '2027-03-01'}
        cls.big = cls.env['garden.crop'].create(dict(crop_vals, bed_id=cls.bed.id))  # 36 m²
        cls.small = cls.env['garden.crop'].create(dict(crop_vals, bed_id=cls.bed2.id))  # 10 m²
        cls.set_method('prorata')

    @classmethod
    def set_method(cls, method):
        cls.env['ir.config_parameter'].sudo().set_param('odoo_garden.revenue_method', method)

    def _invoice(self, product, qty, price, date, move_type='out_invoice', currency=None, post=True):
        move = self.env['account.move'].create({
            'move_type': move_type, 'partner_id': self.customer.id, 'invoice_date': date,
            'currency_id': (currency or self.env.company.currency_id).id,
            'invoice_line_ids': [Command.create({
                'product_id': product.id, 'quantity': qty, 'price_unit': price, 'tax_ids': [Command.set([])],
            })],
        })
        if post:
            move.action_post()
        return move

    def _sell(self, product, qty, price, lots_qty, date='2027-07-20'):
        """Commande confirmée, livrée sur les lots indiqués ``{lot: quantité}`` puis facturée et comptabilisée."""
        order = self.env['sale.order'].create({
            'partner_id': self.customer.id,
            'order_line': [Command.create({
                'product_id': product.id, 'product_uom_qty': qty, 'price_unit': price, 'tax_ids': [Command.set([])],
            })],
        })
        order.action_confirm()
        picking = order.picking_ids
        picking.action_assign()
        move = picking.move_ids
        move.move_line_ids.unlink()
        for lot, quantity in lots_qty.items():
            self.env['stock.move.line'].create({
                'move_id': move.id, 'picking_id': picking.id, 'product_id': product.id,
                'product_uom_id': product.uom_id.id, 'quantity': quantity, 'lot_id': lot.id,
                'location_id': picking.location_id.id, 'location_dest_id': picking.location_dest_id.id,
                'picked': True,
            })
        move.picked = True
        picking.button_validate()
        self.assertEqual(picking.state, 'done')
        invoice = order._create_invoices()
        invoice.invoice_date = date
        invoice.action_post()
        return order, invoice

    def _revenue(self, *crops):
        crops = self.env['garden.crop'].union(*crops)
        crops.invalidate_recordset()
        return {crop: crop.revenue for crop in crops}


@tagged('post_install', '-at_install')
class TestGardenRevenueProrata(GardenRevenueCase):

    def test_split_by_monthly_harvest(self):
        self._harvest(self.big, 30.0, date='2027-07-05')
        self._harvest(self.small, 10.0, date='2027-07-25')
        self._invoice(self.tomato, 40, 5.0, '2027-07-31')
        revenue = self._revenue(self.big, self.small)
        self.assertAlmostEqual(revenue[self.big], 150.0)
        self.assertAlmostEqual(revenue[self.small], 50.0)
        self.assertEqual(self.big.sale_line_count, 1)

    def test_month_without_harvest_is_not_attributed(self):
        self._harvest(self.big, 30.0, date='2027-07-05')
        self._invoice(self.tomato, 10, 5.0, '2027-08-10')  # pas de récolte en août
        self.assertAlmostEqual(self._revenue(self.big)[self.big], 0.0)
        self.assertEqual(self.big.sale_line_count, 0)
        # le mois de juillet, lui, est attribué
        self._invoice(self.tomato, 10, 5.0, '2027-07-10')
        self.assertAlmostEqual(self._revenue(self.big)[self.big], 50.0)

    def test_only_the_month_harvest_counts(self):
        self._harvest(self.big, 30.0, date='2027-06-05')
        self._harvest(self.small, 10.0, date='2027-07-05')
        self._invoice(self.tomato, 4, 5.0, '2027-06-30')
        self._invoice(self.tomato, 6, 5.0, '2027-07-01')
        revenue = self._revenue(self.big, self.small)
        self.assertAlmostEqual(revenue[self.big], 20.0)
        self.assertAlmostEqual(revenue[self.small], 30.0)

    def test_credit_note_reduces_revenue(self):
        self._harvest(self.big, 30.0, date='2027-07-05')
        self._harvest(self.small, 10.0, date='2027-07-25')
        self._invoice(self.tomato, 40, 5.0, '2027-07-31')
        self._invoice(self.tomato, 4, 5.0, '2027-07-31', move_type='out_refund')
        revenue = self._revenue(self.big, self.small)
        self.assertAlmostEqual(revenue[self.big], 135.0)
        self.assertAlmostEqual(revenue[self.small], 45.0)

    def test_only_posted_customer_invoices(self):
        self._harvest(self.big, 30.0, date='2027-07-05')
        draft = self._invoice(self.tomato, 10, 5.0, '2027-07-31', post=False)
        self.assertAlmostEqual(self._revenue(self.big)[self.big], 0.0)
        draft.action_post()
        self.assertAlmostEqual(self._revenue(self.big)[self.big], 50.0)
        draft.button_draft()
        self.assertAlmostEqual(self.big.revenue, 0.0)  # l'invalidation est automatique
        # une facture fournisseur du même produit ne compte pas
        bill = self.env['account.move'].create({
            'move_type': 'in_invoice', 'partner_id': self.customer.id, 'invoice_date': '2027-07-31',
            'invoice_line_ids': [Command.create({'product_id': self.tomato.id, 'quantity': 10, 'price_unit': 3.0})],
        })
        bill.action_post()
        self.assertAlmostEqual(self._revenue(self.big)[self.big], 0.0)

    def test_other_product_is_not_mixed(self):
        self._harvest(self.big, 30.0, date='2027-07-05')
        self._invoice(self.carrot, 10, 2.0, '2027-07-31')
        self.assertAlmostEqual(self._revenue(self.big)[self.big], 0.0)

    def test_harvest_reversal_is_deducted(self):
        operation = self._harvest(self.big, 30.0, date='2027-07-05')
        self._harvest(self.small, 10.0, date='2027-07-25')
        operation.action_reset_planned()  # annule la récolte de la grande culture
        self._invoice(self.tomato, 10, 5.0, '2027-07-31')
        revenue = self._revenue(self.big, self.small)
        self.assertAlmostEqual(revenue[self.big], 0.0)
        self.assertAlmostEqual(revenue[self.small], 50.0)

    def test_foreign_currency_converted_at_invoice_date(self):
        company_currency = self.env.company.currency_id
        other = self.env['res.currency'].with_context(active_test=False).search(
            [('name', 'in', ('EUR', 'USD')), ('id', '!=', company_currency.id)], limit=1,
        )
        other.active = True
        self.env['res.currency.rate'].create({
            'name': '2027-07-01', 'rate': 2.0, 'currency_id': other.id, 'company_id': self.env.company.id,
        })
        self._harvest(self.big, 30.0, date='2027-07-05')
        self._invoice(self.tomato, 10, 10.0, '2027-07-10', currency=other)  # 100 en devise = 50 en société
        self.assertAlmostEqual(self._revenue(self.big)[self.big], 50.0)

    def test_settings_default_and_parameter(self):
        self.env['ir.config_parameter'].sudo().search([('key', '=', 'odoo_garden.revenue_method')]).unlink()
        self.assertEqual(self.env['garden.revenue']._get_method(), 'prorata')
        self.set_method('lot')
        self.assertEqual(self.env['garden.revenue']._get_method(), 'lot')
        self.set_method('inconnu')
        self.assertEqual(self.env['garden.revenue']._get_method(), 'prorata')


@tagged('post_install', '-at_install')
class TestGardenRevenueByLot(GardenRevenueCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.set_method('lot')
        cls._harvest_all()

    @classmethod
    def _harvest_all(cls):
        for crop, qty in ((cls.big, 40.0), (cls.small, 20.0)):
            operation = cls._operation_cls(crop, qty)
            operation.action_done()
        cls.lot_big = cls.big.lot_ids
        cls.lot_small = cls.small.lot_ids

    @classmethod
    def _operation_cls(cls, crop, qty):
        return cls.env['garden.operation'].create({
            'type_id': cls.type_harvest.id, 'crop_ids': [(6, 0, crop.ids)], 'harvest_qty': qty,
            'date': '2027-07-15',
        })

    def test_invoice_split_between_lots_by_quantity(self):
        order, invoice = self._sell(self.tomato, 10, 4.0, {self.lot_big: 6, self.lot_small: 4})
        revenue = self._revenue(self.big, self.small)
        self.assertAlmostEqual(revenue[self.big], 24.0)
        self.assertAlmostEqual(revenue[self.small], 16.0)
        self.assertEqual(self.big.sale_line_count, 1)

    def test_non_crop_lot_is_ignored(self):
        foreign = self.env['stock.lot'].create({'name': 'ACHAT-1', 'product_id': self.tomato.id})
        self._set_stock(self.tomato, 20, foreign)
        self._sell(self.tomato, 10, 4.0, {self.lot_big: 5, foreign: 5})
        revenue = self._revenue(self.big, self.small)
        # la moitié livrée sur un lot étranger n'est attribuée à aucune culture
        self.assertAlmostEqual(revenue[self.big], 20.0)
        self.assertAlmostEqual(revenue[self.small], 0.0)

    def test_credit_note_follows_the_lots(self):
        order, invoice = self._sell(self.tomato, 10, 4.0, {self.lot_big: 6, self.lot_small: 4})
        credit = invoice._reverse_moves([{'invoice_date': '2027-08-01'}])
        credit.action_post()
        revenue = self._revenue(self.big, self.small)
        self.assertAlmostEqual(revenue[self.big], 0.0)
        self.assertAlmostEqual(revenue[self.small], 0.0)

    def test_invoice_without_order_is_not_attributed_by_lot(self):
        self._invoice(self.tomato, 10, 4.0, '2027-07-31')
        self.assertAlmostEqual(self._revenue(self.big)[self.big], 0.0)

    def test_two_invoices_on_the_same_delivery(self):
        order, invoice = self._sell(self.tomato, 10, 4.0, {self.lot_big: 10})
        self.assertAlmostEqual(self._revenue(self.big)[self.big], 40.0)
        self.assertAlmostEqual(self._revenue(self.small)[self.small], 0.0)

    def test_customer_return_reduces_delivered_quantity(self):
        order, invoice = self._sell(self.tomato, 10, 4.0, {self.lot_big: 6, self.lot_small: 4})
        picking = order.picking_ids
        wizard = self.env['stock.return.picking'].with_context(
            active_id=picking.id, active_model='stock.picking',
        ).create({})
        wizard.product_return_moves.quantity = 4
        return_picking = self.env['stock.picking'].browse(wizard.action_create_returns()['res_id'])
        return_picking.action_assign()
        return_picking.move_ids.move_line_ids.write({'lot_id': self.lot_small.id, 'quantity': 4})
        return_picking.move_ids.picked = True
        return_picking.button_validate()
        revenue = self._revenue(self.big, self.small)
        # quantités nettes livrées : 6 (grande culture), 0 (petite), total 6
        self.assertAlmostEqual(revenue[self.big], 40.0)
        self.assertAlmostEqual(revenue[self.small], 0.0)


@tagged('post_install', '-at_install')
class TestGardenIndicators(GardenRevenueCase):

    def test_margin_indicators(self):
        crop = self.big
        self._operation(
            crop_ids=[(6, 0, crop.ids)], employee_ids=[(6, 0, self.alice.ids)], duration=2.0,
            input_ids=[(0, 0, {'product_id': self.fertilizer.id, 'quantity': 5})], date='2027-04-15',
        ).action_done()
        self._harvest(crop, 30.0, date='2027-07-05')
        self._invoice(self.tomato, 30, 5.0, '2027-07-31')  # 150
        crop.invalidate_recordset()
        self.assertAlmostEqual(crop.labour_hours, 2.0 + 0)  # la récolte n'a pas de durée
        self.assertAlmostEqual(crop.labour_cost, 40.0)
        self.assertAlmostEqual(crop.input_cost, 10.0)
        self.assertAlmostEqual(crop.revenue, 150.0)
        self.assertAlmostEqual(crop.fixed_cost, 0.0)
        self.assertAlmostEqual(crop.margin, 100.0)
        self.assertAlmostEqual(crop.margin_per_hour, 50.0)
        self.assertAlmostEqual(crop.margin_per_m2, 100.0 / 36.0, places=2)

    def test_fixed_costs_when_enabled(self):
        crop = self.big
        self._harvest(crop, 30.0, date='2027-07-05')
        self._invoice(self.tomato, 30, 5.0, '2027-07-31')
        self.assertAlmostEqual(crop.fixed_cost, 0.0)
        self.env['ir.config_parameter'].sudo().set_param('odoo_garden.fixed_cost_per_m2', '73')
        crop.invalidate_recordset()
        self.assertTrue(crop.occupation_days > 0)
        expected = 73.0 * 36.0 * crop.occupation_days / 365.0
        self.assertAlmostEqual(crop.fixed_cost, expected)
        self.assertAlmostEqual(crop.margin, 150.0 - crop.labour_cost - crop.input_cost - expected)

    def test_zero_denominators(self):
        crop = self.small
        self.assertEqual((crop.margin_per_hour, crop.revenue), (0.0, 0.0))
        self.assertEqual(crop.margin_per_m2, 0.0)

    def test_expected_vs_actual(self):
        crop = self.big
        self.assertAlmostEqual(crop.expected_yield_qty, 36 * 8)
        self.assertAlmostEqual(crop.expected_revenue, 36 * 8 * 5)
        self._harvest(crop, 100.0, date='2027-07-05')
        self._invoice(self.tomato, 100, 5.0, '2027-07-31')
        crop.invalidate_recordset()
        self.assertAlmostEqual(crop.yield_gap, 100.0 - 288.0)
        self.assertAlmostEqual(crop.revenue_gap, 500.0 - 1440.0)
        self.assertAlmostEqual(crop.hours_gap, crop.labour_hours - crop.expected_hours)
        self.assertAlmostEqual(crop.expected_hours, crop.area * sum(self.template.step_ids.mapped('expected_duration')))


@tagged('post_install', '-at_install')
class TestGardenRevenueSecurity(GardenRevenueCase):

    def test_worker_never_sees_costs_revenue_or_margin(self):
        self._harvest(self.big, 30.0, date='2027-07-05')
        self._invoice(self.tomato, 30, 5.0, '2027-07-31')
        as_worker = self.big.with_user(self.worker)
        for fname in ('revenue', 'margin', 'margin_per_hour', 'margin_per_m2', 'fixed_cost', 'revenue_gap',
                      'labour_cost', 'input_cost', 'sale_line_count'):
            with self.assertRaises(AccessError, msg=fname):
                as_worker.read([fname])
        # les heures et les écarts physiques restent visibles
        self.assertTrue(as_worker.read(['labour_hours', 'harvested_qty', 'yield_gap', 'hours_gap']))

    def test_chef_reads_revenue_without_accounting_access(self):
        self._harvest(self.big, 30.0, date='2027-07-05')
        invoice = self._invoice(self.tomato, 30, 5.0, '2027-07-31')
        as_chef = self.big.with_user(self.chef)
        self.assertAlmostEqual(as_chef.revenue, 150.0)
        self.assertTrue(as_chef.read(['margin', 'margin_per_hour']))
        with self.assertRaises(AccessError):
            invoice.with_user(self.chef).read(['name'])
        with self.assertRaises(AccessError):
            self.env['account.move.line'].with_user(self.chef).search([])
