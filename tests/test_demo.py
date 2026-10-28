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
