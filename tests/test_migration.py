import importlib.util

from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from odoo.tools import file_path


@tagged('post_install', '-at_install')
class TestGardenMigration(TransactionCase):
    """The 19.0.1.7.0 migration renames the former French default records (noupdate data)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        spec = importlib.util.spec_from_file_location(
            'garden_post_migration_1_7_0', file_path('odoo_garden/migrations/19.0.1.7.0/post-migration.py'),
        )
        cls.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.migration)

    def test_renames_french_defaults_and_keeps_custom_names(self):
        sowing = self.env.ref('odoo_garden.operation_type_sowing')
        weeding = self.env.ref('odoo_garden.operation_type_weeding')
        location = self.env.ref('odoo_garden.stock_location_garden_production')
        rule = self.env.ref('odoo_garden.garden_farm_company_rule')
        self.env['res.lang']._activate_lang('fr_FR')
        sowing.with_context(lang='en_US').name = 'Semis'
        weeding.with_context(lang='en_US').name = 'Mon désherbage'  # renamed by the user: untouched
        location.name = 'Production maraîchage'
        rule.name = 'Ferme : multi-société'
        self.migration.rename_defaults(self.env)
        self.assertEqual(sowing.with_context(lang='en_US').name, 'Sowing')
        self.assertEqual(sowing.with_context(lang='fr_FR').name, 'Semis')
        self.assertEqual(weeding.with_context(lang='en_US').name, 'Mon désherbage')
        self.assertEqual(location.name, 'Market Gardening Production')
        self.assertEqual(rule.name, 'Farm: multi-company')

    def test_is_idempotent_on_a_fresh_database(self):
        before = self.env.ref('odoo_garden.operation_type_sowing').with_context(lang='en_US').name
        self.migration.rename_defaults(self.env)
        self.assertEqual(self.env.ref('odoo_garden.operation_type_sowing').with_context(lang='en_US').name, before)
