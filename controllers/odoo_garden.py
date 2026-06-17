from odoo import http
from odoo.http import request


class GardenRedirectController(http.Controller):
    @http.route('/odoo/garden', type='http', auth='public')
    def garden_redirect(self, **kw):
        if request.env.user._is_public():
            return request.redirect('/web/login?redirect=/odoo/garden')

        action = None
        try:
            action = request.env.ref('garden.action_garden_farm', raise_if_not_found=False)
        except Exception:
            action = None

        if not action:
            return request.not_found()

        return request.redirect(f'/web#action={action.id}')
