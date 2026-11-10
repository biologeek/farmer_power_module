from urllib.parse import parse_qs, unquote, urlparse

from odoo.addons.web.controllers.utils import get_action_triples
from odoo.tests import HttpCase, tagged

from .test_operations import GardenOperationCase


def _png_backend_missing():
    """Vrai si reportlab ne peut pas produire de PNG (ni rlPyCairo ni _rl_renderPM installés)."""
    try:
        from reportlab.graphics import renderPM
        renderPM._getPMBackend()
    except Exception:  # noqa: BLE001 - dépend de l'environnement
        return True
    return False


@tagged('post_install', '-at_install')
class TestGardenBedLabels(GardenOperationCase):

    def test_qr_url_opens_the_bed(self):
        url = self.bed._get_qr_url()
        self.assertTrue(url.startswith(self.bed.get_base_url()))
        self.assertTrue(url.endswith('/odoo/action-farmer_power.action_garden_bed/%d' % self.bed.id))
        # la route /odoo/action-<xmlid>/<id> se résout en l'action des planches et l'enregistrement
        path = urlparse(url).path
        [(active_id, action, record_id)] = list(get_action_triples(self.env, path.removeprefix('/odoo')))
        self.assertEqual(action, self.env.ref('farmer_power.action_garden_bed'))
        self.assertEqual(record_id, self.bed.id)

    def test_qr_image_source(self):
        src = self.bed._get_qr_image_src(200)
        self.assertTrue(src.startswith('/report/barcode/?'))
        query = parse_qs(urlparse(src).query)
        self.assertEqual(query['barcode_type'], ['QR'])
        self.assertEqual(unquote(query['value'][0]), self.bed._get_qr_url())
        if _png_backend_missing():
            self.skipTest("reportlab n'a pas de moteur PNG (rlPyCairo / _rl_renderPM) dans cet environnement.")
        # l'image est bien générée par le moteur de codes-barres d'Odoo
        png = self.env['ir.actions.report'].barcode('QR', self.bed._get_qr_url(), width=200, height=200)
        self.assertTrue(png.startswith(b'\x89PNG'))

    def test_label_report_renders(self):
        beds = self.bed | self.bed2
        report = self.env.ref('farmer_power.action_report_garden_bed_label')
        self.assertEqual(report.report_type, 'qweb-pdf')
        self.assertEqual(report.model, 'garden.bed')
        html, report_type = self.env['ir.actions.report']._render_qweb_html(report.report_name, beds.ids)
        self.assertEqual(report_type, 'html')
        text = html.decode()
        self.assertEqual(text.count('o_garden_bed_label'), 2)
        for bed in beds:
            self.assertIn(bed.name, text)
            self.assertIn(bed.code, text)
            self.assertIn('%d' % bed.id, text)
        self.assertIn('/report/barcode/', text)
        self.assertEqual(text.count('barcode_type=QR'), 2)

    def test_bed_new_operation_button(self):
        action = self.bed.action_new_operation()
        self.assertEqual(action['res_model'], 'garden.operation')
        self.assertEqual(action['context']['default_scope'], 'bed')
        self.assertEqual(action['context']['default_bed_ids'], [(6, 0, self.bed.ids)])
        crop = self._crop(planned_sowing_date='2027-03-01')
        by_bed = self._operation(scope='bed', bed_ids=[(6, 0, self.bed.ids)])
        by_crop = self._operation(crop_ids=[(6, 0, crop.ids)])
        by_garden = self._operation(
            type_id=self.type_irrigation.id, scope='garden', garden_id=self.garden.id,
        )
        self.assertEqual(self.bed.operation_count, 3)
        found = self.env['garden.operation'].search(self.bed.action_view_operations()['domain'])
        self.assertEqual(found, by_bed | by_crop | by_garden)


@tagged('post_install', '-at_install')
class TestGardenBedLabelsHttp(HttpCase):

    def test_barcode_route_and_bed_url(self):
        farm = self.env['garden.farm'].create({'name': 'Ferme QR'})
        site = self.env['garden.site'].create({'name': 'Site QR', 'farm_id': farm.id})
        garden = self.env['garden.garden'].create({'name': 'Îlot QR', 'site_id': site.id})
        bed = self.env['garden.bed'].create({'name': 'Planche QR', 'code': 'QR1', 'garden_id': garden.id})
        self.authenticate('admin', 'admin')
        if not _png_backend_missing():
            response = self.url_open(bed._get_qr_image_src(120))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers['Content-Type'], 'image/png')
            self.assertTrue(response.content.startswith(b'\x89PNG'))
        # l'adresse du QR code ouvre le client web
        path = '/odoo/action-farmer_power.action_garden_bed/%d' % bed.id
        response = self.url_open(path)
        self.assertEqual(response.status_code, 200)
