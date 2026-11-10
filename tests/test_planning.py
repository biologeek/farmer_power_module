from odoo.exceptions import AccessError, ValidationError
from odoo.fields import Date
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user
from odoo.tools import mute_logger


class GardenPlanningCase(TransactionCase):
    """Fixtures communes aux tests de planification (phase 2)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.farm = cls.env['garden.farm'].create({'name': 'Ferme plan'})
        cls.site = cls.env['garden.site'].create({'name': 'Site plan', 'farm_id': cls.farm.id})
        cls.garden = cls.env['garden.garden'].create({'name': 'Îlot plan', 'code': 'IP', 'site_id': cls.site.id})
        cls.bed = cls.env['garden.bed'].create({
            'name': 'Planche 12', 'code': 'P12', 'garden_id': cls.garden.id, 'length': 30, 'width': 1.2,
        })
        cls.bed2 = cls.env['garden.bed'].create({
            'name': 'Planche 13', 'code': 'P13', 'garden_id': cls.garden.id, 'length': 10, 'width': 1,
        })
        cls.solanaceae = cls.env['garden.species'].create({
            'name': 'Tomate plan', 'family': 'solanaceae', 'rotation_years': 3,
        })
        cls.brassica = cls.env['garden.species'].create({
            'name': 'Chou plan', 'family': 'brassicaceae', 'rotation_years': 2,
        })
        cls.variety = cls.env['garden.variety'].create({
            'name': 'Cœur de bœuf plan', 'species_id': cls.solanaceae.id,
            'seeds_per_gram': 300, 'germination_rate': 80,
        })
        cls.variety_cabbage = cls.env['garden.variety'].create({
            'name': 'Milan plan', 'species_id': cls.brassica.id,
            'seeds_per_gram': 4, 'germination_rate': 100,
        })
        cls.template = cls.env['garden.crop.template'].create({
            'name': 'Tomate sous abri', 'variety_id': cls.variety.id, 'propagation': 'own_plants',
            'row_spacing': 50, 'plant_spacing': 50,  # 4 plants/m²
            'days_to_transplant': 30, 'days_to_maturity': 90, 'harvest_window_days': 40,
            'expected_yield': 8, 'expected_price': 5,
        })
        cls.template_direct = cls.env['garden.crop.template'].create({
            'name': 'Chou semis direct', 'variety_id': cls.variety_cabbage.id, 'propagation': 'direct_sowing',
            'row_spacing': 50, 'plant_spacing': 40,  # 5 plants/m²
            'days_to_maturity': 100, 'harvest_window_days': 20, 'expected_yield': 3, 'expected_price': 2,
        })
        cls.season = cls.env['garden.season'].create({
            'name': 'Saison test 2027', 'date_start': '2027-01-01', 'date_end': '2027-12-31',
        })

    def _crop(self, **vals):
        vals.setdefault('template_id', self.template.id)
        vals.setdefault('bed_id', self.bed.id)
        vals.setdefault('season_id', self.season.id)
        return self.env['garden.crop'].create(vals)


@tagged('post_install', '-at_install')
class TestGardenSeasonAndCrop(GardenPlanningCase):

    def test_season_workflow(self):
        self.assertEqual(self.season.state, 'draft')
        self.season.action_validate()
        self.assertEqual(self.season.state, 'validated')
        self.season.action_close()
        self.assertEqual(self.season.state, 'closed')
        self.season.action_reset_draft()
        self.assertEqual(self.season.state, 'draft')

    def test_season_constraints(self):
        with self.assertRaises(ValidationError):
            self.env['garden.season'].create({'name': 'Inversée', 'date_start': '2027-12-31', 'date_end': '2027-01-01'})
        with mute_logger('odoo.sql_db'), self.assertRaises(Exception), self.cr.savepoint():
            self.env['garden.season'].create({
                'name': 'Saison test 2027', 'date_start': '2027-01-01', 'date_end': '2027-12-31',
            })

    def test_season_crop_count(self):
        self.assertEqual(self.season.crop_count, 0)
        self._crop()
        self._crop(bed_id=self.bed2.id)
        self.assertEqual(self.season.crop_count, 2)
        self.assertEqual(self.season.action_view_crops()['domain'], [('season_id', '=', self.season.id)])

    def test_crop_name_sequence(self):
        crop1 = self._crop()
        crop2 = self._crop()
        crop3 = self._crop(bed_id=self.bed2.id)
        self.assertEqual(crop1.name, 'T-2027-P12-01')
        self.assertEqual(crop2.name, 'T-2027-P12-02')
        self.assertEqual(crop3.name, 'T-2027-P13-01')
        # création en lot : numéros distincts
        batch = self.env['garden.crop'].create([
            {'template_id': self.template.id, 'bed_id': self.bed2.id, 'season_id': self.season.id},
            {'template_id': self.template.id, 'bed_id': self.bed2.id, 'season_id': self.season.id},
        ])
        self.assertEqual(batch.mapped('name'), ['T-2027-P13-02', 'T-2027-P13-03'])
        # la copie reçoit une nouvelle référence
        self.assertEqual(crop1.copy().name, 'T-2027-P12-03')
        # changer de planche renomme la culture
        crop2.bed_id = self.bed2
        self.assertEqual(crop2.name, 'T-2027-P13-04')

    def test_crop_name_without_season(self):
        crop = self._crop(season_id=False, planned_sowing_date='2026-03-01')
        self.assertEqual(crop.name, 'T-2026-P12-01')

    def test_crop_area_and_forecast(self):
        crop = self._crop(bed_share=50)
        self.assertAlmostEqual(crop.area, 18.0)  # 36 m² * 50 %
        self.assertAlmostEqual(crop.planned_plant_qty, 72.0)  # 18 m² * 4 plants/m²
        self.assertAlmostEqual(crop.expected_yield_qty, 144.0)  # 18 m² * 8 kg/m²
        self.assertAlmostEqual(crop.expected_revenue, 720.0)  # 144 kg * 5 €
        crop.bed_share = 100
        self.assertAlmostEqual(crop.area, 36.0)
        self.assertAlmostEqual(crop.expected_yield_qty, 288.0)
        self.bed.width = 1.0
        self.assertAlmostEqual(crop.area, 30.0)

    def test_bed_share_constraint(self):
        for share in (0, 100.5, -5):
            with mute_logger('odoo.sql_db'), self.assertRaises(Exception), self.cr.savepoint():
                self._crop(bed_share=share)

    def test_crop_state_default(self):
        crop = self._crop()
        self.assertEqual(crop.state, 'planned')
        crop.state = 'sown'
        self.assertEqual(crop.state, 'sown')

    def test_occupation_period(self):
        # plants autoproduits : la planche est occupée à partir du repiquage
        crop = self._crop(
            planned_sowing_date='2027-03-01', planned_transplant_date='2027-03-31',
            planned_harvest_start='2027-06-01', planned_harvest_end='2027-07-10',
        )
        self.assertEqual(crop.occupation_start, Date.to_date('2027-03-31'))
        self.assertEqual(crop.occupation_end, Date.to_date('2027-07-10'))
        # semis direct : dès le semis ; la fin réelle prime
        direct = self._crop(
            template_id=self.template_direct.id, planned_sowing_date='2027-04-01',
            planned_harvest_end='2027-08-01', date_end='2027-07-20',
        )
        self.assertEqual(direct.occupation_start, Date.to_date('2027-04-01'))
        self.assertEqual(direct.occupation_end, Date.to_date('2027-07-20'))

    def test_bed_current_crops_use_occupation(self):
        today = Date.today()
        crop = self._crop(planned_sowing_date=today, planned_harvest_end=Date.add(today, days=30))
        crop.planned_transplant_date = False
        self.assertIn(crop, self.bed.current_crop_ids)
        crop.state = 'cancelled'
        self.assertNotIn(crop, self.bed.current_crop_ids)


@tagged('post_install', '-at_install')
class TestGardenPlanningSecurity(GardenPlanningCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.worker = new_test_user(cls.env, login='plan_worker', groups='farmer_power.group_garden_worker')
        cls.chef = new_test_user(cls.env, login='plan_chef', groups='farmer_power.group_garden_chef')

    def test_worker_reads_but_cannot_edit_season(self):
        self.assertTrue(self.season.with_user(self.worker).read(['name']))
        with self.assertRaises(AccessError):
            self.env['garden.season'].with_user(self.worker).create({
                'name': 'Interdite', 'date_start': '2028-01-01', 'date_end': '2028-12-31',
            })
        with self.assertRaises(AccessError):
            self.season.with_user(self.worker).write({'name': 'X'})
        with self.assertRaises(AccessError):
            self.season.with_user(self.worker).unlink()

    def test_chef_manages_season(self):
        season = self.env['garden.season'].with_user(self.chef).create({
            'name': 'Chef 2028', 'date_start': '2028-01-01', 'date_end': '2028-12-31',
        })
        season.action_validate()
        self.assertEqual(season.state, 'validated')
        season.unlink()

    def test_season_multi_company_rule(self):
        company2 = self.env['res.company'].create({'name': 'Autre société'})
        season2 = self.env['garden.season'].create({
            'name': 'Other', 'date_start': '2027-01-01', 'date_end': '2027-12-31', 'company_id': company2.id,
        })
        chef = self.chef.with_company(self.env.company)
        self.assertNotIn(season2, self.env['garden.season'].with_user(chef).search([]))
        self.assertIn(self.season, self.env['garden.season'].with_user(chef).search([]))


@tagged('post_install', '-at_install')
class TestGardenBackPlanning(GardenPlanningCase):

    def test_plan_dates_from_harvest(self):
        dates = self.template._plan_dates(harvest_start='2027-07-01')
        self.assertEqual(dates['planned_sowing_date'], Date.to_date('2027-04-02'))
        self.assertEqual(dates['planned_transplant_date'], Date.to_date('2027-05-02'))
        self.assertEqual(dates['planned_harvest_start'], Date.to_date('2027-07-01'))
        self.assertEqual(dates['planned_harvest_end'], Date.to_date('2027-08-10'))

    def test_plan_dates_from_sowing(self):
        dates = self.template._plan_dates(sowing_date='2027-03-01')
        self.assertEqual(dates['planned_transplant_date'], Date.to_date('2027-03-31'))
        self.assertEqual(dates['planned_harvest_start'], Date.to_date('2027-05-30'))
        self.assertEqual(dates['planned_harvest_end'], Date.to_date('2027-07-09'))
        self.assertEqual(self.template._plan_dates(), {})

    def test_direct_sowing_has_no_transplant(self):
        dates = self.template_direct._plan_dates(harvest_start='2027-09-01')
        self.assertFalse(dates['planned_transplant_date'])
        self.assertEqual(dates['planned_sowing_date'], Date.to_date('2027-05-24'))
        self.assertEqual(dates['planned_harvest_end'], Date.to_date('2027-09-21'))

    def test_create_completes_dates(self):
        from_harvest = self._crop(planned_harvest_start='2027-07-01')
        self.assertEqual(from_harvest.planned_sowing_date, Date.to_date('2027-04-02'))
        self.assertEqual(from_harvest.planned_transplant_date, Date.to_date('2027-05-02'))
        self.assertEqual(from_harvest.planned_harvest_end, Date.to_date('2027-08-10'))
        from_sowing = self._crop(planned_sowing_date='2027-03-01')
        self.assertEqual(from_sowing.planned_harvest_start, Date.to_date('2027-05-30'))
        # une date explicite n'est pas écrasée
        manual = self._crop(planned_sowing_date='2027-03-01', planned_harvest_end='2027-09-01')
        self.assertEqual(manual.planned_harvest_end, Date.to_date('2027-09-01'))

    def test_onchange_and_buttons(self):
        crop = self._crop(planned_sowing_date='2027-03-01')
        crop.planned_harvest_start = Date.to_date('2027-07-01')
        crop._onchange_planned_harvest_start()
        self.assertEqual(crop.planned_sowing_date, Date.to_date('2027-04-02'))
        crop.planned_sowing_date = Date.to_date('2027-03-01')
        crop.action_plan_from_sowing()
        self.assertEqual(crop.planned_harvest_start, Date.to_date('2027-05-30'))
        crop.planned_harvest_start = Date.to_date('2027-06-15')
        crop.action_plan_from_harvest()
        self.assertEqual(crop.planned_sowing_date, Date.to_date('2027-03-17'))
        self.assertEqual(crop.planned_transplant_date, Date.to_date('2027-04-16'))
        # changer d'itinéraire recalcule depuis le semis
        crop.template_id = self.template_direct
        crop._onchange_template_id_dates()
        self.assertFalse(crop.planned_transplant_date)
        self.assertEqual(crop.planned_harvest_start, Date.to_date('2027-06-25'))

    def test_get_planned_steps(self):
        sowing = self.env['garden.operation.type'].create({'name': 'Semis test'})
        weeding = self.env['garden.operation.type'].create({'name': 'Désherbage test'})
        harvest = self.env['garden.operation.type'].create({'name': 'Récolte test'})
        Step = self.env['garden.crop.template.step']
        Step.create([
            {'template_id': self.template.id, 'operation_type_id': harvest.id, 'sequence': 30,
             'day_offset': 90, 'expected_duration': 0.1},
            {'template_id': self.template.id, 'operation_type_id': sowing.id, 'sequence': 10,
             'day_offset': 0, 'expected_duration': 0.01},
            {'template_id': self.template.id, 'operation_type_id': weeding.id, 'sequence': 20,
             'day_offset': 45, 'expected_duration': 0.05},
        ])
        crop = self._crop(planned_sowing_date='2027-03-01', bed_share=50)  # 18 m²
        steps = crop._get_planned_steps()
        self.assertEqual([s['operation_type'] for s in steps], [sowing, weeding, harvest])
        self.assertEqual(
            [s['date'] for s in steps],
            [Date.to_date('2027-03-01'), Date.to_date('2027-04-15'), Date.to_date('2027-05-30')],
        )
        self.assertAlmostEqual(steps[0]['duration'], 0.18)
        self.assertAlmostEqual(steps[2]['duration'], 1.8)
        # sans semis prévu, aucune étape
        self.assertEqual(self._crop()._get_planned_steps(), [])


@tagged('post_install', '-at_install')
class TestGardenPlanWizard(GardenPlanningCase):

    def _wizard(self, user=None, **vals):
        vals.setdefault('season_id', self.season.id)
        vals.setdefault('template_id', self.template.id)
        Wizard = self.env['garden.season.plan.wizard']
        return (Wizard.with_user(user) if user else Wizard).create(vals)

    def test_serial_creation_staggered(self):
        beds = self.bed | self.bed2
        wizard = self._wizard(
            bed_ids=[(6, 0, beds.ids)], target='harvest', target_date='2027-07-01', stagger_days=14, bed_share=80,
        )
        action = wizard.action_create_crops()
        crops = self.env['garden.crop'].search(action['domain'])
        self.assertEqual(len(crops), 2)
        first, second = crops.sorted('planned_harvest_start')
        self.assertEqual(first.planned_harvest_start, Date.to_date('2027-07-01'))
        self.assertEqual(second.planned_harvest_start, Date.to_date('2027-07-15'))
        self.assertEqual(first.planned_sowing_date, Date.to_date('2027-04-02'))
        self.assertEqual(second.planned_sowing_date, Date.to_date('2027-04-16'))
        self.assertEqual(second.planned_harvest_end, Date.to_date('2027-08-24'))
        self.assertEqual(crops.mapped('season_id'), self.season)
        self.assertEqual(set(crops.mapped('bed_id').ids), set(beds.ids))
        self.assertEqual(set(crops.mapped('bed_share')), {80.0})
        self.assertEqual(crops.mapped('state'), ['planned', 'planned'])

    def test_serial_creation_from_sowing_without_stagger(self):
        wizard = self._wizard(
            bed_ids=[(6, 0, (self.bed | self.bed2).ids)], target='sowing', target_date='2027-03-01',
        )
        crops = self.env['garden.crop'].search(wizard.action_create_crops()['domain'])
        self.assertEqual(set(crops.mapped('planned_sowing_date')), {Date.to_date('2027-03-01')})
        self.assertEqual(set(crops.mapped('planned_harvest_start')), {Date.to_date('2027-05-30')})
        self.assertIn('Planche 12', wizard.preview)

    def test_wizard_requires_beds(self):
        from odoo.exceptions import UserError
        wizard = self._wizard(target_date='2027-07-01')
        with self.assertRaises(UserError):
            wizard.action_create_crops()

    def test_wizard_reserved_to_chef(self):
        worker = new_test_user(self.env, login='wiz_worker', groups='farmer_power.group_garden_worker')
        chef = new_test_user(self.env, login='wiz_chef', groups='farmer_power.group_garden_chef')
        with self.assertRaises(AccessError):
            self._wizard(user=worker, target_date='2027-07-01')
        wizard = self._wizard(user=chef, target_date='2027-07-01', bed_ids=[(6, 0, self.bed.ids)])
        self.assertEqual(len(self.env['garden.crop'].search(wizard.action_create_crops()['domain'])), 1)


@tagged('post_install', '-at_install')
class TestGardenWarnings(GardenPlanningCase):

    def _period(self, start, end, **vals):
        """Culture en semis direct de chou (période d'occupation = semis → fin de récolte)."""
        vals.setdefault('template_id', self.template_direct.id)
        return self._crop(planned_sowing_date=start, planned_harvest_end=end, **vals)

    def test_no_warning_alone(self):
        crop = self._period('2027-03-01', '2027-06-30')
        self.assertFalse(crop.has_overlap or crop.has_rotation_conflict)
        self.assertFalse(crop.overlap_warning or crop.rotation_warning)

    def test_overlap_detected_on_both_crops(self):
        first = self._period('2027-03-01', '2027-06-30')
        second = self._period('2027-05-01', '2027-08-30')
        for crop, other in ((first, second), (second, first)):
            self.assertTrue(crop.has_overlap)
            self.assertAlmostEqual(crop.overlap_share, 200.0)
            self.assertIn(other.name, crop.overlap_warning)

    def test_no_overlap_when_shares_fit(self):
        first = self._period('2027-03-01', '2027-06-30', bed_share=50)
        second = self._period('2027-04-01', '2027-06-30', bed_share=50)
        self.assertFalse(first.has_overlap or second.has_overlap)
        second.bed_share = 60
        self.assertTrue(first.has_overlap and second.has_overlap)
        self.assertAlmostEqual(first.overlap_share, 110.0)

    def test_no_overlap_when_periods_disjoint_or_other_bed(self):
        first = self._period('2027-03-01', '2027-06-30')
        after = self._period('2027-07-01', '2027-09-30')
        elsewhere = self._period('2027-03-01', '2027-06-30', bed_id=self.bed2.id)
        self.assertFalse(first.has_overlap or after.has_overlap or elsewhere.has_overlap)

    def test_overlap_ignores_chained_non_concurrent_crops(self):
        # B (50 %) et C (50 %) chevauchent A (50 %) mais jamais entre eux : 100 % au maximum
        a = self._period('2027-03-01', '2027-09-30', bed_share=50)
        b = self._period('2027-03-01', '2027-05-31', bed_share=50)
        c = self._period('2027-06-15', '2027-09-30', bed_share=50)
        self.assertFalse(a.has_overlap or b.has_overlap or c.has_overlap)

    def test_cancelled_crop_does_not_overlap(self):
        first = self._period('2027-03-01', '2027-06-30')
        second = self._period('2027-05-01', '2027-08-30')
        second.state = 'cancelled'
        self.assertFalse(first.has_overlap or second.has_overlap)

    def test_rotation_conflict(self):
        previous = self._crop(
            planned_sowing_date='2025-03-01', template_id=self.template_direct.id,
            planned_harvest_end='2025-09-30',
        )
        # chou (rotation 2 ans) : 2025-09-30 → 2027-04-01 = moins de 2 ans
        too_soon = self._period('2027-04-01', '2027-08-31')
        self.assertTrue(too_soon.has_rotation_conflict)
        self.assertIn(previous.name, too_soon.rotation_warning)
        self.assertFalse(previous.has_rotation_conflict)
        # après le délai (la culture trop proche est annulée) : plus de conflit
        too_soon.state = 'cancelled'
        later = self._period('2027-10-01', '2027-12-15')
        self.assertFalse(later.has_rotation_conflict)

    def test_rotation_ignores_other_families_and_beds(self):
        self._period('2026-03-01', '2026-09-30')  # chou sur P12
        tomato = self._crop(planned_sowing_date='2027-03-01', planned_harvest_end='2027-09-30')
        self.assertFalse(tomato.has_rotation_conflict)
        other_bed = self._period('2027-03-01', '2027-09-30', bed_id=self.bed2.id)
        self.assertFalse(other_bed.has_rotation_conflict)

    def test_rotation_family_other_not_checked(self):
        species = self.env['garden.species'].create({'name': 'Divers plan', 'family': 'other'})
        variety = self.env['garden.variety'].create({'name': 'Div', 'species_id': species.id})
        template = self.env['garden.crop.template'].create({'name': 'Div', 'variety_id': variety.id})
        self._period('2026-03-01', '2026-09-30', template_id=template.id)
        crop = self._period('2027-03-01', '2027-09-30', template_id=template.id)
        self.assertFalse(crop.has_rotation_conflict)

    def test_rotation_disabled_when_zero_years(self):
        self.brassica.rotation_years = 0
        self._period('2026-03-01', '2026-09-30')
        self.assertFalse(self._period('2027-03-01', '2027-09-30').has_rotation_conflict)

    def test_warnings_update_on_change(self):
        first = self._period('2027-03-01', '2027-06-30')
        second = self._period('2027-05-01', '2027-08-30')
        self.assertTrue(first.has_overlap)
        second.bed_id = self.bed2
        self.assertFalse(first.has_overlap)


@tagged('post_install', '-at_install')
class TestGardenSeedNeeds(GardenPlanningCase):

    def setUp(self):
        super().setUp()
        self.env['ir.config_parameter'].sudo().set_param('farmer_power.seed_margin', '20')

    def test_default_margin(self):
        self.env['ir.config_parameter'].sudo().search([('key', '=', 'farmer_power.seed_margin')]).unlink()
        self.assertEqual(self.env['garden.crop']._get_seed_margin(), 20.0)

    def test_seed_computation(self):
        # 36 m² × 4 plants/m² = 144 plants ; 144 / 0,8 × 1,2 = 216 graines ; 216 / 300 = 0,72 g
        crop = self._crop()
        self.assertAlmostEqual(crop.planned_plant_qty, 144.0)
        self.assertEqual(crop.planned_seed_count, 216)
        self.assertAlmostEqual(crop.planned_seed_qty, 0.72)

    def test_bought_plants_need_no_seed(self):
        self.template.propagation = 'bought_plants'
        crop = self._crop()
        self.assertEqual(crop.planned_seed_count, 0)
        self.assertEqual(crop.planned_seed_qty, 0.0)

    def test_margin_setting_recomputes(self):
        crop = self._crop()
        settings = self.env['res.config.settings'].create({'garden_seed_margin': 50.0})
        settings.execute()
        self.assertEqual(self.env['garden.crop']._get_seed_margin(), 50.0)
        self.assertEqual(crop.planned_seed_count, 270)  # 144 / 0,8 × 1,5
        self.assertAlmostEqual(crop.planned_seed_qty, 0.9)

    def test_seed_needs_per_variety(self):
        self._crop()  # 144 plants de tomate
        self._crop(bed_id=self.bed2.id, bed_share=50)  # 5 m² → 20 plants, 30 graines
        cabbage = self._crop(template_id=self.template_direct.id)  # 36 m² × 5 = 180 plants, 216 graines, 54 g
        cancelled = self._crop(template_id=self.template_direct.id, bed_id=self.bed2.id)
        cancelled.state = 'cancelled'
        needs = {line['variety']: line for line in self.env['garden.crop'].get_seed_needs(
            [('season_id', '=', self.season.id)])}
        self.assertEqual(set(needs), {self.variety, self.variety_cabbage})
        tomato = needs[self.variety]
        self.assertAlmostEqual(tomato['plants'], 164.0)
        self.assertEqual(tomato['seeds'], 216 + 30)
        self.assertAlmostEqual(tomato['grams'], 0.72 + 0.1)
        self.assertAlmostEqual(tomato['area'], 41.0)
        self.assertAlmostEqual(needs[self.variety_cabbage]['plants'], cabbage.planned_plant_qty)
        self.assertAlmostEqual(needs[self.variety_cabbage]['grams'], 216 / 4.0)

    def test_manual_plant_quantity_is_used(self):
        crop = self._crop()
        crop.planned_plant_qty = 100
        self.assertEqual(crop.planned_seed_count, 150)  # 100 / 0,8 × 1,2
