from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestGardenPurchaseTranslations(TransactionCase):

    def test_bridge_terms_are_translated(self):
        langs = {'fr_FR': 'Créer les demandes de prix', 'de_DE': 'Angebotsanfragen erstellen',
                 'es_ES': 'Crear solicitudes de presupuesto', 'nl_NL': 'Offerteaanvragen aanmaken',
                 'it_IT': 'Crea richieste di offerta', 'pt_BR': 'Criar solicitações de cotação'}
        for lang in langs:
            self.env['res.lang']._activate_lang(lang)
        self.env['ir.module.module']._load_module_terms(['farmer_power_purchase'], list(langs), overwrite=True)
        action = self.env.ref('farmer_power_purchase.action_garden_seed_order_wizard')
        self.assertEqual(action.with_context(lang='en_US').name, 'Create Requests for Quotation')
        for lang, expected in langs.items():
            self.assertEqual(action.with_context(lang=lang).name, expected, lang)
        message = 'The requests for quotation were already created.'
        wizard = self.env['garden.seed.order.wizard']
        self.assertNotEqual(wizard.with_context(lang='fr_FR').env._(message), message)
