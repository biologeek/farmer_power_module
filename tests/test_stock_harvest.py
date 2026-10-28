from odoo.exceptions import UserError
from odoo.tests import tagged

from .test_stock_inputs import GardenStockCase


class GardenHarvestCase(GardenStockCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tomato = cls._storable('Tomate récolte (kg)', tracking='lot')
        cls.carrot = cls._storable('Carotte récolte (kg)')  # sans suivi par lots
        cls.variety.harvest_product_id = cls.tomato
        cls.variety_cabbage.harvest_product_id = cls.carrot

    def _harvest(self, crops, qty, **vals):
        vals.setdefault('date', '2027-07-15')
        operation = self._operation(
            type_id=self.type_harvest.id, crop_ids=[(6, 0, crops.ids)], harvest_qty=qty, **vals,
        )
        operation.action_done()
        return operation


@tagged('post_install', '-at_install')
class TestGardenHarvest(GardenHarvestCase):

    def test_harvest_enters_stock_with_crop_lot(self):
        crop = self._crop(planned_sowing_date='2027-03-01')
        operation = self._harvest(crop, 12.5)
        move = operation.move_ids
        self.assertEqual(len(move), 1)
        self.assertEqual(move.state, 'done')
        self.assertEqual(move.garden_kind, 'harvest')
        self.assertEqual(move.location_id, self.production_location)
        self.assertEqual(move.location_dest_id, self.stock_location)
        self.assertEqual(move.product_id, self.tomato)
        self.assertEqual(move.garden_crop_id, crop)
        self.assertEqual(str(move.date.date()), '2027-07-15')
        lot = move.move_line_ids.lot_id
        self.assertEqual(lot.name, crop.name)
        self.assertEqual(lot.garden_crop_id, crop)
        self.assertEqual(crop.lot_ids, lot)
        self.assertEqual(crop.lot_count, 1)
        self.assertEqual(self._qty(self.tomato, lot), 12.5)
        self.assertAlmostEqual(crop.harvested_qty, 12.5)
        self.assertEqual(crop.harvest_move_ids, move)

    def test_product_without_lot_tracking(self):
        crop = self._crop(template_id=self.template_direct.id, planned_sowing_date='2027-03-01')
        operation = self._harvest(crop, 8.0)
        move = operation.move_ids
        self.assertFalse(move.move_line_ids.lot_id)
        self.assertFalse(crop.lot_ids)
        self.assertEqual(self._qty(self.carrot), 8.0)
        self.assertAlmostEqual(crop.harvested_qty, 8.0)

    def test_quantity_split_between_crops_by_allocation(self):
        big = self._crop(planned_sowing_date='2027-03-01')  # 36 m²
        small = self._crop(bed_id=self.bed2.id, planned_sowing_date='2027-03-01')  # 10 m²
        operation = self._harvest(big | small, 46.0)
        by_crop = {m.garden_crop_id: m for m in operation.move_ids}
        self.assertEqual(set(by_crop), {big, small})
        self.assertAlmostEqual(by_crop[big].quantity, 36.0)
        self.assertAlmostEqual(by_crop[small].quantity, 10.0)
        self.assertEqual(by_crop[big].move_line_ids.lot_id.name, big.name)
        self.assertEqual(by_crop[small].move_line_ids.lot_id.name, small.name)
        self.assertNotEqual(by_crop[big].move_line_ids.lot_id, by_crop[small].move_line_ids.lot_id)
        self.assertAlmostEqual(big.harvested_qty, 36.0)
        self.assertAlmostEqual(small.harvested_qty, 10.0)

    def test_rounding_remainder_goes_to_last_crop(self):
        bed3 = self.env['garden.bed'].create({'name': 'P3', 'code': 'P3', 'garden_id': self.garden.id, 'length': 10, 'width': 1})
        bed4 = self.env['garden.bed'].create({'name': 'P4', 'code': 'P4', 'garden_id': self.garden.id, 'length': 10, 'width': 1})
        crops = (
            self._crop(bed_id=self.bed2.id, planned_sowing_date='2027-03-01')
            | self._crop(bed_id=bed3.id, planned_sowing_date='2027-03-01')
            | self._crop(bed_id=bed4.id, planned_sowing_date='2027-03-01')
        )
        operation = self._harvest(crops, 10.0)
        self.assertAlmostEqual(sum(operation.move_ids.mapped('quantity')), 10.0)
        self.assertEqual(len(operation.move_ids), 3)
        self.assertAlmostEqual(sum(crops.mapped('harvested_qty')), 10.0)

    def test_bed_scope_harvest_uses_crops_in_place(self):
        a = self._crop(planned_sowing_date='2027-03-01', bed_share=50)
        b = self._crop(planned_sowing_date='2027-03-01', bed_share=50)
        operation = self._operation(
            type_id=self.type_harvest.id, scope='bed', bed_ids=[(6, 0, self.bed.ids)],
            harvest_product_id=self.tomato.id, harvest_qty=20.0, date='2027-06-15',
        )
        operation.action_done()
        self.assertAlmostEqual(a.harvested_qty, 10.0)
        self.assertAlmostEqual(b.harvested_qty, 10.0)

    def test_second_harvest_reuses_lot(self):
        crop = self._crop(planned_sowing_date='2027-03-01')
        self._harvest(crop, 5.0)
        self._harvest(crop, 7.0, date='2027-07-20')
        self.assertEqual(len(crop.lot_ids), 1)
        self.assertEqual(self._qty(self.tomato, crop.lot_ids), 12.0)
        self.assertAlmostEqual(crop.harvested_qty, 12.0)
        self.assertEqual(len(crop.harvest_move_ids), 2)

    def test_reopen_reverses_harvest(self):
        crop = self._crop(planned_sowing_date='2027-03-01')
        operation = self._harvest(crop, 9.0)
        lot = crop.lot_ids
        move = operation.move_ids
        operation.action_reset_planned()
        self.assertAlmostEqual(crop.harvested_qty, 0.0)
        self.assertEqual(self._qty(self.tomato, lot), 0.0)
        reverse = move.garden_reversal_ids
        self.assertEqual(reverse.garden_kind, 'harvest_return')
        self.assertEqual((reverse.location_id, reverse.location_dest_id), (self.stock_location, self.production_location))
        self.assertEqual(len(crop.harvest_move_ids), 2)
        # nouvelle validation : une nouvelle entrée en stock
        operation.action_done()
        self.assertAlmostEqual(crop.harvested_qty, 9.0)
        self.assertEqual(self._qty(self.tomato, lot), 9.0)

    def test_done_harvest_is_locked(self):
        crop = self._crop(planned_sowing_date='2027-03-01')
        operation = self._harvest(crop, 9.0)
        with self.assertRaises(UserError):
            operation.harvest_qty = 10.0
        with self.assertRaises(UserError):
            operation.crop_ids = crop | self._crop(bed_id=self.bed2.id)
        operation.action_reset_planned()
        operation.harvest_qty = 10.0
        operation.action_done()
        self.assertAlmostEqual(crop.harvested_qty, 10.0)

    def test_harvest_requires_product(self):
        crop = self._crop(planned_sowing_date='2027-03-01')
        operation = self._operation(type_id=self.type_harvest.id, crop_ids=[(6, 0, crop.ids)], harvest_qty=3.0)
        operation.harvest_product_id = False
        with self.assertRaises(UserError):
            operation.action_done()

    def test_no_crop_in_place(self):
        # produit suivi par lots : impossible de nommer le lot
        operation = self._operation(
            type_id=self.type_harvest.id, scope='bed', bed_ids=[(6, 0, self.bed2.ids)],
            harvest_product_id=self.tomato.id, harvest_qty=4.0, date='2027-07-15',
        )
        with self.assertRaises(UserError):
            operation.action_done()
        # produit sans lot : l'entrée en stock se fait sans culture
        operation.harvest_product_id = self.carrot
        operation.action_done()
        self.assertEqual(len(operation.move_ids), 1)
        self.assertFalse(operation.move_ids.garden_crop_id)
        self.assertEqual(self._qty(self.carrot), 4.0)

    def test_other_unit_converted_to_product_unit(self):
        gram = self.env['uom.uom'].create({
            'name': 'g récolte', 'relative_uom_id': self.carrot.uom_id.id, 'relative_factor': 0.001,
        })
        crop = self._crop(template_id=self.template_direct.id, planned_sowing_date='2027-03-01')
        operation = self._operation(
            type_id=self.type_harvest.id, crop_ids=[(6, 0, crop.ids)], harvest_qty=2500.0,
            harvest_uom_id=gram.id, date='2027-07-15',
        )
        operation.action_done()
        self.assertAlmostEqual(self._qty(self.carrot), 2.5)
        self.assertAlmostEqual(crop.harvested_qty, 2.5)

    def test_production_statistics_use_harvested_qty(self):
        crop = self._crop(planned_sowing_date='2027-03-01', date_start='2027-03-05')
        self._harvest(crop, 12.0)
        data = self.env['garden.crop'].get_production_statistics_data()
        beds = {row['bed']: row for row in data['bed_totals']}
        self.assertAlmostEqual(beds[self.bed.name]['quantity'], 12.0)
        months = {row['period']: row for row in data['month_totals']}
        self.assertAlmostEqual(months['2027-03']['quantity'], 12.0)
        crops = {row['crop']: row for row in data['crop_totals']}
        self.assertAlmostEqual(crops[self.template.name]['quantity'], 12.0)
        for rows in data.values():
            self.assertTrue(all('value' not in row for row in rows))

    def test_worker_harvests_without_stock_access(self):
        crop = self._crop(planned_sowing_date='2027-03-01')
        operation = self.env['garden.operation'].with_user(self.worker).create({
            'type_id': self.type_harvest.id, 'crop_ids': [(6, 0, crop.ids)], 'harvest_qty': 6.0, 'date': '2027-07-15',
        })
        operation.action_done()
        self.assertAlmostEqual(crop.harvested_qty, 6.0)
        # l'ouvrier voit la quantité récoltée et les lots, pas les mouvements
        as_worker = crop.with_user(self.worker)
        self.assertAlmostEqual(as_worker.harvested_qty, 6.0)
        self.assertTrue(as_worker.lot_ids.read(['name', 'product_qty']))
        with self.assertRaises(Exception):
            as_worker.harvest_move_ids.read(['state'])
