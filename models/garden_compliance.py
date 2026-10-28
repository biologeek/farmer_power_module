import io

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

REGISTER_SELECTION = [
    ('phyto', 'Registre phytosanitaire'),
]


class GardenComplianceLine(models.TransientModel):
    _name = 'garden.compliance.line'
    _description = "Ligne d'un registre réglementaire"
    _order = 'date, id'
    # Ligne calculée (ORM, aucune vue SQL) par ``garden.compliance.wizard`` à partir des intrants des
    # opérations « faites ». Une ligne par intrant et par culture concernée : un traitement réparti sur
    # plusieurs cultures donne une ligne par culture, avec la quantité et la surface au prorata de la
    # répartition de l'opération. Modèle transitoire : les lignes ne sont conservées que le temps de
    # la consultation et des exports ; le registre se recalcule à chaque demande.

    wizard_id = fields.Many2one('garden.compliance.wizard', string='Registre', required=True, ondelete='cascade')
    register = fields.Selection(REGISTER_SELECTION, string='Registre de la ligne', required=True)
    operation_id = fields.Many2one('garden.operation', string='Opération', ondelete='cascade')
    date = fields.Date('Date')
    season_id = fields.Many2one('garden.season', string='Saison', ondelete='cascade')
    crop_id = fields.Many2one('garden.crop', string='Culture', ondelete='cascade')
    bed_id = fields.Many2one('garden.bed', string='Planche', ondelete='cascade')
    parcel = fields.Char('Parcelle', help="Site, îlot et planche traités.")
    product_id = fields.Many2one('product.product', string='Produit', ondelete='cascade')
    amm_number = fields.Char('N° AMM')
    quantity = fields.Float('Quantité utilisée', digits='Product Unit')
    uom_id = fields.Many2one('uom.uom', string='Unité', ondelete='cascade')
    treated_area = fields.Float('Surface traitée (m²)', digits=(16, 2))
    dose = fields.Float('Dose (par ha)', digits=(16, 3))
    operator = fields.Char('Opérateur')
    target = fields.Char('Cible')
    weather_notes = fields.Text('Conditions')


class GardenComplianceWizard(models.TransientModel):
    _name = 'garden.compliance.wizard'
    _description = 'Registre réglementaire (France)'
    # Écran commun aux registres réglementaires français : filtres (période, saison, cultures), liste
    # calculée, impression PDF et export XLSX. Réservé au chef de culture et au gérant (droits d'accès).
    # Les données sont lues en ``sudo()`` (opérations faites, répartitions, produits, employés) mais
    # limitées aux sociétés autorisées de l'utilisateur.

    register = fields.Selection(
        REGISTER_SELECTION, string='Registre', required=True,
        default=lambda self: self.env.context.get('default_register') or 'phyto',
    )
    date_from = fields.Date('Du', help="Premier jour de la période (date de réalisation des opérations).")
    date_to = fields.Date('Au', help="Dernier jour de la période (inclus).")
    season_id = fields.Many2one('garden.season', string='Saison', help="Limite le registre aux cultures de la saison.")
    crop_ids = fields.Many2many(
        'garden.crop', 'garden_compliance_wizard_crop_rel', 'wizard_id', 'crop_id', string='Cultures',
        help="Limite le registre à ces cultures (vide : toutes).",
    )
    line_ids = fields.One2many('garden.compliance.line', 'wizard_id', string='Lignes')
    phyto_line_ids = fields.One2many(
        'garden.compliance.line', 'wizard_id', string='Traitements', domain=[('register', '=', 'phyto')],
    )
    line_count = fields.Integer('Nombre de lignes', compute='_compute_line_count')

    @api.depends('line_ids')
    def _compute_line_count(self):
        for wizard in self:
            wizard.line_count = len(wizard.line_ids)

    # ------------------------------------------------------------------
    # Lecture des données
    # ------------------------------------------------------------------
    def _get_input_domain(self, input_types):
        self.ensure_one()
        domain = [
            ('operation_id.state', '=', 'done'),
            ('garden_input_type', 'in', input_types),
            ('company_id', 'in', self.env.companies.ids),
        ]
        if self.date_from:
            domain.append(('operation_id.date', '>=', self.date_from))
        if self.date_to:
            domain.append(('operation_id.date', '<=', self.date_to))
        return domain

    def _get_input_rows(self, input_types):
        """Intrants faits à reporter : ``[(ligne d'intrant, culture, part)]``, triés par date.

        La part est celle de la culture dans la répartition de l'opération (1 pour une opération sans
        répartition, qui n'apparaît alors que si aucun filtre de culture ou de saison n'est posé).
        """
        self.ensure_one()
        inputs = self.env['garden.operation.input'].sudo().search(
            self._get_input_domain(input_types), order='id',
        ).sorted(lambda l: (l.operation_id.date or l.operation_id.planned_date or fields.Date.today(), l.id))
        filtered = bool(self.crop_ids or self.season_id)
        rows = []
        for line in inputs:
            allocations = line.operation_id.allocation_ids
            if self.crop_ids:
                allocations = allocations.filtered(lambda a: a.crop_id in self.crop_ids)
            if self.season_id:
                allocations = allocations.filtered(lambda a: a.crop_id.season_id == self.season_id)
            if line.operation_id.allocation_ids:
                rows.extend((line, a.crop_id, a.share / 100.0) for a in allocations)
            elif not filtered:
                rows.append((line, self.env['garden.crop'], 1.0))
        return rows

    @api.model
    def _get_operators(self, operation):
        employees = operation.employee_ids | operation.worker_ids.employee_id
        return ", ".join(employees.mapped('name'))

    @api.model
    def _get_parcel(self, operation, crop):
        """Libellé « Site / Îlot / Planche » : planche de la culture, sinon cible de l'opération."""
        beds = crop.bed_id or operation.bed_ids
        if beds:
            return ", ".join("%s / %s / %s" % (b.site_id.name, b.garden_id.name, b.name) for b in beds)
        garden = operation.garden_main_id
        return "%s / %s" % (garden.site_id.name, garden.name) if garden else ""

    def _base_line_vals(self, line, crop, share):
        operation = line.operation_id
        return {
            'wizard_id': self.id,
            'operation_id': operation.id,
            'date': operation.date or operation.planned_date,
            'season_id': crop.season_id.id,
            'crop_id': crop.id,
            'bed_id': (crop.bed_id or operation.bed_ids[:1]).id,
            'parcel': self._get_parcel(operation, crop),
            'product_id': line.product_id.id,
            'quantity': line.quantity * share,
            'uom_id': line.uom_id.id,
        }

    def _get_phyto_line_vals(self):
        vals_list = []
        for line, crop, share in self._get_input_rows(['phytosanitary']):
            operation = line.operation_id
            vals_list.append(dict(
                self._base_line_vals(line, crop, share),
                register='phyto',
                amm_number=line.product_id.amm_number or False,
                treated_area=line.treated_area * share,
                dose=line.dose,
                operator=self._get_operators(operation),
                target=operation.target or False,
                weather_notes=operation.weather_notes or False,
            ))
        return vals_list

    # ------------------------------------------------------------------
    # Calcul, impression, export
    # ------------------------------------------------------------------
    def _check_access_chef(self):
        if not self.env.user.has_group('odoo_garden.group_garden_chef'):
            raise AccessError(self.env._("Les registres réglementaires sont réservés au chef de culture et au gérant."))

    def _compute_lines(self):
        """Recalcule les lignes du registre (supprime les précédentes)."""
        self._check_access_chef()
        for wizard in self:
            wizard.line_ids.unlink()
            getter = getattr(wizard, '_get_%s_line_vals' % wizard.register)
            self.env['garden.compliance.line'].create(getter())
        return True

    def action_compute(self):
        """Bouton « Calculer » : recalcule les lignes puis rouvre l'écran."""
        self.ensure_one()
        self._compute_lines()
        return self._reopen()

    def _reopen(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': dict(self._fields['register'].selection)[self.register],
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
            'context': dict(self.env.context, default_register=self.register),
        }

    def action_print(self):
        """Bouton « Imprimer » : registre au format PDF."""
        self.ensure_one()
        self._compute_lines()
        return self.env.ref('odoo_garden.action_report_garden_compliance').report_action(self)

    def action_export_xlsx(self):
        """Bouton « Exporter » : téléchargement du fichier XLSX (contrôleur ``/odoo_garden/compliance/xlsx``)."""
        self.ensure_one()
        self._check_access_chef()
        return {
            'type': 'ir.actions.act_url',
            'url': '/odoo_garden/compliance/xlsx/%d' % self.id,
            'target': 'self',
        }

    @api.model
    def _xlsx_sheets(self):
        """Colonnes de chaque registre : ``{registre: [(titre, champ de la ligne, largeur)]}``."""
        return {
            'phyto': [
                ('Date', 'date', 12), ('Culture', 'crop_id', 18), ('Saison', 'season_id', 14),
                ('Parcelle', 'parcel', 30), ('Surface traitée (m²)', 'treated_area', 12),
                ('Produit', 'product_id', 26), ('N° AMM', 'amm_number', 14), ('Dose (par ha)', 'dose', 12),
                ('Quantité utilisée', 'quantity', 12), ('Unité', 'uom_id', 8), ('Opérateur', 'operator', 20),
                ('Cible', 'target', 18), ('Conditions', 'weather_notes', 28),
            ],
        }

    def _get_xlsx(self):
        """Contenu du classeur XLSX du registre (recalculé) : ``(nom de fichier, octets)``."""
        self.ensure_one()
        self._compute_lines()
        try:
            import xlsxwriter  # noqa: PLC0415
        except ImportError:
            raise UserError(self.env._("La bibliothèque xlsxwriter est nécessaire à l'export XLSX."))
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        bold = workbook.add_format({'bold': True, 'bg_color': '#D9E8D0', 'border': 1, 'text_wrap': True})
        date_format = workbook.add_format({'num_format': 'dd/mm/yyyy'})
        number_format = workbook.add_format({'num_format': '#,##0.00'})
        for title, columns, lines in self._xlsx_tabs():
            sheet = workbook.add_worksheet(title[:31])
            sheet.freeze_panes(1, 0)
            for col, (header, _field, width) in enumerate(columns):
                sheet.write(0, col, header, bold)
                sheet.set_column(col, col, width)
            for row, line in enumerate(lines, start=1):
                for col, (_header, field_name, _width) in enumerate(columns):
                    value = line[field_name]
                    field = line._fields[field_name]
                    if field.type == 'many2one':
                        sheet.write(row, col, (value.name if value._name == 'garden.crop' else value.display_name) or '')
                    elif field.type == 'date':
                        if value:
                            sheet.write_datetime(row, col, fields.Date.to_date(value), date_format)
                    elif field.type == 'float':
                        sheet.write_number(row, col, value, number_format)
                    elif field.type == 'boolean':
                        sheet.write(row, col, self.env._("Oui") if value else self.env._("Non"))
                    else:
                        sheet.write(row, col, value or '')
        workbook.close()
        label = dict(self._fields['register'].selection)[self.register]
        return "%s.xlsx" % label.replace(' ', '_'), output.getvalue()

    def _xlsx_tabs(self):
        """Onglets du classeur : ``[(titre, colonnes, lignes)]``."""
        self.ensure_one()
        columns = self._xlsx_sheets()[self.register]
        return [(dict(self._fields['register'].selection)[self.register], columns, self.line_ids)]
