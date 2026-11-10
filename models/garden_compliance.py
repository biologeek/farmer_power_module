import io
from collections import defaultdict
from datetime import date

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

REGISTER_SELECTION = [
    ('phyto', 'Plant Protection Register'),
    ('fertilization', 'Fertilization Register'),
    ('organic', 'Organic Certification Export'),
]
INPUT_TYPES = ['seed', 'plant', 'fertilizer', 'amendment', 'phytosanitary', 'substrate', 'other']
ORGANIC_CONTROLLED_TYPES = ('fertilizer', 'amendment', 'phytosanitary', 'substrate')


class GardenComplianceLine(models.TransientModel):
    _name = 'garden.compliance.line'
    _description = 'Regulatory Register Line'
    _order = 'date, id'
    # Ligne calculée (ORM, aucune vue SQL) par ``garden.compliance.wizard`` à partir des intrants des
    # opérations « faites ». Une ligne par intrant et par culture concernée : un traitement réparti sur
    # plusieurs cultures donne une ligne par culture, avec la quantité et la surface au prorata de la
    # répartition de l'opération. Modèle transitoire : les lignes ne sont conservées que le temps de
    # la consultation et des exports ; le registre se recalcule à chaque demande.

    wizard_id = fields.Many2one('garden.compliance.wizard', string='Register', required=True, ondelete='cascade')
    register = fields.Selection(REGISTER_SELECTION, string='Register of the line', required=True)
    operation_id = fields.Many2one('garden.operation', string='Operation', ondelete='cascade')
    date = fields.Date('Date')
    season_id = fields.Many2one('garden.season', string='Season', ondelete='cascade')
    crop_id = fields.Many2one('garden.crop', string='Crop', ondelete='cascade')
    bed_id = fields.Many2one('garden.bed', string='Bed', ondelete='cascade')
    parcel = fields.Char('Plot', help='Site, block and bed treated.')
    product_id = fields.Many2one('product.product', string='Product', ondelete='cascade')
    amm_number = fields.Char('MA No.')
    quantity = fields.Float('Quantity Used', digits='Product Unit')
    uom_id = fields.Many2one('uom.uom', string='Unit', ondelete='cascade')
    treated_area = fields.Float('Treated Area (m²)', digits=(16, 2))
    dose = fields.Float('Dose (per ha)', digits=(16, 3))
    operator = fields.Char('Operator')
    target = fields.Char('Target')
    weather_notes = fields.Text('Conditions')
    nitrogen_content = fields.Float('Nitrogen Content (%)', digits=(5, 2))
    quantity_kg = fields.Float('Quantity (kg)', digits=(16, 3), help='Fertilizer quantity converted into kilograms.')
    nitrogen_kg = fields.Float(
        'Nitrogen Applied (kg N)', digits=(16, 3), help='Fertilizer quantity (kg) × nitrogen content / 100.',
    )
    nitrogen_per_ha = fields.Float(
        'Nitrogen (kg N/ha)', digits=(16, 2), help='Nitrogen applied per hectare of fertilized area.',
    )
    note = fields.Char('Remark')
    input_type = fields.Selection(
        related='product_id.garden_input_type', string='Input Type',
    )
    lot_id = fields.Many2one('stock.lot', string='Lot', ondelete='cascade')
    organic_crop = fields.Boolean('Organic Crop', help='The variety of the crop has the "Organic" status.')
    organic_allowed = fields.Selection(
        [('yes', 'Yes'), ('no', 'No'), ('na', 'Not applicable')], string='Allowed in organic',
        help='"Allowed in organic farming" field of the product (fertilizers, amendments, plant protection '
             'products and substrates only).',
    )
    alert = fields.Boolean(
        'Not Allowed in Organic', help='Input not allowed in organic farming used on an organic crop.',
    )


class GardenComplianceWizard(models.TransientModel):
    _name = 'garden.compliance.wizard'
    _description = 'Regulatory Register (France)'
    # Écran commun aux registres réglementaires français : filtres (période, saison, cultures), liste
    # calculée, impression PDF et export XLSX. Réservé au chef de culture et au gérant (droits d'accès).
    # Les données sont lues en ``sudo()`` (opérations faites, répartitions, produits, employés) mais
    # limitées aux sociétés autorisées de l'utilisateur.

    register = fields.Selection(
        REGISTER_SELECTION, string='Register', required=True,
        default=lambda self: self.env.context.get('default_register') or 'phyto',
    )
    date_from = fields.Date('From', help='First day of the period (date the operations were done).')
    date_to = fields.Date('To', help='Last day of the period (included).')
    season_id = fields.Many2one('garden.season', string='Season', help='Limits the register to the crops of the season.')
    crop_ids = fields.Many2many(
        'garden.crop', 'garden_compliance_wizard_crop_rel', 'wizard_id', 'crop_id', string='Crops',
        help='Limits the register to these crops (empty: all).',
    )
    line_ids = fields.One2many('garden.compliance.line', 'wizard_id', string='Lines')
    phyto_line_ids = fields.One2many(
        'garden.compliance.line', 'wizard_id', string='Treatments', domain=[('register', '=', 'phyto')],
    )
    organic_line_ids = fields.One2many(
        'garden.compliance.line', 'wizard_id', string='Inputs', domain=[('register', '=', 'organic')],
    )
    alert_count = fields.Integer(
        'Inputs Not Allowed in Organic', compute='_compute_line_count',
        help='Number of lines of inputs not allowed in organic used on an organic crop.',
    )
    fertilization_line_ids = fields.One2many(
        'garden.compliance.line', 'wizard_id', string='Fertilizations', domain=[('register', '=', 'fertilization')],
    )
    line_count = fields.Integer('Number of Lines', compute='_compute_line_count')

    @api.depends('register')
    def _compute_display_name(self):
        labels = dict(self._fields['register']._description_selection(self.env))
        for wizard in self:
            wizard.display_name = labels.get(wizard.register) or wizard._description

    @api.depends('line_ids', 'line_ids.alert')
    def _compute_line_count(self):
        for wizard in self:
            wizard.line_count = len(wizard.line_ids)
            wizard.alert_count = len(wizard.line_ids.filtered('alert'))

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
                vals['note'] = self.env._('Unit not convertible into kg: nitrogen not computed.')
            else:
                vals['quantity_kg'] = line.uom_id._compute_quantity(vals['quantity'], kilogram, round=False)
                if not product.nitrogen_content:
                    vals['note'] = self.env._('Nitrogen content not set on the product.')
                vals['nitrogen_kg'] = vals['quantity_kg'] * product.nitrogen_content / 100.0
                if vals['treated_area'] > 0:
                    vals['nitrogen_per_ha'] = vals['nitrogen_kg'] * 10000.0 / vals['treated_area']
            vals_list.append(vals)
        return vals_list

    def _get_organic_line_vals(self):
        """Intrants utilisés par culture, avec le statut bio du produit.

        Une culture est « bio » si sa variété a le statut « Bio ». Un engrais, amendement, phytosanitaire
        ou substrat dont ``is_organic_allowed`` n'est pas coché, utilisé sur une culture bio, est signalé
        (``alert``). Les semences et plants relèvent du statut de la variété (onglet « Semences »).
        """
        vals_list = []
        for line, crop, share in self._get_input_rows(INPUT_TYPES):
            product = line.product_id
            controlled = product.garden_input_type in ORGANIC_CONTROLLED_TYPES
            organic_crop = crop.variety_id.organic_status == 'organic'
            allowed = 'na' if not controlled else ('yes' if product.is_organic_allowed else 'no')
            vals_list.append(dict(
                self._base_line_vals(line, crop, share),
                register='organic',
                lot_id=line.lot_id.id,
                organic_crop=organic_crop,
                organic_allowed=allowed,
                alert=organic_crop and allowed == 'no',
                note=self.env._('Not allowed in organic on an organic crop') if organic_crop and allowed == 'no' else False,
            ))
        return vals_list

    def _get_organic_seed_rows(self):
        """Origine et statut des semences, par culture (traçabilité amont de la phase 4).

        Même résultat que ``garden.traceability`` culture par culture (opérations faites, intrants de
        semis, plantation ou repiquage, lots de semence et leur réception), mais calculé en quelques
        recherches groupées pour toutes les cultures : le coût ne dépend plus du nombre de cultures.
        """
        self.ensure_one()
        crops = (self.crop_ids | self.line_ids.crop_id).sudo()
        status_labels = dict(self.env['garden.variety']._fields['organic_status'].selection)
        crop_ids = set(crops.ids)
        SEED_CATEGORIES = ('sowing', 'transplanting', 'planting')
        SEED_TYPES = ('seed', 'plant')
        seed_inputs = self.env['garden.operation.input'].sudo().search([
            ('operation_id.state', '=', 'done'), ('operation_id.category', 'in', SEED_CATEGORIES),
            ('garden_input_type', 'in', SEED_TYPES),
            '|', ('operation_id.crop_ids', 'in', crops.ids), ('operation_id.allocation_ids.crop_id', 'in', crops.ids),
        ])
        # intrants de semence par culture, dans l'ordre des opérations (date, id) puis des lignes
        by_crop = defaultdict(list)
        for line in seed_inputs.sorted(lambda i: (i.operation_id.date or date.min, i.operation_id.id, i.sequence, i.id)):
            operation = line.operation_id
            for crop_id in (set(operation.crop_ids.ids) | set(operation.allocation_ids.crop_id.ids)) & crop_ids:
                by_crop[crop_id].append(line)
        # réceptions fournisseur des lots de semence, groupées par lot
        receipts_by_lot = defaultdict(list)
        seed_lots = seed_inputs.lot_id
        if seed_lots:
            for move_line in self.env['stock.move.line'].sudo().search([
                ('lot_id', 'in', seed_lots.ids), ('state', '=', 'done'), ('location_id.usage', '=', 'supplier'),
            ], order='date, id'):
                receipts_by_lot[move_line.lot_id.id].append(move_line)
        rows = []
        for crop in crops.sorted(lambda c: (c.season_id.name or '', c.name)):
            variety = crop.variety_id
            inputs = by_crop.get(crop.id, [])
            lots = []
            for line in inputs:
                if line.lot_id and line.lot_id not in lots:
                    lots.append(line.lot_id)
            receipts = sorted((r for lot in lots for r in receipts_by_lot.get(lot.id, [])), key=lambda r: (r.date, r.id))
            products = []
            for line in inputs:
                if line.product_id.display_name not in products:
                    products.append(line.product_id.display_name)
            rows.append([
                crop.name, crop.season_id.name or '', crop.bed_id.name or '', crop.species_id.name or '',
                variety.name or '', status_labels.get(variety.organic_status, ''),
                variety.supplier_id.name or '',
                ", ".join(products),
                ", ".join(lot.name for lot in lots),
                ", ".join(sorted({r.picking_id.partner_id.name for r in receipts if r.picking_id.partner_id})),
                receipts[0].date.date() if receipts and receipts[0].date else '',
            ])
        return rows

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
            raise AccessError(self.env._('Regulatory registers are reserved to the crop manager and the manager.'))

    @api.model
    def _is_compliance_enabled(self):
        """Paramètre système ``odoo_garden.compliance_enabled`` (activé par défaut)."""
        value = self.env['ir.config_parameter'].sudo().get_param('odoo_garden.compliance_enabled', 'True')
        return str(value).strip().lower() not in ('false', '0', '')

    def _compute_lines(self):
        """Recalcule les lignes du registre (supprime les précédentes)."""
        self._check_access_chef()
        if not self._is_compliance_enabled():
            raise UserError(self.env._(
                'Regulatory registers (France) are disabled: enable them in Settings > Market Gardening.'
            ))
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
        if self.register == 'organic':
            raise UserError(self.env._('The organic certification export is in XLSX format.'))
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
            'name': self.env._('Nitrogen per Bed and Season'),
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
                (self.env._('Date'), 'date', 12), (self.env._('Crop'), 'crop_id', 18), (self.env._('Season'), 'season_id', 14),
                (self.env._('Plot'), 'parcel', 30), (self.env._('Treated Area (m²)'), 'treated_area', 12),
                (self.env._('Product'), 'product_id', 26), (self.env._('MA No.'), 'amm_number', 14), (self.env._('Dose (per ha)'), 'dose', 12),
                (self.env._('Quantity Used'), 'quantity', 12), (self.env._('Unit'), 'uom_id', 8), (self.env._('Operator'), 'operator', 20),
                (self.env._('Target'), 'target', 18), (self.env._('Conditions'), 'weather_notes', 28),
            ],
            'fertilization': [
                (self.env._('Date'), 'date', 12), (self.env._('Season'), 'season_id', 14), (self.env._('Bed'), 'bed_id', 16),
                (self.env._('Crop'), 'crop_id', 18), (self.env._('Fertilized Area (m²)'), 'treated_area', 12),
                (self.env._('Fertilizer'), 'product_id', 26), (self.env._('Quantity'), 'quantity', 12), (self.env._('Unit'), 'uom_id', 8),
                (self.env._('Quantity (kg)'), 'quantity_kg', 12), (self.env._('Nitrogen Content (%)'), 'nitrogen_content', 12),
                (self.env._('Nitrogen Applied (kg N)'), 'nitrogen_kg', 14), (self.env._('Nitrogen (kg N/ha)'), 'nitrogen_per_ha', 12),
                (self.env._('Remark'), 'note', 30),
            ],
            'organic': [
                (self.env._('Date'), 'date', 12), (self.env._('Season'), 'season_id', 14), (self.env._('Crop'), 'crop_id', 18),
                (self.env._('Bed'), 'bed_id', 16), (self.env._('Organic Crop'), 'organic_crop', 10), (self.env._('Product'), 'product_id', 26),
                (self.env._('Input Type'), 'input_type', 16), (self.env._('Lot'), 'lot_id', 14), (self.env._('Quantity'), 'quantity', 12),
                (self.env._('Unit'), 'uom_id', 8), (self.env._('Allowed in organic'), 'organic_allowed', 14),
                (self.env._('Not Allowed in Organic'), 'alert', 14), (self.env._('Remark'), 'note', 36),
            ],
        }

    def _get_xlsx(self):
        """Contenu du classeur XLSX du registre (recalculé) : ``(nom de fichier, octets)``."""
        self.ensure_one()
        self._compute_lines()
        try:
            import xlsxwriter  # noqa: PLC0415
        except ImportError:
            raise UserError(self.env._('The xlsxwriter library is required for the XLSX export.'))
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
                        sheet.write(row, col, self.env._('Yes') if value else self.env._('No'))
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
        if field.type == 'selection':
            return dict(field._description_selection(self.env)).get(value, '')
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
        if self.register == 'organic':
            seed_headers = [
                (self.env._('Crop'), 18), (self.env._('Season'), 14), (self.env._('Bed'), 16),
                (self.env._('Species'), 16), (self.env._('Variety'), 20), (self.env._('Organic status of the variety'), 22),
                (self.env._('Variety Supplier'), 22), (self.env._('Seeds and Plants Used'), 28),
                (self.env._("Lots"), 18), (self.env._('Origin of the Lots (Receipt)'), 26),
                (self.env._('Receipt Date'), 14),
            ]
            alert_rows = [row for line, row in zip(self.line_ids, tabs[0][2]) if line.alert]
            tabs = [(self.env._('Seeds'), seed_headers, self._get_organic_seed_rows()),
                    (self.env._('Inputs'), tabs[0][1], tabs[0][2]),
                    (self.env._('Organic Alerts'), tabs[0][1], alert_rows)]
        if self.register == 'fertilization':
            tabs.append((
                self.env._('Summary per Bed'),
                [(self.env._('Season'), 14), (self.env._('Bed'), 16), (self.env._('Nitrogen Applied (kg N)'), 16),
                 (self.env._('Cumulative Nitrogen (kg N/ha)'), 16)],
                [[season.name or '', bed.name or '', kg, per_ha]
                 for season, bed, kg, per_ha in self._get_fertilization_summary()],
            ))
        return tabs
