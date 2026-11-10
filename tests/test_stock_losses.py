from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from .test_stock_harvest import GardenHarvestCase


@tagged('post_install', '-at_install')
class TestGardenLoss(GardenHarvestCase):

    def _loss(self, crop, **vals):
        vals.setdefault('quantity', 2.0)
        return self.env['garden.loss'].create(dict({'crop_id': crop.id}, **vals))

    def test_defaults(self):
        crop = self._crop(planned_sowing_date='2027-03-01')
        loss = self._loss(crop)
        self.assertEqual(loss.stage, 'pre_harvest')
        self.assertEqual(loss.product_id, self.tomato)
        self.assertEqual(loss.uom_id, self.tomato.uom_id)
        self.assertEqual(loss.bed_id, crop.bed_id)
        self.assertEqual(loss.company_id, crop.company_id)
        self.assertEqual(loss.date, self.env['garden.loss']._fields['date'].default(loss))
        self.assertFalse(loss.scrap_id)
        self.assertEqual(crop.loss_count, 1)

    def test_pre_harvest_loss_has_no_stock_effect(self):
        crop = self._crop(planned_sowing_date='2027-03-01')
        self._harvest(crop, 10.0)
        lot = crop.lot_ids
        self._loss(crop, quantity=3.0, cause='disease')
        self.assertEqual(self._qty(self.tomato, lot), 10.0)
        self.assertEqual(self.env['stock.scrap'].search_count([('product_id', '=', self.tomato.id)]), 0)

    def test_post_harvest_loss_scraps_crop_lot(self):
        crop = self._crop(planned_sowing_date='2027-03-01')
        self._harvest(crop, 10.0)
        lot = crop.lot_ids
        loss = self._loss(crop, stage='post_harvest', quantity=2.5, cause='unsold', date='2027-07-20')
        scrap = loss.scrap_id
        self.assertEqual(scrap.state, 'done')
        self.assertEqual(scrap.lot_id, lot)
        self.assertEqual(scrap.product_id, self.tomato)
        self.assertEqual(scrap.scrap_qty, 2.5)
        self.assertEqual(scrap.location_id, self.stock_location)
        self.assertEqual(loss.lot_id, lot)
        self.assertEqual(self._qty(self.tomato, lot), 7.5)
        self.assertEqual(str(scrap.move_ids.date.date()), '2027-07-20')
        # les pertes verrouillent le rebut
        with self.assertRaises(UserError):
            loss.quantity = 1.0
        loss.write({'notes': 'Écrasées', 'cause': 'other'})
        with self.assertRaises(UserError):
            loss.unlink()

    def test_post_harvest_without_lot_product(self):
        crop = self._crop(template_id=self.template_direct.id, planned_sowing_date='2027-03-01')
        self._harvest(crop, 6.0)
        loss = self._loss(crop, stage='post_harvest', quantity=1.0)
        self.assertFalse(loss.scrap_id.lot_id)
        self.assertEqual(self._qty(self.carrot), 5.0)

    def test_post_harvest_needs_a_harvest_and_stock(self):
        crop = self._crop(planned_sowing_date='2027-03-01')
        with self.assertRaises(UserError):  # aucun lot encore
            self._loss(crop, stage='post_harvest')
        self._harvest(crop, 2.0)
        with self.assertRaises(UserError):  # plus que le stock du lot
            self._loss(crop, stage='post_harvest', quantity=5.0)
        # le produit est obligatoire
        crop2 = self._crop(bed_id=self.bed2.id, template_id=self.template_direct.id, planned_sowing_date='2027-03-01')
        self.variety_cabbage.harvest_product_id = False
        with self.assertRaises(UserError):
            self._loss(crop2, stage='post_harvest')

    def test_switching_stage_creates_scrap(self):
        crop = self._crop(planned_sowing_date='2027-03-01')
        self._harvest(crop, 10.0)
        loss = self._loss(crop, quantity=1.0)
        self.assertFalse(loss.scrap_id)
        loss.stage = 'post_harvest'
        self.assertTrue(loss.scrap_id)
        self.assertEqual(self._qty(self.tomato, crop.lot_ids), 9.0)

    def test_loss_rate(self):
        crop = self._crop(planned_sowing_date='2027-03-01')
        self.assertEqual(crop.loss_rate, 0.0)
        self._loss(crop, quantity=5.0)  # sans récolte : tout est perdu
        self.assertAlmostEqual(crop.loss_rate, 1.0)
        self._harvest(crop, 15.0)
        self.assertAlmostEqual(crop.loss_qty, 5.0)
        self.assertAlmostEqual(crop.loss_rate, 5.0 / 20.0)
        self._loss(crop, stage='post_harvest', quantity=5.0)
        self.assertAlmostEqual(crop.loss_qty, 10.0)
        self.assertAlmostEqual(crop.loss_rate, 10.0 / 25.0)

    def test_loss_quantity_converted_to_product_unit(self):
        gram = self.env['uom.uom'].create({
            'name': 'g perte', 'relative_uom_id': self.tomato.uom_id.id, 'relative_factor': 0.001,
        })
        crop = self._crop(planned_sowing_date='2027-03-01')
        self._harvest(crop, 9.0)
        loss = self._loss(crop, quantity=1000.0, uom_id=gram.id)
        self.assertAlmostEqual(loss.quantity_ref, 1.0)
        self.assertAlmostEqual(crop.loss_rate, 1.0 / 10.0)

    def test_quantity_must_be_positive(self):
        crop = self._crop(planned_sowing_date='2027-03-01')
        from odoo.tools import mute_logger
        with mute_logger('odoo.sql_db'), self.assertRaises(Exception), self.cr.savepoint():
            self._loss(crop, quantity=0.0)

    def test_worker_declares_losses_without_stock_access(self):
        crop = self._crop(planned_sowing_date='2027-03-01')
        self._harvest(crop, 10.0)
        loss = self.env['garden.loss'].with_user(self.worker).create({
            'crop_id': crop.id, 'stage': 'post_harvest', 'quantity': 1.0, 'cause': 'unsold',
        })
        self.assertTrue(loss.sudo().scrap_id)
        self.assertEqual(self._qty(self.tomato, crop.lot_ids), 9.0)
        loss.write({'notes': 'ok'})
        with self.assertRaises(AccessError):
            loss.unlink()
        with self.assertRaises(AccessError):
            self.env['stock.scrap'].with_user(self.worker).search([])

    def test_multi_company_rule(self):
        company2 = self.env['res.company'].create({'name': 'Autre ferme perte'})
        farm2 = self.env['garden.farm'].create({'name': 'Ferme 2 perte', 'company_id': company2.id})
        site2 = self.env['garden.site'].create({'name': 'S2', 'farm_id': farm2.id})
        garden2 = self.env['garden.garden'].create({'name': 'G2', 'site_id': site2.id})
        bed2 = self.env['garden.bed'].create({'name': 'B2', 'garden_id': garden2.id})
        crop2 = self._crop(bed_id=bed2.id, planned_sowing_date='2027-03-01')
        loss2 = self._loss(crop2)
        self.assertEqual(loss2.company_id, company2)
        loss1 = self._loss(self._crop(planned_sowing_date='2027-03-01'))
        self.assertFalse(loss2.with_user(self.chef).search([('id', '=', loss2.id)]))
        self.assertTrue(loss1.with_user(self.chef).search([('id', '=', loss1.id)]))

    def test_views_and_action(self):
        action = self.env.ref('farmer_power.action_garden_loss')
        self.assertEqual(action.res_model, 'garden.loss')
        for view in ('list', 'form', 'pivot', 'search'):
            self.assertTrue(self.env.ref('farmer_power.view_garden_loss_%s' % ('tree' if view == 'list' else view)))
        crop = self._crop(planned_sowing_date='2027-03-01')
        act = crop.action_view_losses()
        self.assertEqual(act['domain'], [('crop_id', '=', crop.id)])
