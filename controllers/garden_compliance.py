from odoo import http
from odoo.http import content_disposition, request


class GardenComplianceController(http.Controller):

    @http.route('/odoo_garden/compliance/xlsx/<int:wizard_id>', type='http', auth='user', readonly=False)
    def compliance_xlsx(self, wizard_id, **kw):
        """Télécharge le registre réglementaire de l'écran ``wizard_id`` au format XLSX.

        L'accès suit les droits du modèle (chef de culture et gérant) ; l'écran est un modèle
        transitoire, que seul son créateur peut relire.
        """
        wizard = request.env['garden.compliance.wizard'].browse(wizard_id).exists()
        if not wizard:
            return request.not_found()
        filename, content = wizard._get_xlsx()
        return request.make_response(content, [
            ('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
            ('Content-Disposition', content_disposition(filename)),
        ])
