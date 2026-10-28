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

    def test_demo_stock(self):
        ref = self.env.ref
        if not ref('odoo_garden.demo_season_2027', raise_if_not_found=False):
            self.skipTest("Données de démonstration non installées.")
        company = self.env.company
        stock = company._get_garden_stock_location()

        def qty(product, lot=None):
            domain = [('product_id', '=', product.id), ('location_id', '=', stock.id)]
            if lot:
                domain.append(('lot_id', '=', lot.id))
            return sum(self.env['stock.quant'].search(domain).mapped('quantity'))

        crop = ref('odoo_garden.demo_crop_2027_tomato_coeur_s1_01')
        self.assertEqual(ref('odoo_garden.demo_operation_sowing_tomato').state, 'done')
        # intrants consommés : 300 g de semence - 8, 40 sacs - 3, 200 kg - 12, 25 kg - 1,5
        self.assertAlmostEqual(qty(ref('odoo_garden.demo_input_potting_soil')), 37.0)
        self.assertAlmostEqual(qty(ref('odoo_garden.demo_input_fertilizer')), 188.0)
        self.assertAlmostEqual(qty(ref('odoo_garden.demo_input_copper')), 23.5)
        seed_lot = ref('odoo_garden.demo_lot_seed_tomato')
        self.assertAlmostEqual(qty(ref('odoo_garden.demo_seed_tomato_coeur'), seed_lot), 292.0)
        # coûts d'intrants (lecture en administrateur)
        self.assertAlmostEqual(
            ref('odoo_garden.demo_operation_sowing_tomato').input_cost, 8 * 0.45 + 3 * 12.0,
        )
        self.assertAlmostEqual(crop.input_cost, 8 * 0.45 + 36.0 + 12 * 1.8 + 1.5 * 6.5)
        # récolte : 45 kg sur le lot de la culture, 3 kg perdus avant récolte, 4 kg rebutés
        lot = crop.lot_ids
        self.assertEqual(len(lot), 1)
        self.assertEqual(lot.name, crop.name)
        self.assertAlmostEqual(crop.harvested_qty, 45.0)
        self.assertAlmostEqual(qty(ref('odoo_garden.demo_harvest_tomato_coeur'), lot), 41.0)
        self.assertFalse(ref('odoo_garden.demo_loss_tomato_pre').scrap_id)
        self.assertEqual(ref('odoo_garden.demo_loss_tomato_post').scrap_id.lot_id, lot)
        self.assertAlmostEqual(crop.loss_rate, 7.0 / 52.0, places=3)
        # traçabilité depuis le lot de récolte : lot de semence utilisé
        trace = self.env['garden.traceability'].browse(lot.action_garden_traceability()['res_id'])
        self.assertEqual(trace.seed_lot_ids, seed_lot)
        self.assertEqual(len(trace.out_line_ids), 1)
        # la récolte de laitue de la phase 3 reste valide (produit non stockable, sans lot)
        lettuce = ref('odoo_garden.demo_operation_harvest_lettuce')
        self.assertEqual(lettuce.move_ids.garden_kind, 'harvest')
        self.assertFalse(lettuce.move_ids.move_line_ids.lot_id)
        self.assertAlmostEqual(lettuce.crop_ids.harvested_qty, 28.0)
