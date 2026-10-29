import glob
import os
import re

import polib

from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from odoo.tools import file_path

I18N_DIR = file_path('odoo_garden/i18n')
PLACEHOLDER = re.compile(r'%\([A-Za-z_]+\)[sdf]|%\.\d+f|%[sd]')
# Languages with a .po file in the module (French is the original vocabulary; the others are machine translations).
PO_CODES = sorted(os.path.basename(path)[:-3] for path in glob.glob(os.path.join(I18N_DIR, '*.po')))
ODOO_LANGS = {'fr': 'fr_FR', 'es': 'es_ES', 'de': 'de_DE', 'nl': 'nl_NL', 'it': 'it_IT', 'pt_BR': 'pt_BR'}
# Expected translations of key terms, per language.
EXPECTED = {
    'fr': {'bed': 'Planche', 'block': 'Îlot', 'menu_beds': 'Planches', 'root': 'Maraîchage', 'sowing': 'Semis',
           'planned': 'Planifiée', 'crop_manager': 'Chef de culture', 'message': 'Sélectionnez au moins une planche.'},
    'es': {'bed': 'Bancal', 'block': 'Bloque', 'menu_beds': 'Bancales', 'root': 'Horticultura de mercado',
           'sowing': 'Siembra', 'planned': 'Planificada', 'crop_manager': 'Responsable de cultivo',
           'message': 'Seleccione al menos un bancal.'},
    'de': {'bed': 'Beet', 'block': 'Block', 'menu_beds': 'Beete', 'root': 'Gemüsebau', 'sowing': 'Aussaat',
           'planned': 'Geplant', 'crop_manager': 'Kulturleiter', 'message': 'Wählen Sie mindestens ein Beet aus.'},
    'nl': {'bed': 'Bed', 'block': 'Blok', 'menu_beds': 'Bedden', 'root': 'Groenteteelt', 'sowing': 'Zaaien',
           'planned': 'Gepland', 'crop_manager': 'Teeltleider', 'message': 'Selecteer minstens één bed.'},
    'it': {'bed': 'Aiuola', 'block': 'Blocco', 'menu_beds': 'Aiuole', 'root': 'Orticoltura', 'sowing': 'Semina',
           'planned': 'Pianificata', 'crop_manager': 'Responsabile di coltura',
           'message': "Seleziona almeno un'aiuola."},
    'pt_BR': {'bed': 'Canteiro', 'block': 'Bloco', 'menu_beds': 'Canteiros', 'root': 'Horticultura',
              'sowing': 'Semeadura', 'planned': 'Planejada', 'crop_manager': 'Responsável pelo cultivo',
              'message': 'Selecione pelo menos um canteiro.'},
}


@tagged('post_install', '-at_install')
class TestGardenTranslationFiles(TransactionCase):
    """Consistency of the shipped .pot / .po files."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.pot = {entry.msgid: entry for entry in polib.pofile(os.path.join(I18N_DIR, 'odoo_garden.pot'))}

    def test_pot_has_source_terms_in_english(self):
        self.assertGreater(len(self.pot), 700)
        for term in ('Bed', 'Crop Template', 'Pre-Harvest Interval (days)', 'Regulatory Registers (France)', 'Sowing'):
            self.assertIn(term, self.pot)
        for msgid in self.pot:
            self.assertNotRegex(msgid, r'[éèêàçôûîï]', "French text left in the template: %r" % msgid)

    def test_pot_covers_every_kind_of_term(self):
        locations = {location for entry in self.pot.values() for location, _line in entry.occurrences}
        for prefix in ('model:ir.model.fields,field_description', 'model:ir.model.fields.selection', 'model:ir.ui.menu',
                       'model_terms:ir.ui.view', 'model:garden.operation.type,name', 'model:res.groups',
                       'code:addons/odoo_garden/models', 'model:ir.actions.server'):
            self.assertTrue(
                any(location.startswith(prefix) for location in locations), "No term extracted for %s" % prefix,
            )
        self.assertTrue(any('static/src/js' in location for location in locations), "No JavaScript term")
        self.assertTrue(any('static/src/xml' in location for location in locations), "No OWL template term")
        # QR labels and registers (QWeb report templates)
        self.assertTrue(any('odoo_garden.report_garden_bed_label' in location for location in locations))
        self.assertTrue(any('odoo_garden.report_garden_compliance' in location for location in locations))

    def test_po_files_are_complete_and_consistent(self):
        for code in PO_CODES:
            po = polib.pofile(os.path.join(I18N_DIR, '%s.po' % code))
            self.assertEqual({e.msgid for e in po}, set(self.pot), "%s.po does not match the template" % code)
            for entry in po:
                self.assertTrue(entry.msgstr, "%s: empty translation for %r" % (code, entry.msgid))
                self.assertEqual(
                    sorted(PLACEHOLDER.findall(entry.msgid)), sorted(PLACEHOLDER.findall(entry.msgstr)),
                    "%s: placeholders differ for %r" % (code, entry.msgid),
                )
                self.assertEqual(
                    entry.msgid.count('<'), entry.msgstr.count('<'), "%s: markup differs for %r" % (code, entry.msgid),
                )
            self.assertEqual(po.metadata.get('Language'), code)
            if code != 'fr':
                with open(os.path.join(I18N_DIR, '%s.po' % code), encoding='utf-8') as po_file:
                    self.assertIn('Machine translation', po_file.read(1500), "%s.po must say it is machine-made" % code)


@tagged('post_install', '-at_install')
class TestGardenTranslationLoading(TransactionCase):
    """The .po files load and translate the main kinds of terms."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.langs = {code: ODOO_LANGS[code] for code in PO_CODES if code in ODOO_LANGS}
        for lang in cls.langs.values():
            cls.env['res.lang']._activate_lang(lang)
        cls.env['ir.module.module']._load_module_terms(['odoo_garden'], list(cls.langs.values()), overwrite=True)

    def _field(self, lang, model, field):
        return self.env[model].with_context(lang=lang).fields_get([field])[field]

    def test_english_source(self):
        self.assertEqual(self._field('en_US', 'garden.bed', 'area')['string'], 'Area (m²)')
        self.assertEqual(self.env.ref('odoo_garden.menu_garden_bed').with_context(lang='en_US').name, 'Beds')
        self.assertEqual(self.env.ref('odoo_garden.operation_type_sowing').with_context(lang='en_US').name, 'Sowing')

    def test_field_labels_and_selections(self):
        for code, lang in self.langs.items():
            expected = EXPECTED[code]
            self.assertEqual(self._field(lang, 'garden.crop', 'bed_id')['string'], expected['bed'], lang)
            self.assertEqual(self._field(lang, 'garden.bed', 'garden_id')['string'], expected['block'], lang)
            states = dict(self._field(lang, 'garden.operation', 'state')['selection'])
            self.assertEqual(states['planned'], expected['planned'], lang)

    def test_menus_groups_and_default_data(self):
        for code, lang in self.langs.items():
            expected = EXPECTED[code]
            self.assertEqual(self.env.ref('odoo_garden.menu_garden_bed').with_context(lang=lang).name, expected['menu_beds'], lang)
            self.assertEqual(self.env.ref('odoo_garden.menu_garden_root').with_context(lang=lang).name, expected['root'], lang)
            self.assertEqual(
                self.env.ref('odoo_garden.group_garden_chef').with_context(lang=lang).name, expected['crop_manager'], lang,
            )
            self.assertEqual(
                self.env.ref('odoo_garden.operation_type_sowing').with_context(lang=lang).name, expected['sowing'], lang,
            )
            registers = self.env.ref('odoo_garden.menu_garden_compliance').with_context(lang=lang).name
            self.assertRegex(registers, r'Fran', lang)  # the registers stay presented as French ones

    def test_python_messages(self):
        message = 'Select at least one bed.'
        wizard = self.env['garden.season.plan.wizard']
        self.assertEqual(wizard.with_context(lang='en_US').env._(message), message)
        for code, lang in self.langs.items():
            self.assertEqual(wizard.with_context(lang=lang).env._(message), EXPECTED[code]['message'], lang)

    def test_view_terms(self):
        view = self.env.ref('odoo_garden.view_garden_bed_form')
        english = self.env['garden.bed'].with_context(lang='en_US').get_view(view.id, 'form')['arch']
        for code, lang in self.langs.items():
            arch = self.env['garden.bed'].with_context(lang=lang).get_view(view.id, 'form')['arch']
            self.assertNotEqual(arch, english, lang)
            if code == 'fr':
                self.assertIn('Nom de la planche', arch)
