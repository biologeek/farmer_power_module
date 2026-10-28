from odoo.exceptions import AccessError, ValidationError
from odoo.tests import tagged

from .test_compliance_fields import GardenComplianceCase


@tagged('post_install', '-at_install')
class TestGardenPreHarvestInterval(GardenComplianceCase):
    """Délai avant récolte (DAR) : blocage, dérogation du gérant, cas sans blocage."""

    def test_harvest_blocked_inside_interval(self):
        self._treatment('2027-06-10')  # DAR de 7 jours
        harvest = self._harvest('2027-06-13')  # 3 jours après
        with self.assertRaises(ValidationError) as caught:
            harvest.action_done()
        self.assertIn("Délai avant récolte", str(caught.exception))
        self.assertEqual(harvest.state, 'planned')
        self.assertFalse(harvest.move_ids)
        # la veille de la fin du délai : encore bloquée ; le jour de la fin : autorisée
        with self.assertRaises(ValidationError):
            self._harvest('2027-06-16').action_done()
        self._harvest('2027-06-17').action_done()

    def test_creating_done_harvest_is_checked(self):
        self._treatment('2027-06-10')
        with self.assertRaises(ValidationError):
            self._harvest('2027-06-12', state='done')
        with self.assertRaises(ValidationError):
            harvest = self._harvest('2027-06-30')
            harvest.action_done()
            harvest.action_reset_planned()
            harvest.write({'date': '2027-06-11', 'state': 'done'})

    def test_manager_override_is_traced(self):
        self._treatment('2027-06-10')
        harvest = self._harvest('2027-06-13')
        manager_harvest = harvest.with_user(self.manager)
        with self.assertRaises(ValidationError):  # motif obligatoire
            manager_harvest.write({'dar_override': True})
        manager_harvest.write({'dar_override': True, 'dar_override_reason': 'Maladie : récolte sanitaire'})
        self.assertEqual(harvest.sudo().dar_override_user_id, self.manager)
        notes = " ".join(harvest.message_ids.mapped('body'))
        self.assertIn('Maladie : récolte sanitaire', notes)
        self.assertIn(self.manager.name, notes)
        harvest.action_done()
        self.assertEqual(harvest.state, 'done')
        self.assertTrue(harvest.move_ids)
        notes = " ".join(harvest.message_ids.mapped('body'))
        self.assertIn('Récolte validée en dérogation', notes)
        self.assertIn(self.crop.name, notes)

    def test_chef_and_worker_cannot_override(self):
        self._treatment('2027-06-10')
        harvest = self._harvest('2027-06-13')
        for user in (self.chef, self.worker):
            with self.assertRaises(AccessError):
                harvest.with_user(user).write({'dar_override': True, 'dar_override_reason': 'Je veux'})
            with self.assertRaises(AccessError):
                harvest.with_user(user).read(['dar_override_reason'])
        with self.assertRaises(AccessError):
            self.env['garden.operation'].with_user(self.chef).create({
                'type_id': self.type_harvest.id, 'crop_ids': [(6, 0, self.crop.ids)], 'dar_override': True,
                'dar_override_reason': 'x',
            })
        # sans dérogation, le chef de culture reste bloqué
        with self.assertRaises(ValidationError):
            harvest.with_user(self.chef).action_done()

    def test_override_set_by_manager_lets_worker_finish(self):
        self._treatment('2027-06-10')
        harvest = self._harvest('2027-06-13')
        harvest.with_user(self.manager).write({'dar_override': True, 'dar_override_reason': 'Accord du gérant'})
        harvest.with_user(self.worker).action_done()
        self.assertEqual(harvest.state, 'done')

    def test_no_block_without_interval_cancelled_or_later_treatment(self):
        # produit sans DAR
        no_dar = self._storable('Phyto sans DAR', garden_input_type='phytosanitary')
        self._set_stock(no_dar, 10)
        self._treatment('2027-06-10', product=no_dar)
        self._harvest('2027-06-11').action_done()
        # traitement annulé ou planifié : ignoré
        other = self._crop(planned_sowing_date='2027-03-01', bed_id=self.bed2.id)
        treatment = self._treatment('2027-07-01', crop=other)
        treatment.action_reset_planned()
        self._harvest('2027-07-02', crop=other).action_done()
        treatment.action_cancel()
        self._harvest('2027-07-03', crop=other).action_done()
        # traitement postérieur à la récolte : ignoré
        third = self._crop(planned_sowing_date='2027-03-01', bed_id=self.bed2.id)
        self._treatment('2027-08-10', crop=third)
        self._harvest('2027-08-05', crop=third).action_done()
        # un traitement d'une autre culture ne bloque pas
        self._treatment('2027-09-01', crop=third)
        self._harvest('2027-09-02', crop=self.crop).action_done()

    def test_multi_crop_harvest_checks_each_crop(self):
        other = self._crop(planned_sowing_date='2027-03-01', bed_id=self.bed2.id)
        self._treatment('2027-06-10', crop=other)
        harvest = self._operation(
            type_id=self.type_harvest.id, crop_ids=[(6, 0, (self.crop | other).ids)], date='2027-06-12',
            harvest_product_id=self.harvest_product.id, harvest_qty=20,
        )
        with self.assertRaises(ValidationError) as caught:
            harvest.action_done()
        self.assertIn(other.name, str(caught.exception))
        self.assertEqual(str(caught.exception).count('traitement du'), 1)  # seule la culture traitée est citée
        # récolte de planche : les cultures en place sont contrôlées
        bed_harvest = self._operation(
            type_id=self.type_harvest.id, scope='bed', bed_ids=[(6, 0, self.bed2.ids)], date='2027-06-12',
            harvest_product_id=self.harvest_product.id, harvest_qty=5,
        )
        with self.assertRaises(ValidationError):
            bed_harvest.action_done()

    def test_warning_and_crop_date(self):
        self.assertFalse(self.crop.harvest_allowed_from)
        self._treatment('2027-06-10')
        self.assertEqual(str(self.crop.harvest_allowed_from), '2027-06-17')
        self.assertTrue(self.crop.harvest_allowed_warning)  # la fin du délai est dans le futur
        harvest = self._harvest('2027-06-13')
        self.assertIn(self.crop.name, harvest.dar_warning)
        self.assertIn('2027-06-17', harvest.dar_warning)
        later = self._harvest('2027-06-20')
        self.assertFalse(later.dar_warning)
        # le plus long des délais fixe la date
        long_dar = self._storable('Phyto long', garden_input_type='phytosanitary', pre_harvest_interval_days=21)
        self._set_stock(long_dar, 10)
        self._treatment('2027-06-12', product=long_dar)
        self.assertEqual(str(self.crop.harvest_allowed_from), '2027-07-03')
        self.assertTrue(self.crop.with_user(self.worker).harvest_allowed_from)
        # délai échu (traitement passé) : plus d'avertissement sur la culture
        past = self._crop(planned_sowing_date='2020-03-01', bed_id=self.bed2.id)
        self._treatment('2020-06-10', crop=past)
        self.assertEqual(str(past.harvest_allowed_from), '2020-06-17')
        self.assertFalse(past.harvest_allowed_warning)

    def test_warning_not_computed_once_done(self):
        self._treatment('2027-06-10')
        harvest = self._harvest('2027-06-30')
        harvest.action_done()
        self.assertFalse(harvest.dar_warning)
