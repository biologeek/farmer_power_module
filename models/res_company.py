from odoo import api, fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    garden_production_location_id = fields.Many2one(
        'stock.location', string='Emplacement « Production maraîchage »', check_company=True,
        domain="[('usage', '=', 'production')]", ondelete='restrict', copy=False,
        help="Emplacement virtuel d'où sortent les récoltes (entrée en stock des produits récoltés).",
    )
    garden_consumption_location_id = fields.Many2one(
        'stock.location', string='Emplacement « Consommation maraîchage »', check_company=True,
        domain="[('usage', '=', 'production')]", ondelete='restrict', copy=False,
        help="Emplacement virtuel où partent les intrants consommés par les opérations (semences, engrais...).",
    )
    garden_stock_location_id = fields.Many2one(
        'stock.location', string='Emplacement de stockage maraîchage', check_company=True,
        domain="[('usage', '=', 'internal')]", ondelete='restrict', copy=False,
        help="Emplacement où entrent les récoltes et d'où sortent les intrants. "
             "Vide : stock principal du premier entrepôt de la société.",
    )

    def _get_garden_stock_location(self):
        """Emplacement de stockage maraîchage de la société (à défaut, stock de son premier entrepôt)."""
        self.ensure_one()
        return self.garden_stock_location_id or self.env['stock.warehouse'].sudo().search(
            [('company_id', '=', self.id)], limit=1,
        ).lot_stock_id

    def _create_garden_locations(self):
        """Renseigne les emplacements virtuels de production et de consommation manquants.

        La société principale reprend les emplacements déclarés en données XML ; les autres sociétés
        (existantes ou nouvelles) reçoivent les leurs, créés ici. Une écriture XML sur ``base.main_company``
        n'est pas possible : l'enregistrement est ``noupdate`` dans ``base`` et serait ignoré à la mise à jour.
        """
        Location = self.env['stock.location'].sudo()
        main_company = self.env.ref('base.main_company', raise_if_not_found=False)
        for company in self.sudo():
            vals = {}
            for field, xmlid, name in (
                ('garden_production_location_id', 'odoo_garden.stock_location_garden_production', 'Production maraîchage'),
                ('garden_consumption_location_id', 'odoo_garden.stock_location_garden_consumption', 'Consommation maraîchage'),
            ):
                if company[field]:
                    continue
                location = self.env.ref(xmlid, raise_if_not_found=False) if company == main_company else False
                vals[field] = (location or Location.create({
                    'name': name, 'usage': 'production', 'company_id': company.id,
                })).id
            if vals:
                company.write(vals)

    @api.model
    def create_missing_garden_locations(self):
        """Appelé à l'installation : complète les sociétés qui n'ont pas encore ces emplacements."""
        self.search([])._create_garden_locations()

    @api.model_create_multi
    def create(self, vals_list):
        companies = super().create(vals_list)
        companies._create_garden_locations()
        return companies
