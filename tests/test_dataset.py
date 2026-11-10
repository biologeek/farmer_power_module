from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user

from odoo.addons.farmer_power import datasets


@tagged('post_install', '-at_install')
class TestGardenDatasetContent(TransactionCase):
    """Consistency of the static data of every language (no database writes)."""

    def test_every_dataset_is_consistent(self):
        for code in datasets.LANGUAGES:
            data = datasets.get_dataset(code)
            self.assertTrue(data, code)
            for species_key, names in data.VARIETIES.items():
                with self.subTest(code=code, species=species_key):
                    self.assertIn(species_key, datasets.SPECIES_SEEDS)
                    self.assertTrue(self.env.ref('farmer_power.species_' + species_key, raise_if_not_found=False))
                    self.assertTrue(self.env.ref('farmer_power.product_harvest_' + species_key, raise_if_not_found=False))
                    self.assertEqual(len(names), len(set(names)), 'duplicate variety name')
            self.assertEqual(set(data.INPUT_NAMES), set(datasets.INPUTS), code)
            self.assertGreaterEqual(sum(len(v) for v in data.VARIETIES.values()), 90, code)

    def test_agronomic_values_are_sane(self):
        for species_key, (seeds, germination) in datasets.SPECIES_SEEDS.items():
            self.assertGreaterEqual(seeds, 0, species_key)
            self.assertTrue(0 < germination <= 100, species_key)
        for key, (input_type, uom, nitrogen, organic) in datasets.INPUTS.items():
            self.assertIn(input_type, ('fertilizer', 'amendment', 'substrate'), key)
            if input_type != 'fertilizer':
                self.assertEqual(nitrogen, 0.0, key)  # nitrogen only counts for fertilizers
            self.assertNotEqual(input_type, 'phytosanitary', key)  # regulatory products are never shipped

    def test_code_for_lang(self):
        self.assertEqual(datasets.code_for_lang('fr_FR'), 'fr')
        self.assertEqual(datasets.code_for_lang('fr_BE'), 'fr')
        self.assertEqual(datasets.code_for_lang('es_MX'), 'es')
        self.assertEqual(datasets.code_for_lang('pt_BR'), 'pt_BR')
        self.assertIsNone(datasets.code_for_lang('pt_PT'))
        self.assertIsNone(datasets.code_for_lang('en_US'))
        self.assertIsNone(datasets.code_for_lang(False))


@tagged('post_install', '-at_install')
class TestGardenDatasetLoading(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Dataset = self.env['garden.dataset']

    def test_load_each_language(self):
        for code in datasets.LANGUAGES:
            with self.subTest(code=code):
                data = datasets.get_dataset(code)
                expected = sum(len(names) for names in data.VARIETIES.values())
                before = self.env['garden.variety'].search_count([])
                counts = self.Dataset._load_dataset(code)
                self.assertEqual(counts['inputs'], len(datasets.INPUTS))
                self.assertGreater(counts['varieties'], 0)
                self.assertLessEqual(counts['varieties'], expected)
                self.assertEqual(self.env['garden.variety'].search_count([]), before + counts['varieties'])

    def test_varieties_are_linked_to_species_and_harvest_product(self):
        self.Dataset._load_dataset('fr')
        variety = self.env.ref("farmer_power.dataset_fr_variety_tomato_coeur_de_boeuf")
        self.assertEqual(variety.name, 'Cœur de Bœuf')
        self.assertEqual(variety.species_id, self.env.ref('farmer_power.species_tomato'))
        self.assertEqual(
            variety.harvest_product_id.product_tmpl_id, self.env.ref('farmer_power.product_harvest_tomato'),
        )
        self.assertEqual(variety.germination_rate, 90)
        self.assertEqual(variety.seeds_per_gram, 300)
        garlic = self.env['garden.variety'].search([('name', '=', 'Messidrome')])
        self.assertEqual(garlic.seeds_per_gram, 0)  # propagated by cloves

    def test_inputs_feed_the_fertilization_register(self):
        self.Dataset._load_dataset('de')
        feather = self.env.ref('farmer_power.dataset_de_input_feather_meal')
        self.assertEqual(feather.name, 'Federmehl (kg)')
        self.assertEqual(feather.garden_input_type, 'fertilizer')
        self.assertEqual(feather.nitrogen_content, 12.0)
        self.assertTrue(feather.is_organic_allowed)
        self.assertEqual(feather.uom_id, self.env.ref('uom.product_uom_kgm'))
        npk = self.env.ref('farmer_power.dataset_de_input_npk')
        self.assertFalse(npk.is_organic_allowed)  # flagged by the organic certification export
        ash = self.env.ref('farmer_power.dataset_de_input_wood_ash')
        self.assertEqual(ash.garden_input_type, 'amendment')
        self.assertFalse(self.env['product.template'].search([
            ('garden_input_type', '=', 'phytosanitary'), ('name', 'like', 'dataset')]))

    def test_inputs_do_not_duplicate_the_shipped_ones(self):
        shipped = self.env['product.template'].search([('garden_input_type', '!=', False)])
        self.Dataset._load_dataset('fr')
        loaded = self.env['product.template'].search([('garden_input_type', '!=', False)]) - shipped
        self.assertEqual(len(loaded), len(datasets.INPUTS))
        for template in loaded:
            self.assertNotIn(template.name, shipped.mapped('name'))

    def test_reload_is_idempotent_and_keeps_user_edits(self):
        self.Dataset._load_dataset('es')
        variety = self.env.ref('farmer_power.dataset_es_variety_tomato_raf')
        variety.germination_rate = 77.0
        counts = self.Dataset._load_dataset('es')
        self.assertEqual(counts, {'varieties': 0, 'inputs': 0})
        self.assertEqual(variety.germination_rate, 77.0)

    def test_manual_variety_is_not_duplicated(self):
        species = self.env.ref('farmer_power.species_tomato')
        manual = self.env['garden.variety'].create({'name': 'Marmande', 'species_id': species.id})
        self.Dataset._load_dataset('fr')
        self.assertEqual(self.env['garden.variety'].search_count([('name', '=', 'Marmande'), ('species_id', '=', species.id)]), 1)
        self.assertTrue(manual.exists())

    def test_two_languages_coexist(self):
        self.Dataset._load_dataset('fr')
        self.Dataset._load_dataset('nl')
        self.assertTrue(self.env.ref('farmer_power.dataset_fr_variety_tomato_marmande'))
        self.assertTrue(self.env.ref('farmer_power.dataset_nl_variety_tomato_moneymaker'))

    def test_unknown_language_is_refused(self):
        with self.assertRaises(Exception):
            self.Dataset._load_dataset('xx')

    def test_guess_follows_admin_language(self):
        admin = self.env.ref('base.user_admin')
        self.env['res.lang']._activate_lang('it_IT')
        admin.lang = 'it_IT'
        self.assertEqual(self.Dataset._guess_dataset_code(), 'it')
        admin.lang = 'en_US'
        self.env.company.partner_id.lang = 'en_US'
        self.assertIsNone(self.Dataset._guess_dataset_code())


@tagged('post_install', '-at_install')
class TestGardenDatasetWizard(TransactionCase):

    def test_wizard_loads_catalog_and_notifies(self):
        chef = new_test_user(self.env, login='dataset_chef', groups='farmer_power.group_garden_chef,base.group_user')
        wizard = self.env['garden.dataset.wizard'].with_user(chef).create({'lang_code': 'pt_BR'})
        action = wizard.action_load()
        self.assertEqual(action['tag'], 'display_notification')
        self.assertTrue(self.env.ref('farmer_power.dataset_pt_BR_variety_tomato_santa_cruz'))
        self.assertTrue(self.env.ref('farmer_power.dataset_pt_BR_input_wood_ash'))

    def test_worker_cannot_open_wizard(self):
        worker = new_test_user(self.env, login='dataset_worker', groups='farmer_power.group_garden_worker,base.group_user')
        with self.assertRaises(AccessError):
            self.env['garden.dataset.wizard'].with_user(worker).create({'lang_code': 'fr'})
