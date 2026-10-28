import io

from odoo.exceptions import AccessError, UserError
from odoo.tests import HttpCase, tagged

from .test_compliance_fields import GardenComplianceCase


class GardenRegisterCase(GardenComplianceCase):

    def _wizard(self, user=None, register='phyto', **vals):
        wizard = self.env['garden.compliance.wizard'].with_user(user or self.chef).create(
            dict(vals, register=register),
        )
        wizard._compute_lines()
        return wizard


@tagged('post_install', '-at_install')
class TestGardenPhytoRegister(GardenRegisterCase):

    def test_register_content(self):
        operation = self._treatment(
            '2027-06-10', quantity=0.18, target='Mildiou', weather_notes='Sec, 18 °C, vent faible',
            employee_ids=[(6, 0, (self.alice | self.bob).ids)],
        )
        wizard = self._wizard()
        line = wizard.phyto_line_ids
        self.assertEqual(len(line), 1)
        self.assertEqual(str(line.date), '2027-06-10')
        self.assertEqual(line.crop_id, self.crop)
        self.assertEqual(line.season_id, self.season)
        self.assertEqual(line.bed_id, self.bed)
        self.assertEqual(line.parcel, "%s / %s / %s" % (self.site.name, self.garden.name, self.bed.name))
        self.assertAlmostEqual(line.treated_area, 36.0)
        self.assertEqual(line.product_id, self.phyto)
        self.assertEqual(line.amm_number, 'AMM-TEST-0001')
        self.assertAlmostEqual(line.quantity, 0.18)
        self.assertAlmostEqual(line.dose, 50.0)  # 0,18 pour 36 m² = 50 par ha
        self.assertEqual(line.uom_id, self.phyto.uom_id)
        self.assertEqual(set(line.operator.split(', ')), {'Alice test', 'Bob test'})
        self.assertEqual(line.target, 'Mildiou')
        self.assertEqual(line.weather_notes, 'Sec, 18 °C, vent faible')
        self.assertEqual(line.operation_id, operation)

    def test_only_done_phytosanitary_inputs(self):
        # planifiée, annulée, ou produit non phytosanitaire : absents du registre
        self._operation(
            type_id=self.type_treatment.id, crop_ids=[(6, 0, self.crop.ids)], date='2027-06-01',
            input_ids=[(0, 0, {'product_id': self.phyto.id, 'quantity': 1})],
        )
        cancelled = self._treatment('2027-06-02')
        cancelled.action_reset_planned()
        cancelled.action_cancel()
        self._operation(
            type_id=self.type_fertilization.id, crop_ids=[(6, 0, self.crop.ids)], date='2027-06-03',
            input_ids=[(0, 0, {'product_id': self.nitro.id, 'quantity': 1})],
        ).action_done()
        done = self._treatment('2027-06-04')
        self.assertEqual(self._wizard().phyto_line_ids.operation_id, done)

    def test_operation_split_between_crops(self):
        other = self._crop(planned_sowing_date='2027-03-01', bed_id=self.bed2.id)  # 10 m²
        operation = self._operation(
            type_id=self.type_treatment.id, scope='bed', bed_ids=[(6, 0, (self.bed | self.bed2).ids)],
            date='2027-06-10', input_ids=[(0, 0, {'product_id': self.phyto.id, 'quantity': 4.6})],
        )
        operation.action_done()
        lines = self._wizard().phyto_line_ids
        self.assertEqual(lines.crop_id, self.crop | other)
        by_crop = {line.crop_id: line for line in lines}
        self.assertAlmostEqual(by_crop[self.crop].quantity, 4.6 * 36 / 46)
        self.assertAlmostEqual(by_crop[other].quantity, 4.6 * 10 / 46)
        self.assertAlmostEqual(by_crop[other].treated_area, 10.0)
        self.assertAlmostEqual(sum(lines.mapped('quantity')), 4.6)
        self.assertAlmostEqual(by_crop[other].dose, by_crop[self.crop].dose)

    def test_filters(self):
        other_season = self.env['garden.season'].create({
            'name': 'Saison 2028 test', 'date_start': '2028-01-01', 'date_end': '2028-12-31',
        })
        other = self._crop(planned_sowing_date='2028-03-01', bed_id=self.bed2.id, season_id=other_season.id)
        first = self._treatment('2027-06-10')
        second = self._treatment('2028-06-10', crop=other)
        self.assertEqual(self._wizard().phyto_line_ids.operation_id, first | second)
        self.assertEqual(self._wizard(date_from='2028-01-01').phyto_line_ids.operation_id, second)
        self.assertEqual(self._wizard(date_to='2027-12-31').phyto_line_ids.operation_id, first)
        self.assertEqual(
            self._wizard(date_from='2027-06-10', date_to='2027-06-10').phyto_line_ids.operation_id, first,
        )
        self.assertEqual(self._wizard(season_id=other_season.id).phyto_line_ids.operation_id, second)
        self.assertEqual(self._wizard(crop_ids=[(6, 0, self.crop.ids)]).phyto_line_ids.operation_id, first)
        self.assertFalse(self._wizard(season_id=other_season.id, date_to='2027-12-31').phyto_line_ids)

    def test_recompute_replaces_lines(self):
        self._treatment('2027-06-10')
        wizard = self._wizard()
        self.assertEqual(len(wizard.line_ids), 1)
        wizard._compute_lines()
        self.assertEqual(len(wizard.line_ids), 1)
        self._treatment('2027-06-20')
        wizard._compute_lines()
        self.assertEqual(len(wizard.line_ids), 2)

    def test_access_rights(self):
        with self.assertRaises(AccessError):
            self.env['garden.compliance.wizard'].with_user(self.worker).create({'register': 'phyto'})
        with self.assertRaises(AccessError):
            self.env['garden.compliance.line'].with_user(self.worker).search([])
        self.assertTrue(self._wizard(user=self.chef))
        self.assertTrue(self._wizard(user=self.manager))
        # le chef de culture lit le registre sans coût ni droits sur les produits
        self._treatment('2027-06-10')
        line = self._wizard(user=self.chef).phyto_line_ids
        self.assertEqual(line.amm_number, 'AMM-TEST-0001')
        wizard = self._wizard(user=self.chef)
        with self.assertRaises(AccessError):
            wizard.with_user(self.worker).action_compute()

    def test_multi_company_registers(self):
        other_company = self.env['res.company'].create({'name': 'Autre ferme'})
        self._treatment('2027-06-10')
        wizard = self.env['garden.compliance.wizard'].with_user(self.chef).with_company(self.company).create({})
        self.assertEqual(wizard.env.companies, self.company)
        wizard._compute_lines()
        self.assertEqual(len(wizard.line_ids), 1)
        other_chef = self.env['res.users'].with_company(other_company).create({
            'name': 'Chef autre', 'login': 'garden_other_chef', 'company_id': other_company.id,
            'company_ids': [(6, 0, other_company.ids)],
            'group_ids': [(6, 0, [self.env.ref('odoo_garden.group_garden_chef').id])],
        })
        other_wizard = self.env['garden.compliance.wizard'].with_user(other_chef).with_company(other_company).create({})
        other_wizard._compute_lines()
        self.assertFalse(other_wizard.line_ids)

    def test_xlsx_export(self):
        import openpyxl
        self._treatment('2027-06-10', quantity=0.36, target='Mildiou', weather_notes='Sec')
        wizard = self._wizard()
        filename, content = wizard.with_user(self.chef)._get_xlsx()
        self.assertTrue(filename.endswith('.xlsx'))
        workbook = openpyxl.load_workbook(io.BytesIO(content))
        sheet = workbook.worksheets[0]
        rows = list(sheet.iter_rows(values_only=True))
        self.assertEqual(len(rows), 2)
        header, data = rows
        self.assertIn('N° AMM', header)
        values = dict(zip(header, data))
        self.assertEqual(values['Culture'], self.crop.name)
        self.assertEqual(values['Produit'], self.phyto.display_name)
        self.assertEqual(values['N° AMM'], 'AMM-TEST-0001')
        self.assertAlmostEqual(values['Dose (par ha)'], 100.0)
        self.assertAlmostEqual(values['Quantité utilisée'], 0.36)
        self.assertAlmostEqual(values['Surface traitée (m²)'], 36.0)
        self.assertEqual(values['Cible'], 'Mildiou')
        self.assertEqual(values['Date'].strftime('%Y-%m-%d'), '2027-06-10')
        with self.assertRaises(AccessError):
            wizard.with_user(self.worker)._get_xlsx()

    def test_pdf_report_renders(self):
        self._treatment('2027-06-10', target='Mildiou')
        wizard = self._wizard()
        report = self.env.ref('odoo_garden.action_report_garden_compliance')
        self.assertEqual(report.report_type, 'qweb-pdf')
        self.assertEqual(report.model, 'garden.compliance.wizard')
        self.assertEqual(report.paperformat_id.orientation, 'Landscape')
        html, report_type = self.env['ir.actions.report']._render_qweb_html(report.report_name, wizard.ids)
        self.assertEqual(report_type, 'html')
        text = html.decode()
        for expected in ('Registre phytosanitaire', self.crop.name, 'AMM-TEST-0001', 'Mildiou', 'Phyto test'):
            self.assertIn(expected, text)
        action = wizard.action_print()
        self.assertEqual(action['report_name'], 'odoo_garden.report_garden_compliance')
        self.assertEqual(action['context']['active_ids'], wizard.ids)


@tagged('post_install', '-at_install')
class TestGardenComplianceDownload(HttpCase, GardenRegisterCase):

    def test_xlsx_download(self):
        import openpyxl
        self._treatment('2027-06-10')
        wizard = self._wizard()
        self.authenticate('garden_stock_chef', 'garden_stock_chef')
        response = self.url_open('/odoo_garden/compliance/xlsx/%d' % wizard.id)
        self.assertEqual(response.status_code, 200)
        self.assertIn('spreadsheetml', response.headers['Content-Type'])
        sheet = openpyxl.load_workbook(io.BytesIO(response.content)).worksheets[0]
        self.assertEqual(sheet.max_row, 2)
        # un ouvrier n'obtient rien
        self.authenticate('garden_stock_worker', 'garden_stock_worker')
        response = self.url_open('/odoo_garden/compliance/xlsx/%d' % wizard.id)
        self.assertNotEqual(response.status_code, 200)


@tagged('post_install', '-at_install')
class TestGardenFertilizationRegister(GardenRegisterCase):

    def _fertilize(self, date, quantity, crop=None, product=None, uom=None, **vals):
        line = {'product_id': (product or self.nitro).id, 'quantity': quantity}
        if uom:
            line['uom_id'] = uom.id
        operation = self._operation(
            type_id=self.type_fertilization.id, crop_ids=[(6, 0, (crop or self.crop).ids)], date=date,
            input_ids=[(0, 0, line)], **vals,
        )
        operation.action_done()
        return operation

    def test_nitrogen_units(self):
        self._fertilize('2027-04-10', 10.0)  # 10 kg à 10 % = 1 kg N sur 36 m²
        line = self._wizard(register='fertilization').fertilization_line_ids
        self.assertEqual(len(line), 1)
        self.assertEqual(line.season_id, self.season)
        self.assertEqual(line.bed_id, self.bed)
        self.assertAlmostEqual(line.nitrogen_content, 10.0)
        self.assertAlmostEqual(line.quantity_kg, 10.0)
        self.assertAlmostEqual(line.nitrogen_kg, 1.0)
        self.assertAlmostEqual(line.treated_area, 36.0)
        self.assertAlmostEqual(line.nitrogen_per_ha, 10000.0 / 36.0, delta=0.01)
        self.assertFalse(line.note)

    def test_unit_conversion_and_missing_data(self):
        gram = self.env.ref('uom.product_uom_gram')
        self._fertilize('2027-04-10', 500.0, uom=gram)  # 0,5 kg
        poor = self._storable('Engrais sans azote', garden_input_type='fertilizer', uom_id=self.env.ref('uom.product_uom_kgm').id)
        self._set_stock(poor, 10)
        self._fertilize('2027-04-11', 2.0, product=poor)
        litre = self.env.ref('uom.product_uom_litre')
        self._fertilize('2027-04-12', 3.0, uom=litre)
        lines = {l.date.day: l for l in self._wizard(register='fertilization').fertilization_line_ids}
        self.assertAlmostEqual(lines[10].nitrogen_kg, 0.05)
        self.assertAlmostEqual(lines[10].quantity_kg, 0.5)
        self.assertEqual(lines[11].nitrogen_kg, 0.0)
        self.assertIn('Teneur en azote non renseignée', lines[11].note)
        self.assertEqual(lines[12].nitrogen_kg, 0.0)
        self.assertIn('Unité non convertible', lines[12].note)

    def test_summary_per_bed_and_season(self):
        other = self._crop(planned_sowing_date='2027-03-01', bed_id=self.bed2.id)  # 10 m²
        self._fertilize('2027-04-10', 10.0)
        self._fertilize('2027-05-10', 5.0)
        self._fertilize('2027-04-10', 2.0, crop=other)
        wizard = self._wizard(register='fertilization')
        summary = {bed: (kg, per_ha) for _season, bed, kg, per_ha in wizard._get_fertilization_summary()}
        self.assertAlmostEqual(summary[self.bed][0], 1.5)
        self.assertAlmostEqual(summary[self.bed][1], 1.5 * 10000 / 36, delta=0.01)
        self.assertAlmostEqual(summary[self.bed2][0], 0.2)
        self.assertAlmostEqual(summary[self.bed2][1], 0.2 * 10000 / 10, delta=0.01)
        # filtre de période
        wizard = self._wizard(register='fertilization', date_from='2027-05-01')
        self.assertEqual(len(wizard.fertilization_line_ids), 1)
        # les opérations non faites ne comptent pas
        self._operation(
            type_id=self.type_fertilization.id, crop_ids=[(6, 0, self.crop.ids)], date='2027-06-01',
            input_ids=[(0, 0, {'product_id': self.nitro.id, 'quantity': 50})],
        )
        self.assertEqual(len(self._wizard(register='fertilization').fertilization_line_ids), 3)

    def test_partial_area_and_split(self):
        other = self._crop(planned_sowing_date='2027-03-01', bed_id=self.bed2.id)
        operation = self._operation(
            type_id=self.type_fertilization.id, scope='bed', bed_ids=[(6, 0, (self.bed | self.bed2).ids)],
            date='2027-04-10', input_ids=[(0, 0, {'product_id': self.nitro.id, 'quantity': 4.6})],
        )
        operation.action_done()
        lines = self._wizard(register='fertilization').fertilization_line_ids
        self.assertAlmostEqual(sum(lines.mapped('nitrogen_kg')), 0.46)
        # même dose à l'hectare sur les deux planches
        self.assertAlmostEqual(lines[0].nitrogen_per_ha, lines[1].nitrogen_per_ha, delta=0.01)
        self.assertAlmostEqual(lines[0].nitrogen_per_ha, 0.46 * 10000 / 46, delta=0.01)

    def test_exports_and_pivot(self):
        import openpyxl
        self._fertilize('2027-04-10', 10.0)
        wizard = self._wizard(register='fertilization')
        _filename, content = wizard._get_xlsx()
        workbook = openpyxl.load_workbook(io.BytesIO(content))
        self.assertEqual(len(workbook.worksheets), 2)
        detail, summary = (list(ws.iter_rows(values_only=True)) for ws in workbook.worksheets)
        values = dict(zip(detail[0], detail[1]))
        self.assertAlmostEqual(values['Azote apporté (kg N)'], 1.0)
        self.assertAlmostEqual(values['Azote (kg N/ha)'], 10000 / 36, delta=0.01)
        self.assertEqual(values['Planche'], self.bed.name)
        self.assertEqual(summary[1][1], self.bed.name)
        self.assertAlmostEqual(summary[1][2], 1.0)
        html, _type = self.env['ir.actions.report']._render_qweb_html('odoo_garden.report_garden_compliance', wizard.ids)
        text = html.decode()
        self.assertIn('Registre de fertilisation', text)
        self.assertIn('o_garden_register_fertilization_summary', text)
        self.assertIn(self.nitro.display_name, text)
        action = wizard.action_open_pivot()
        lines = self.env['garden.compliance.line'].search(action['domain'])
        self.assertEqual(lines, wizard.fertilization_line_ids)
        self.assertEqual(action['view_mode'], 'pivot,list')

    def test_rights(self):
        with self.assertRaises(AccessError):
            self.env['garden.compliance.wizard'].with_user(self.worker).create({'register': 'fertilization'})


@tagged('post_install', '-at_install')
class TestGardenOrganicExport(GardenRegisterCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.supplier = cls.env['res.partner'].create({'name': 'Graineterie test'})
        cls.type_sowing = cls.env.ref('odoo_garden.operation_type_sowing')

    def setUp(self):
        super().setUp()
        self.variety.write({'organic_status': 'organic', 'supplier_id': self.supplier.id})
        self.seed_lot2 = self.env['stock.lot'].create({'name': 'LOT-BIO-7', 'product_id': self.seed.id})
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.warehouse.in_type_id.id, 'partner_id': self.supplier.id,
            'location_id': self.env.ref('stock.stock_location_suppliers').id,
            'location_dest_id': self.stock_location.id,
            'move_ids': [(0, 0, {
                'product_id': self.seed.id, 'product_uom_qty': 5, 'product_uom': self.seed.uom_id.id,
                'location_id': self.env.ref('stock.stock_location_suppliers').id,
                'location_dest_id': self.stock_location.id,
            })],
        })
        picking.action_confirm()
        picking.move_ids.move_line_ids.write({'lot_id': self.seed_lot2.id, 'quantity': 5})
        picking.move_ids.picked = True
        picking._action_done()
        self.sowing = self._operation(
            type_id=self.type_sowing.id, crop_ids=[(6, 0, self.crop.ids)], date='2027-03-02',
            input_ids=[(0, 0, {'product_id': self.seed.id, 'quantity': 2, 'lot_id': self.seed_lot2.id})],
        )
        self.sowing.action_done()

    def _tabs(self, wizard):
        import openpyxl
        _filename, content = wizard._get_xlsx()
        workbook = openpyxl.load_workbook(io.BytesIO(content))
        return {ws.title: list(ws.iter_rows(values_only=True)) for ws in workbook.worksheets}

    def test_unauthorized_inputs_are_flagged(self):
        no_organic = self._storable(
            'Phyto de synthèse', garden_input_type='phytosanitary', is_organic_allowed=False,
        )
        self._set_stock(no_organic, 10)
        organic_ok = self._storable('Purin bio', garden_input_type='amendment', is_organic_allowed=True)
        self._set_stock(organic_ok, 10)
        self._treatment('2027-05-01', product=no_organic)
        self._treatment('2027-05-02', product=organic_ok)
        conventional = self.env['garden.variety'].create({'name': 'Conventionnelle', 'species_id': self.solanaceae.id})
        template = self.env['garden.crop.template'].create({'name': 'Tomate conv', 'variety_id': conventional.id})
        other = self._crop(template_id=template.id, bed_id=self.bed2.id, planned_sowing_date='2027-03-01')
        self._treatment('2027-05-03', crop=other, product=no_organic)
        wizard = self._wizard(register='organic')
        lines = wizard.organic_line_ids
        flagged = lines.filtered('alert')
        self.assertEqual(len(flagged), 1)
        self.assertEqual(flagged.product_id, no_organic)
        self.assertEqual(flagged.crop_id, self.crop)
        self.assertEqual(wizard.alert_count, 1)
        self.assertTrue(flagged.organic_crop)
        self.assertEqual(flagged.organic_allowed, 'no')
        # produit autorisé, ou culture non bio : pas d'alerte
        self.assertFalse(lines.filtered(lambda l: l.product_id == organic_ok).alert)
        self.assertFalse(lines.filtered(lambda l: l.crop_id == other).alert)
        # les semences sont « sans objet » (statut de la variété)
        seed_line = lines.filtered(lambda l: l.product_id == self.seed)
        self.assertEqual(seed_line.organic_allowed, 'na')
        self.assertEqual(seed_line.lot_id, self.seed_lot2)

    def test_xlsx_one_sheet_per_theme(self):
        no_organic = self._storable('Phyto de synthèse', garden_input_type='phytosanitary')
        self._set_stock(no_organic, 10)
        self._treatment('2027-05-01', product=no_organic)
        tabs = self._tabs(self._wizard(register='organic'))
        self.assertEqual(list(tabs), ['Semences', 'Intrants', 'Alertes bio'])
        header, seed_row = tabs['Semences']
        values = dict(zip(header, seed_row))
        self.assertEqual(values['Culture'], self.crop.name)
        self.assertEqual(values['Variété'], self.variety.name)
        self.assertEqual(values['Statut bio de la variété'], 'Bio')
        self.assertEqual(values['Fournisseur de la variété'], 'Graineterie test')
        self.assertIn(self.seed.display_name, values['Semences et plants utilisés'])
        self.assertEqual(values['Lots'], 'LOT-BIO-7')
        self.assertEqual(values['Origine des lots (réception)'], 'Graineterie test')
        inputs = tabs['Intrants']
        self.assertEqual(len(inputs), 3)  # en-tête, semence, phytosanitaire
        alerts = tabs['Alertes bio']
        self.assertEqual(len(alerts), 2)
        alert = dict(zip(alerts[0], alerts[1]))
        self.assertEqual(alert['Produit'], no_organic.display_name)
        self.assertEqual(alert['Autorisé en bio'], 'Non')
        self.assertEqual(alert['Non autorisé en bio'], 'Oui')

    def test_period_filter_and_no_pdf(self):
        wizard = self._wizard(register='organic', date_to='2027-03-01')
        self.assertFalse(wizard.organic_line_ids)
        wizard = self._wizard(register='organic', date_from='2027-03-01')
        self.assertEqual(len(wizard.organic_line_ids), 1)
        with self.assertRaises(UserError):
            wizard.action_print()
        with self.assertRaises(AccessError):
            self.env['garden.compliance.wizard'].with_user(self.worker).create({'register': 'organic'})


@tagged('post_install', '-at_install')
class TestGardenComplianceSetting(GardenRegisterCase):

    def _set_enabled(self, enabled):
        self.env['res.config.settings'].create({'garden_compliance_enabled': enabled}).execute()

    def test_enabled_by_default_for_chef_and_manager_only(self):
        self.assertTrue(self.env['garden.compliance.wizard']._is_compliance_enabled())
        for user in (self.chef, self.manager):
            self.assertTrue(user.has_group('odoo_garden.group_garden_compliance'))
        self.assertFalse(self.worker.has_group('odoo_garden.group_garden_compliance'))
        menu = self.env.ref('odoo_garden.menu_garden_compliance')
        self.assertIn(self.env.ref('odoo_garden.group_garden_compliance'), menu.group_ids)
        visible = self.env['ir.ui.menu'].with_user(self.chef)._visible_menu_ids()
        self.assertIn(menu.id, visible)
        self.assertIn(self.env.ref('odoo_garden.menu_garden_compliance_phyto').id, visible)
        visible_worker = self.env['ir.ui.menu'].with_user(self.worker)._visible_menu_ids()
        for xmlid in ('menu_garden_compliance', 'menu_garden_compliance_phyto',
                      'menu_garden_compliance_fertilization', 'menu_garden_compliance_organic'):
            self.assertNotIn(self.env.ref('odoo_garden.' + xmlid).id, visible_worker)

    def test_disabling_hides_menus_and_blocks_exports(self):
        self._treatment('2027-06-10')
        wizard = self._wizard()
        self._set_enabled(False)
        self.assertFalse(self.env['garden.compliance.wizard']._is_compliance_enabled())
        for user in (self.chef, self.manager):
            self.assertFalse(user.has_group('odoo_garden.group_garden_compliance'))
            self.assertTrue(user.has_group('odoo_garden.group_garden_chef'))
        visible = self.env['ir.ui.menu'].with_user(self.chef)._visible_menu_ids()
        self.assertNotIn(self.env.ref('odoo_garden.menu_garden_compliance').id, visible)
        self.assertIn(self.env.ref('odoo_garden.menu_garden_today').id, visible)
        with self.assertRaises(UserError):
            wizard.with_user(self.chef).action_print()
        with self.assertRaises(UserError):
            wizard.with_user(self.chef)._get_xlsx()
        # le contrôle DAR reste actif
        harvest = self._harvest('2027-06-12')
        with self.assertRaises(Exception):
            harvest.action_done()
        # réactivation
        self._set_enabled(True)
        self.assertTrue(self.chef.has_group('odoo_garden.group_garden_compliance'))
        self.assertTrue(wizard.with_user(self.chef)._get_xlsx())

    def test_init_does_not_reactivate(self):
        self._set_enabled(False)
        self.env['res.config.settings']._garden_init_compliance()
        self.assertFalse(self.env['garden.compliance.wizard']._is_compliance_enabled())
        self.assertFalse(self.chef.has_group('odoo_garden.group_garden_compliance'))
