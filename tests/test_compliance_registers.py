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
