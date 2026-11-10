from odoo import fields
from odoo.tests import tagged

from .test_stock_harvest import GardenHarvestCase


@tagged('post_install', '-at_install')
class TestGardenCropProgress(GardenHarvestCase):
    """Phase 5 (rattrapage §3.4 point 3) : l'état et les dates réelles suivent les opérations faites."""

    def _do(self, crop, type_xmlid, date, **vals):
        operation = self._operation(
            type_id=self.env.ref('farmer_power.' + type_xmlid).id, crop_ids=[(6, 0, crop.ids)], **vals,
        )
        operation.write({'date': date})
        operation.action_done()
        return operation

    def test_sowing_sets_sown_and_start_date(self):
        crop = self._crop(template_id=self.template_direct.id, planned_sowing_date='2027-03-01')
        self.assertEqual(crop.state, 'planned')
        self.assertFalse(crop.date_start)
        self._do(crop, 'operation_type_sowing', '2027-03-04')
        self.assertEqual(crop.state, 'sown')
        self.assertEqual(str(crop.date_start), '2027-03-04')
        self.assertFalse(crop.date_end)

    def test_transplanting_and_planting_set_in_place(self):
        crop = self._crop(planned_sowing_date='2027-03-01')
        self._do(crop, 'operation_type_sowing', '2027-03-02')
        self.assertEqual(crop.state, 'sown')
        self._do(crop, 'operation_type_transplanting', '2027-04-05')
        self.assertEqual(crop.state, 'in_place')
        self.assertEqual(str(crop.date_start), '2027-03-02')
        other = self._crop(bed_id=self.bed2.id, planned_sowing_date='2027-03-01')
        self._do(other, 'operation_type_planting', '2027-04-10')
        self.assertEqual(other.state, 'in_place')
        self.assertEqual(str(other.date_start), '2027-04-10')

    def test_first_harvest_sets_harvesting_without_touching_dates(self):
        crop = self._crop(planned_sowing_date='2027-03-01')
        self._do(crop, 'operation_type_sowing', '2027-03-02')
        self._do(crop, 'operation_type_harvest', '2027-07-15', harvest_qty=5.0)
        self.assertEqual(crop.state, 'harvesting')
        self.assertFalse(crop.date_end)
        # sans semis enregistré, la récolte n'invente pas de début réel
        bare = self._crop(bed_id=self.bed2.id, planned_sowing_date='2027-03-01')
        self._do(bare, 'operation_type_harvest', '2027-07-16', harvest_qty=2.0)
        self.assertEqual(bare.state, 'harvesting')
        self.assertFalse(bare.date_start)

    def test_state_never_goes_back(self):
        crop = self._crop(planned_sowing_date='2027-03-01')
        self._do(crop, 'operation_type_harvest', '2027-07-15', harvest_qty=5.0)
        self.assertEqual(crop.state, 'harvesting')
        late_sowing = self._do(crop, 'operation_type_sowing', '2027-07-20')
        self.assertEqual(crop.state, 'harvesting')
        self.assertEqual(str(crop.date_start), '2027-07-20')
        # rouvrir une opération ne défait rien
        late_sowing.action_reset_planned()
        self.assertEqual(crop.state, 'harvesting')
        self.assertEqual(str(crop.date_start), '2027-07-20')

    def test_manual_values_are_not_overwritten(self):
        crop = self._crop(planned_sowing_date='2027-03-01', date_start='2027-02-20')
        self._do(crop, 'operation_type_sowing', '2027-03-04')
        self.assertEqual(crop.state, 'sown')
        self.assertEqual(str(crop.date_start), '2027-02-20')

    def test_start_date_is_first_done_operation(self):
        crop = self._crop(template_id=self.template_direct.id, planned_sowing_date='2027-03-01')
        self._do(crop, 'operation_type_sowing', '2027-03-10')
        second = self._do(crop, 'operation_type_sowing', '2027-03-05')
        self.assertEqual(str(crop.date_start), '2027-03-10')  # déjà renseigné : conservé
        self.assertTrue(second.allocation_ids)
        fresh = self._crop(bed_id=self.bed2.id, template_id=self.template_direct.id, planned_sowing_date='2027-03-01')
        a = self._operation(
            type_id=self.type_sowing.id, crop_ids=[(6, 0, fresh.ids)], date='2027-03-12', state='done',
        )
        self.assertEqual(str(fresh.date_start), '2027-03-12')
        self.assertTrue(a)

    def test_bed_scope_operation_advances_crops_in_place(self):
        crop = self._crop(template_id=self.template_direct.id, planned_sowing_date='2027-03-01')
        operation = self._operation(
            type_id=self.type_sowing.id, scope='bed', bed_ids=[(6, 0, self.bed.ids)], date='2027-03-02',
        )
        operation.action_done()
        self.assertEqual(crop.state, 'sown')
        self.assertEqual(str(crop.date_start), '2027-03-02')

    def test_done_and_cancelled_crops_are_left_alone(self):
        done = self._crop(planned_sowing_date='2027-03-01', state='done')
        cancelled = self._crop(bed_id=self.bed2.id, planned_sowing_date='2027-03-01', state='cancelled')
        self._do(done, 'operation_type_sowing', '2027-03-04')
        self._do(cancelled, 'operation_type_sowing', '2027-03-04')
        self.assertEqual(done.state, 'done')
        self.assertEqual(cancelled.state, 'cancelled')
        self.assertFalse(done.date_start | cancelled.date_start)

    def test_closing_sets_end_date_from_last_harvest(self):
        crop = self._crop(planned_sowing_date='2027-03-01')
        self._do(crop, 'operation_type_harvest', '2027-07-15', harvest_qty=5.0)
        self._do(crop, 'operation_type_harvest', '2027-08-02', harvest_qty=3.0)
        self.assertFalse(crop.date_end)  # les récoltes ne ferment pas la culture
        crop.state = 'done'
        self.assertEqual(str(crop.date_end), '2027-08-02')
        # saisie manuelle respectée
        manual = self._crop(bed_id=self.bed2.id, planned_sowing_date='2027-03-01', date_end='2027-09-01')
        manual.state = 'done'
        self.assertEqual(str(manual.date_end), '2027-09-01')
        # sans récolte : le jour même
        empty = self._crop(bed_id=self.bed2.id, planned_sowing_date='2028-03-01')
        empty.state = 'done'
        self.assertEqual(empty.date_end, fields.Date.context_today(empty))

    def test_occupation_stays_coherent(self):
        crop = self._crop(template_id=self.template_direct.id, planned_sowing_date='2027-03-01')
        planned_end = crop.occupation_end
        self.assertTrue(planned_end)
        self._do(crop, 'operation_type_sowing', '2027-03-10')
        self.assertEqual(str(crop.occupation_start), '2027-03-10')
        self._do(crop, 'operation_type_harvest', '2027-06-20', harvest_qty=4.0)
        # la fin d'occupation ne rétrécit pas à la première récolte : la culture occupe encore la planche
        self.assertEqual(crop.occupation_end, planned_end)
        # un chevauchement reste détecté pendant la récolte
        rival = self._crop(planned_sowing_date='2027-06-25', template_id=self.template_direct.id)
        self.assertTrue(rival.has_overlap or crop.has_overlap)
