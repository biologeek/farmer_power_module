from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import new_test_user
from odoo.tools import mute_logger

from .test_planning import GardenPlanningCase


class GardenOperationCase(GardenPlanningCase):
    """Fixtures communes aux tests d'opérations (phase 3)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['ir.config_parameter'].sudo().set_param('odoo_garden.default_hourly_rate', '10')
        cls.alice = cls.env['hr.employee'].create({'name': 'Alice test', 'garden_hourly_cost': 20.0})
        cls.bob = cls.env['hr.employee'].create({'name': 'Bob test', 'garden_hourly_cost': 12.0})
        cls.carol = cls.env['hr.employee'].create({'name': 'Carol test'})  # sans taux : taux par défaut
        cls.type_weeding = cls.env.ref('odoo_garden.operation_type_weeding')
        cls.type_irrigation = cls.env.ref('odoo_garden.operation_type_irrigation')
        cls.type_harvest = cls.env.ref('odoo_garden.operation_type_harvest')
        cls.type_sowing = cls.env.ref('odoo_garden.operation_type_sowing')

    def _operation(self, **vals):
        vals.setdefault('type_id', self.type_weeding.id)
        if not any(k in vals for k in ('crop_ids', 'bed_ids', 'garden_id')):
            vals['crop_ids'] = [(6, 0, self._crop(planned_sowing_date='2027-03-01').ids)]
        return self.env['garden.operation'].create(vals)


@tagged('post_install', '-at_install')
class TestGardenOperation(GardenOperationCase):

    def test_defaults_and_name(self):
        crop = self._crop(planned_sowing_date='2027-03-01')
        operation = self._operation(crop_ids=[(6, 0, crop.ids)])
        self.assertEqual(operation.state, 'planned')
        self.assertEqual(operation.scope, 'crop')  # périmètre par défaut du type
        self.assertEqual(operation.category, 'weeding')
        self.assertIn(crop.name, operation.name)
        self.assertEqual(operation.company_id, self.env.company)
        irrigation = self._operation(type_id=self.type_irrigation.id, garden_id=self.garden.id)
        self.assertEqual(irrigation.scope, 'garden')
        self.assertEqual(irrigation.garden_main_id, self.garden)

    def test_scope_requires_target(self):
        with self.assertRaises(ValidationError):
            self.env['garden.operation'].create({'type_id': self.type_weeding.id, 'scope': 'crop'})
        with self.assertRaises(ValidationError):
            self.env['garden.operation'].create({
                'type_id': self.type_irrigation.id, 'scope': 'garden', 'bed_ids': [(6, 0, self.bed.ids)],
            })

    def test_state_flow(self):
        operation = self._operation()
        operation.action_start()
        self.assertEqual(operation.state, 'in_progress')
        operation.action_done()
        self.assertEqual(operation.state, 'done')
        self.assertEqual(operation.date, fields.Date.context_today(operation))
        operation.action_reset_planned()
        self.assertEqual(operation.state, 'planned')
        operation.action_cancel()
        self.assertEqual(operation.state, 'cancelled')

    def test_irrigation_volume(self):
        self.garden.write({'irrigation_type': 'drip', 'irrigation_flow': 1200})
        operation = self._operation(type_id=self.type_irrigation.id, garden_id=self.garden.id, duration=0.5)
        self.assertAlmostEqual(operation.water_volume, 600.0)
        operation.duration = 2
        self.assertAlmostEqual(operation.water_volume, 2400.0)
        # le volume ne dépend pas du nombre d'employés
        operation.employee_ids = self.alice | self.bob
        self.assertAlmostEqual(operation.water_volume, 2400.0)
        # sur des planches : débit de chaque îlot concerné
        by_bed = self._operation(type_id=self.type_irrigation.id, scope='bed', bed_ids=[(6, 0, self.bed.ids)], duration=1)
        self.assertAlmostEqual(by_bed.water_volume, 1200.0)
        # hors irrigation : pas de volume
        self.assertEqual(self._operation(duration=1).water_volume, 0.0)

    def test_harvest_fields_and_required_quantity(self):
        product = self.env['product.product'].create({'name': 'Tomates plan (kg)'})
        self.variety.harvest_product_id = product
        crop = self._crop(planned_sowing_date='2027-03-01')
        harvest = self._operation(type_id=self.type_harvest.id, crop_ids=[(6, 0, crop.ids)])
        self.assertEqual(harvest.harvest_product_id, product)
        self.assertEqual(harvest.harvest_uom_id, product.uom_id)
        self.assertTrue(self.type_harvest.requires_quantity)
        with self.assertRaises(UserError):
            harvest.action_done()
        harvest.harvest_qty = 12.5
        harvest.action_done()
        self.assertEqual(harvest.state, 'done')
        treatment = self._operation(
            type_id=self.env.ref('odoo_garden.operation_type_treatment').id,
            target='Mildiou', weather_notes='Sec, vent faible',
        )
        self.assertEqual(treatment.target, 'Mildiou')


@tagged('post_install', '-at_install')
class TestGardenLabour(GardenOperationCase):

    def test_cost_duration_times_employees(self):
        operation = self._operation(employee_ids=[(6, 0, (self.alice | self.bob).ids)], duration=2.0)
        self.assertAlmostEqual(operation.total_hours, 4.0)
        self.assertAlmostEqual(operation.labour_cost, 2 * 20 + 2 * 12)

    def test_cost_default_rate(self):
        # Carol n'a pas de taux : taux par défaut (10)
        operation = self._operation(employee_ids=[(6, 0, (self.alice | self.carol).ids)], duration=1.5)
        self.assertAlmostEqual(operation.labour_cost, 1.5 * 20 + 1.5 * 10)
        # sans employé : une personne au taux par défaut
        alone = self._operation(duration=3.0)
        self.assertAlmostEqual(alone.total_hours, 3.0)
        self.assertAlmostEqual(alone.labour_cost, 30.0)

    @mute_logger('odoo.sql_db')
    def test_cost_detailed_lines(self):
        operation = self._operation(
            employee_ids=[(6, 0, (self.alice | self.bob).ids)], duration=5.0,
            worker_ids=[
                (0, 0, {'employee_id': self.alice.id, 'duration': 1.0}),
                (0, 0, {'employee_id': self.carol.id, 'duration': 2.0}),
            ],
        )
        # le détail remplace durée × employés
        self.assertAlmostEqual(operation.total_hours, 3.0)
        self.assertAlmostEqual(operation.labour_cost, 1 * 20 + 2 * 10)
        self.assertIn(self.carol, operation.employee_ids)  # l'employé détaillé est ajouté à l'opération
        operation.worker_ids[0].duration = 4.0
        self.assertAlmostEqual(operation.labour_cost, 4 * 20 + 2 * 10)
        with self.assertRaises(Exception), self.cr.savepoint():
            self.env['garden.operation.worker'].create({
                'operation_id': operation.id, 'employee_id': self.alice.id, 'duration': 1,
            })

    def test_cost_follows_rate_changes(self):
        operation = self._operation(employee_ids=[(6, 0, self.alice.ids)], duration=2.0)
        self.assertAlmostEqual(operation.labour_cost, 40.0)
        self.alice.garden_hourly_cost = 30.0
        self.assertAlmostEqual(operation.labour_cost, 60.0)
        alone = self._operation(duration=2.0)
        self.assertAlmostEqual(alone.labour_cost, 20.0)
        settings = self.env['res.config.settings'].create({'garden_default_hourly_rate': 25.0})
        settings.set_values()
        self.assertAlmostEqual(alone.labour_cost, 50.0)

    def test_timer(self):
        operation = self._operation(duration=1.0)
        operation.action_start()
        self.assertEqual(operation.state, 'in_progress')
        self.assertTrue(operation.timer_start)
        # 90 minutes se sont écoulées
        operation.timer_start = fields.Datetime.now() - timedelta(minutes=90)
        operation.action_stop_timer()
        self.assertFalse(operation.timer_start)
        self.assertAlmostEqual(operation.duration, 2.5, delta=0.01)
        self.assertEqual(operation.state, 'in_progress')
        # un second démarrage puis « Terminer » arrête le chronomètre
        operation.action_start()
        operation.timer_start = fields.Datetime.now() - timedelta(minutes=30)
        operation.action_done()
        self.assertFalse(operation.timer_start)
        self.assertAlmostEqual(operation.duration, 3.0, delta=0.01)
        self.assertEqual(operation.state, 'done')

    def test_timer_adds_current_employee(self):
        user = new_test_user(self.env, login='garden_timer', groups='odoo_garden.group_garden_worker')
        employee = self.env['hr.employee'].create({'name': 'Dan test', 'user_id': user.id})
        operation = self._operation()
        operation.with_user(user).action_start()
        self.assertEqual(operation.employee_ids, employee)

    def test_cost_hidden_from_worker(self):
        worker = new_test_user(self.env, login='garden_labour_worker', groups='odoo_garden.group_garden_worker')
        chef = new_test_user(self.env, login='garden_labour_chef', groups='odoo_garden.group_garden_chef')
        operation = self._operation(
            employee_ids=[(6, 0, self.alice.ids)], duration=2.0,
            worker_ids=[(0, 0, {'employee_id': self.alice.id, 'duration': 2.0})],
        )
        as_worker = operation.with_user(worker)
        self.assertEqual(as_worker.read(['total_hours'])[0]['total_hours'], 2.0)
        for record, fname in (
            (as_worker, 'labour_cost'), (as_worker.worker_ids, 'labour_cost'),
            (as_worker.employee_ids, 'garden_hourly_cost'),
        ):
            with self.assertRaises(AccessError, msg=fname):
                record.read([fname])
        self.assertNotIn('labour_cost', as_worker.fields_get())
        self.assertNotIn('garden_hourly_cost', self.env['hr.employee'].with_user(worker).fields_get())
        # la vue de l'ouvrier ne contient pas les coûts
        arch = as_worker.get_view(as_worker.env.ref('odoo_garden.view_garden_operation_form').id)['arch']
        self.assertNotIn('labour_cost', arch)
        arch = as_worker.get_view(as_worker.env.ref('odoo_garden.view_garden_operation_tree').id)['arch']
        self.assertNotIn('labour_cost', arch)
        # le chef de culture les voit
        as_chef = operation.with_user(chef)
        self.assertAlmostEqual(as_chef.read(['labour_cost'])[0]['labour_cost'], 40.0)
        self.assertAlmostEqual(as_chef.worker_ids.read(['labour_cost'])[0]['labour_cost'], 40.0)
        self.assertIn('labour_cost', as_chef.get_view(as_chef.env.ref('odoo_garden.view_garden_operation_form').id)['arch'])
        # l'ouvrier saisit toujours du temps, sans voir le coût
        worker_op = self.env['garden.operation'].with_user(worker).create({
            'type_id': self.type_weeding.id, 'crop_ids': [(6, 0, operation.crop_ids.ids)], 'duration': 1.0,
        })
        worker_op.write({'duration': 2.0})
        self.assertEqual(worker_op.sudo().total_hours, 2.0)


@tagged('post_install', '-at_install')
class TestGardenAllocation(GardenOperationCase):

    def _done(self, **vals):
        vals.setdefault('date', '2027-04-15')
        operation = self._operation(**vals)
        operation.action_done()
        return operation

    def _shares(self, operation):
        return {a.crop_id: a.share for a in operation.allocation_ids}

    def test_crop_scope_prorata_of_area(self):
        # planche 12 : 36 m² ; planche 13 : 10 m²
        big = self._crop(planned_sowing_date='2027-03-01')
        small = self._crop(bed_id=self.bed2.id, planned_sowing_date='2027-03-01')
        operation = self._done(
            crop_ids=[(6, 0, (big | small).ids)], employee_ids=[(6, 0, self.alice.ids)], duration=4.6,
        )
        shares = self._shares(operation)
        self.assertAlmostEqual(shares[big], 36 / 46 * 100, places=3)
        self.assertAlmostEqual(shares[small], 10 / 46 * 100, places=3)
        self.assertAlmostEqual(sum(operation.allocation_ids.mapped('hours')), 4.6)
        self.assertAlmostEqual(sum(operation.allocation_ids.mapped('labour_cost')), 4.6 * 20)
        by_crop = {a.crop_id: a for a in operation.allocation_ids}
        self.assertAlmostEqual(by_crop[small].hours, 1.0)
        self.assertAlmostEqual(big.labour_hours, 3.6)
        self.assertAlmostEqual(small.labour_cost, 20.0)

    def test_single_crop_gets_everything(self):
        crop = self._crop(planned_sowing_date='2027-03-01')
        operation = self._done(crop_ids=[(6, 0, crop.ids)], duration=2.0)
        self.assertEqual(len(operation.allocation_ids), 1)
        self.assertAlmostEqual(operation.allocation_ids.share, 100.0)
        self.assertAlmostEqual(operation.allocation_ids.hours, 2.0)

    def test_bed_scope_uses_crops_in_place_at_date(self):
        # deux cultures en place sur la planche 12 en avril 2027 (moitié chacune) ; une troisième plus tard
        half_a = self._crop(planned_sowing_date='2027-03-01', bed_share=50)
        half_b = self._crop(planned_sowing_date='2027-03-10', bed_share=25)
        later = self._crop(planned_sowing_date='2027-11-01')
        cancelled = self._crop(planned_sowing_date='2027-03-01', state='cancelled')
        operation = self._done(type_id=self.type_weeding.id, scope='bed', bed_ids=[(6, 0, self.bed.ids)], duration=3.0)
        shares = self._shares(operation)
        self.assertEqual(set(shares), {half_a, half_b})
        self.assertNotIn(later, shares)
        self.assertNotIn(cancelled, shares)
        self.assertAlmostEqual(shares[half_a], 100 * 18 / 27, places=3)
        self.assertAlmostEqual(shares[half_b], 100 * 9 / 27, places=3)
        self.assertAlmostEqual(sum(shares.values()), 100.0)

    def test_garden_scope_spreads_over_all_beds(self):
        a = self._crop(planned_sowing_date='2027-03-01')  # 36 m²
        b = self._crop(bed_id=self.bed2.id, planned_sowing_date='2027-03-01')  # 10 m²
        operation = self._done(
            type_id=self.type_irrigation.id, scope='garden', garden_id=self.garden.id,
            employee_ids=[(6, 0, (self.alice | self.bob).ids)], duration=1.0,
        )
        shares = self._shares(operation)
        self.assertEqual(set(shares), {a, b})
        self.assertAlmostEqual(shares[a], 36 / 46 * 100, places=3)
        # 2 employés × 1 h = 2 h réparties
        self.assertAlmostEqual(sum(operation.allocation_ids.mapped('hours')), 2.0)
        self.assertAlmostEqual(sum(operation.allocation_ids.mapped('labour_cost')), 32.0)

    def test_no_crop_in_place(self):
        operation = self._done(
            type_id=self.type_weeding.id, scope='bed', bed_ids=[(6, 0, self.bed2.ids)], duration=1.0,
        )
        self.assertEqual(operation.state, 'done')
        self.assertFalse(operation.allocation_ids)
        self.assertTrue(operation.allocation_warning)
        self.assertEqual(sum(operation.allocation_ids.mapped('hours')), 0.0)

    def test_zero_area_crops_share_equally(self):
        bed = self.env['garden.bed'].create({'name': 'Sans dimension', 'code': 'SD', 'garden_id': self.garden.id})
        c1 = self._crop(bed_id=bed.id, planned_sowing_date='2027-03-01')
        c2 = self._crop(bed_id=bed.id, planned_sowing_date='2027-03-01')
        operation = self._done(scope='bed', bed_ids=[(6, 0, bed.ids)], duration=1.0)
        self.assertEqual(self._shares(operation), {c1: 50.0, c2: 50.0})

    def test_recomputed_when_reopened_or_modified(self):
        a = self._crop(planned_sowing_date='2027-03-01')
        b = self._crop(bed_id=self.bed2.id, planned_sowing_date='2027-03-01')
        operation = self._done(crop_ids=[(6, 0, a.ids)], duration=2.0)
        self.assertEqual(a.labour_hours, 2.0)
        operation.crop_ids = a | b
        self.assertEqual(set(self._shares(operation)), {a, b})
        operation.duration = 4.6
        self.assertAlmostEqual(b.labour_hours, 1.0)
        operation.action_reset_planned()
        self.assertFalse(operation.allocation_ids)
        self.assertEqual(a.labour_hours, 0.0)
        operation.action_done()
        self.assertEqual(len(operation.allocation_ids), 2)
        operation.action_cancel()  # une opération faite ne peut pas être annulée
        self.assertEqual(operation.state, 'done')

    def test_planned_operation_has_no_allocation(self):
        operation = self._operation(duration=2.0)
        self.assertFalse(operation.allocation_ids)
        self.assertFalse(operation.allocation_warning)

    def test_crop_operation_count_and_actions(self):
        crop = self._crop(planned_sowing_date='2027-03-01')
        direct = self._operation(crop_ids=[(6, 0, crop.ids)])
        by_bed = self._done(scope='bed', bed_ids=[(6, 0, self.bed.ids)], duration=1.0)
        self.assertEqual(crop.operation_count, 2)
        action = crop.action_view_operations()
        found = self.env['garden.operation'].search(action['domain'])
        self.assertEqual(found, direct | by_bed)
        self.assertEqual(crop.action_new_operation()['context']['default_crop_ids'], [(6, 0, crop.ids)])
