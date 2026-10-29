from psycopg2 import IntegrityError

from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from odoo.tools import mute_logger


@tagged('post_install', '-at_install')
class TestGardenCatalog(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.species = cls.env['garden.species'].create({'name': 'Tomate test', 'family': 'solanaceae'})
        cls.seed = cls.env['product.product'].create({'name': 'Semence tomate test'})
        cls.harvest = cls.env['product.product'].create({'name': 'Tomate test (kg)', 'list_price': 5.5})
        cls.other = cls.env['product.product'].create({'name': 'Produit sans lien'})
        cls.variety = cls.env['garden.variety'].create({
            'name': 'Cœur de bœuf', 'species_id': cls.species.id,
            'seed_product_id': cls.seed.id, 'harvest_product_id': cls.harvest.id,
            'seeds_per_gram': 300, 'germination_rate': 90,
        })

    def test_species_defaults_and_unique(self):
        self.assertEqual(self.species.rotation_years, 3)
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'), self.cr.savepoint():
            self.env['garden.species'].create({'name': 'Tomate test'})

    def test_variety_germination_range(self):
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'), self.cr.savepoint():
            self.variety.germination_rate = 120

    def test_template_density_and_price(self):
        template = self.env['garden.crop.template'].create({
            'name': 'Tomate test sous abri', 'variety_id': self.variety.id,
            'row_spacing': 50, 'plant_spacing': 40,
        })
        self.assertAlmostEqual(template.density, 5.0)
        self.assertEqual(template.species_id, self.species)
        self.assertEqual(template.expected_price, 5.5)
        template.plant_spacing = 0
        self.assertEqual(template.density, 0.0)

    def test_template_steps(self):
        sowing = self.env.ref('odoo_garden.operation_type_sowing')
        harvest = self.env.ref('odoo_garden.operation_type_harvest')
        template = self.env['garden.crop.template'].create({
            'name': 'Template', 'variety_id': self.variety.id,
            'step_ids': [
                (0, 0, {'operation_type_id': harvest.id, 'day_offset': 90, 'sequence': 20}),
                (0, 0, {'operation_type_id': sowing.id, 'day_offset': 0, 'sequence': 10, 'expected_duration': 0.01}),
            ],
        })
        self.assertEqual(template.step_ids.operation_type_id, sowing | harvest)
        first = template.step_ids.sorted(lambda step: (step.sequence, step.id))[0]
        self.assertEqual(first.operation_type_id, sowing)
        self.assertEqual(first.category, 'sowing')
        copy = template.copy()
        self.assertEqual(len(copy.step_ids), 2)
        template.unlink()
        self.assertFalse(self.env['garden.crop.template.step'].search([('template_id', '=', template.id)]))

    def test_default_operation_types(self):
        types = self.env['garden.operation.type'].search([])
        categories = set(types.mapped('category'))
        for category in ('sowing', 'transplanting', 'planting', 'irrigation', 'weeding', 'fertilization',
                         'treatment', 'mulching', 'harvest', 'post_harvest'):
            self.assertIn(category, categories)

    def test_product_link(self):
        seed_tmpl = self.seed.product_tmpl_id
        self.assertEqual(seed_tmpl.garden_variety_ids, self.variety)
        self.assertEqual(self.harvest.product_tmpl_id.garden_variety_ids, self.variety)
        self.assertFalse(self.other.product_tmpl_id.garden_variety_ids)
        Template = self.env['product.template']
        found = Template.search([('is_garden_product', '=', True)])
        self.assertIn(seed_tmpl, found)
        self.assertIn(self.harvest.product_tmpl_id, found)
        self.assertNotIn(self.other.product_tmpl_id, found)
        not_found = Template.search([('is_garden_product', '=', False)])
        self.assertIn(self.other.product_tmpl_id, not_found)
        self.assertNotIn(seed_tmpl, not_found)


@tagged('post_install', '-at_install')
class TestGardenProductionCatalog(TransactionCase):
    """Catalogue livré à l'installation (hors démonstration) : espèces, produits récoltés, intrants, types."""

    def test_species_are_complete_and_consistent(self):
        self.assertEqual(self.env.ref('odoo_garden.species_leek').family, 'amaryllidaceae')
        self.assertTrue(self.env.ref('odoo_garden.species_lambs_lettuce'))
        self.assertGreaterEqual(self.env['garden.species'].search_count([]), 50)

    def test_harvest_products_are_lot_tracked_in_kg(self):
        product = self.env.ref('odoo_garden.product_harvest_tomato')
        self.assertEqual(product.tracking, 'lot')
        self.assertEqual(product.uom_id, self.env.ref('uom.product_uom_kgm'))
        self.assertFalse(product.purchase_ok)

    def test_inputs_have_a_garden_type_and_no_phytosanitary(self):
        inputs = self.env['product.template'].browse(self.env['ir.model.data'].search([
            ('module', '=', 'odoo_garden'), ('model', '=', 'product.template'), ('name', '=like', 'product_input_%'),
        ]).mapped('res_id'))
        self.assertTrue(inputs)
        self.assertTrue(all(inputs.mapped('garden_input_type')))
        self.assertNotIn('phytosanitary', inputs.mapped('garden_input_type'))
        self.assertEqual(self.env.ref('odoo_garden.product_input_horn_meal').nitrogen_content, 13)

    def test_operation_types_cover_all_categories(self):
        types = self.env['garden.operation.type'].search([])
        self.assertGreaterEqual(len(types), 30)
        self.assertTrue(set(types.mapped('category')) >= {
            'soil_preparation', 'sowing', 'transplanting', 'planting', 'irrigation', 'weeding', 'fertilization',
            'treatment', 'mulching', 'harvest', 'post_harvest', 'other',
        })
        self.assertEqual(self.env.ref('odoo_garden.operation_type_hilling').default_scope, 'crop')
