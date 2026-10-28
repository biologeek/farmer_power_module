from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestGardenDemo(TransactionCase):
    """Vérifie le plan de culture de démonstration (ignoré sur une base sans démo)."""

    def test_demo_season(self):
        season = self.env.ref('odoo_garden.demo_season_2027', raise_if_not_found=False)
        if not season:
            self.skipTest("Données de démonstration non installées.")
        crops = season.crop_ids
        self.assertEqual(len(crops), 12)
        self.assertTrue(all(crops.mapped('planned_sowing_date')))
        self.assertTrue(all(crops.mapped('planned_harvest_end')))
        overlap = crops.filtered('has_overlap')
        self.assertEqual(
            overlap.mapped('bed_id'), self.env.ref('odoo_garden.demo_bed_n1_01'),
        )
        self.assertEqual(len(overlap), 2)
        rotation = crops.filtered('has_rotation_conflict')
        self.assertEqual(rotation.mapped('bed_id'), self.env.ref('odoo_garden.demo_bed_s1_03'))
        # parts de planche à 50 % : pas d'avertissement
        shared = crops.filtered(lambda c: c.bed_share == 50)
        self.assertEqual(len(shared), 2)
        self.assertFalse(shared.filtered('has_overlap'))
        self.assertTrue(self.env['garden.crop'].get_seed_needs([('season_id', '=', season.id)]))

    def test_demo_operations(self):
        if not self.env.ref('odoo_garden.demo_season_2027', raise_if_not_found=False):
            self.skipTest("Données de démonstration non installées.")
        ref = self.env.ref
        self.assertEqual(len(self.env['hr.employee'].search([('name', 'in', ('Léa Maraîchère', 'Hugo Cultivateur', 'Sarah Saisonnière'))])), 3)
        # opération d'îlot répartie entre les cultures en place le 10 juin 2027
        irrigation = ref('odoo_garden.demo_operation_irrigation_n1')
        shares = {a.crop_id: round(a.share, 2) for a in irrigation.allocation_ids}
        self.assertEqual(shares, {
            ref('odoo_garden.demo_crop_2027_carrot_nantes_n1_01'): 40.0,
            ref('odoo_garden.demo_crop_2027_zucchini_verte_n1_03'): 40.0,
            ref('odoo_garden.demo_crop_2027_bean_contender_n1_05'): 20.0,
        })
        self.assertAlmostEqual(sum(irrigation.allocation_ids.mapped('hours')), 2.0)
        self.assertEqual(ref('odoo_garden.demo_operation_weeding_beds').state, 'done')
        self.assertEqual(len(ref('odoo_garden.demo_operation_weeding_beds').allocation_ids), 2)
        zucchini = ref('odoo_garden.demo_operation_weeding_zucchini')
        self.assertAlmostEqual(zucchini.total_hours, 3.5)
        self.assertAlmostEqual(zucchini.labour_cost, 1.5 * 18 + 2.0 * self.env['garden.operation']._get_default_hourly_rate())
        harvest = ref('odoo_garden.demo_operation_harvest_lettuce')
        self.assertTrue(harvest.harvest_product_id)
        # opérations générées par les itinéraires, sans doublon
        generated = self.env['garden.operation'].search([('template_step_id', '!=', False)])
        self.assertTrue(generated)
        self.assertFalse(ref('odoo_garden.demo_season_2027').crop_ids._generate_operations())
        # « Ma journée » : des opérations du jour et en retard pour l'employé de l'administrateur
        late = ref('odoo_garden.demo_operation_late_treatment')
        self.assertEqual(late.employee_ids.user_id, ref('base.user_admin'))
