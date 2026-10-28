import io
from datetime import date

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

REGISTER_SELECTION = [
    ('phyto', 'Registre phytosanitaire'),
    ('fertilization', 'Registre de fertilisation'),
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
    nitrogen_content = fields.Float('Teneur en azote (%)', digits=(5, 2))
    quantity_kg = fields.Float('Quantité (kg)', digits=(16, 3), help="Quantité d'engrais convertie en kilogrammes.")
    nitrogen_kg = fields.Float(
        'Azote apporté (kg N)', digits=(16, 3), help="Quantité d'engrais (kg) × teneur en azote / 100.",
    )
    nitrogen_per_ha = fields.Float(
        'Azote (kg N/ha)', digits=(16, 2), help="Azote apporté ramené à l'hectare de surface fertilisée.",
    )
    note = fields.Char('Remarque')


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
    fertilization_line_ids = fields.One2many(
        'garden.compliance.line', 'wizard_id', string='Fertilisations', domain=[('register', '=', 'fertilization')],
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

    def _get_fertilization_line_vals(self):
        """Azote apporté par chaque engrais (intrants de type engrais d'opérations faites).

        ``nitrogen_kg`` = quantité d'engrais en kg × teneur en azote (%) / 100 ; ``nitrogen_per_ha`` =
        ``nitrogen_kg`` × 10 000 / surface fertilisée (kg N/ha, ce que la réglementation appelle des
        « unités d'azote »). Un engrais dont l'unité n'est pas une masse ou sans teneur en azote est
        listé avec 0 et une remarque.
        """
        kilogram = self.env.ref('uom.product_uom_kgm')
        vals_list = []
        for line, crop, share in self._get_input_rows(['fertilizer']):
            product = line.product_id
            vals = dict(
                self._base_line_vals(line, crop, share),
                register='fertilization',
                treated_area=line.treated_area * share,
                nitrogen_content=product.nitrogen_content,
            )
            if not line.uom_id._has_common_reference(kilogram):
                vals['note'] = self.env._("Unité non convertible en kg : azote non calculé.")
            else:
                vals['quantity_kg'] = line.uom_id._compute_quantity(vals['quantity'], kilogram, round=False)
                if not product.nitrogen_content:
                    vals['note'] = self.env._("Teneur en azote non renseignée sur le produit.")
                vals['nitrogen_kg'] = vals['quantity_kg'] * product.nitrogen_content / 100.0
                if vals['treated_area'] > 0:
                    vals['nitrogen_per_ha'] = vals['nitrogen_kg'] * 10000.0 / vals['treated_area']
            vals_list.append(vals)
        return vals_list

    def _get_fertilization_summary(self):
        """Synthèse par saison et par planche : ``[(saison, planche, kg N, kg N/ha)]``.

        Les kg N/ha des applications d'une même planche et d'une même saison s'additionnent (chaque
        application est ramenée à l'hectare de la surface fertilisée).
        """
        self.ensure_one()
        groups = self.env['garden.compliance.line']._read_group(
            [('wizard_id', '=', self.id), ('register', '=', 'fertilization')],
            ['season_id', 'bed_id'], ['nitrogen_kg:sum', 'nitrogen_per_ha:sum'],
            order='season_id, bed_id',
        )
        return groups

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

    def action_open_pivot(self):
        """Bouton « Synthèse » : pivot de l'azote par planche et par saison."""
        self.ensure_one()
        self._compute_lines()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._("Azote par planche et par saison"),
            'res_model': 'garden.compliance.line',
            'view_mode': 'pivot,list',
            'views': [
                (self.env.ref('odoo_garden.view_garden_compliance_line_fertilization_pivot').id, 'pivot'),
                (self.env.ref('odoo_garden.view_garden_compliance_line_fertilization_list').id, 'list'),
            ],
            'domain': [('wizard_id', '=', self.id), ('register', '=', 'fertilization')],
            'search_view_id': [self.env.ref('odoo_garden.view_garden_compliance_line_search').id, 'search'],
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
            'fertilization': [
                ('Date', 'date', 12), ('Saison', 'season_id', 14), ('Planche', 'bed_id', 16),
                ('Culture', 'crop_id', 18), ('Surface fertilisée (m²)', 'treated_area', 12),
                ('Engrais', 'product_id', 26), ('Quantité', 'quantity', 12), ('Unité', 'uom_id', 8),
                ('Quantité (kg)', 'quantity_kg', 12), ('Teneur en azote (%)', 'nitrogen_content', 12),
                ('Azote apporté (kg N)', 'nitrogen_kg', 14), ('Azote (kg N/ha)', 'nitrogen_per_ha', 12),
                ('Remarque', 'note', 30),
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
        for title, headers, rows in self._xlsx_tabs():
            sheet = workbook.add_worksheet(title[:31])
            sheet.freeze_panes(1, 0)
            for col, (header, width) in enumerate(headers):
                sheet.write(0, col, header, bold)
                sheet.set_column(col, col, width)
            for row, cells in enumerate(rows, start=1):
                for col, value in enumerate(cells):
                    if isinstance(value, bool):
                        sheet.write(row, col, self.env._("Oui") if value else self.env._("Non"))
                    elif isinstance(value, (int, float)):
                        sheet.write_number(row, col, value, number_format)
                    elif isinstance(value, date):
                        sheet.write_datetime(row, col, value, date_format)
                    else:
                        sheet.write(row, col, value or '')
        workbook.close()
        label = dict(self._fields['register'].selection)[self.register]
        return "%s.xlsx" % label.replace(' ', '_'), output.getvalue()

    @api.model
    def _cell_value(self, line, field_name):
        """Valeur d'une cellule du classeur : texte, nombre ou date (les enregistrements deviennent leur nom)."""
        value = line[field_name]
        field = line._fields[field_name]
        if field.type == 'many2one':
            return (value.name if value._name == 'garden.crop' else value.display_name) or ''
        if field.type == 'date':
            return value or ''
        if field.type == 'boolean':
            return bool(value)
        return value or (0.0 if field.type == 'float' else '')

    def _xlsx_tabs(self):
        """Onglets du classeur : ``[(titre, [(en-tête, largeur)], [ligne de cellules])]``."""
        self.ensure_one()
        columns = self._xlsx_sheets()[self.register]
        title = dict(self._fields['register'].selection)[self.register]
        tabs = [(
            title, [(header, width) for header, _field, width in columns],
            [[self._cell_value(line, field) for _header, field, _width in columns] for line in self.line_ids],
        )]
        if self.register == 'fertilization':
            tabs.append((
                self.env._("Synthèse par planche"),
                [(self.env._("Saison"), 14), (self.env._("Planche"), 16), (self.env._("Azote apporté (kg N)"), 16),
                 (self.env._("Azote cumulé (kg N/ha)"), 16)],
                [[season.name or '', bed.name or '', kg, per_ha]
                 for season, bed, kg, per_ha in self._get_fertilization_summary()],
            ))
        return tabs
