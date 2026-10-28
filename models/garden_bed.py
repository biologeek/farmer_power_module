from odoo import api, fields, models


class GardenBed(models.Model):
    _name = 'garden.bed'
    _description = 'Planche de culture'
    _inherit = ['mail.thread']
    _order = 'garden_id, code, name'

    name = fields.Char('Nom de la planche', required=True, tracking=True)
    code = fields.Char('Code', copy=False, tracking=True)
    garden_id = fields.Many2one(
        'garden.garden', string='Îlot', required=True, index=True, ondelete='cascade', tracking=True,
    )
    site_id = fields.Many2one(
        'garden.site', string='Site', related='garden_id.site_id', store=True, index=True,
    )
    company_id = fields.Many2one(
        'res.company', string='Société', related='garden_id.company_id', store=True, index=True,
    )
    length = fields.Float('Longueur (m)')
    width = fields.Float('Largeur (m)')
    area = fields.Float('Surface (m²)', compute='_compute_area', store=True)
    soil_type = fields.Selection(
        [
            ('sandy', 'Sableux'),
            ('silty', 'Limoneux'),
            ('clayey', 'Argileux'),
            ('loamy', 'Limono-argileux'),
            ('humus', 'Humifère'),
            ('other', 'Autre'),
        ],
        string='Type de sol',
    )
    notes = fields.Text('Notes')
    active = fields.Boolean('Actif', default=True)
    crop_ids = fields.One2many('garden.crop', 'bed_id', string='Cultures')
    current_crop_ids = fields.One2many(
        'garden.crop', string='Cultures en place', compute='_compute_current_crop_ids',
    )
    operation_ids = fields.Many2many(
        'garden.operation', 'garden_operation_bed_rel', 'bed_id', 'operation_id', string='Opérations',
        help="Opérations dont la cible est directement cette planche (périmètre « Planche »).",
    )

    _code_site_uniq = models.Constraint(
        'UNIQUE (site_id, code)',
        'Le code de la planche doit être unique par site.',
    )

    @api.depends('length', 'width')
    def _compute_area(self):
        for bed in self:
            bed.area = bed.length * bed.width

    @api.depends('crop_ids.occupation_start', 'crop_ids.occupation_end', 'crop_ids.state')
    def _compute_current_crop_ids(self):
        today = fields.Date.context_today(self)
        for bed in self:
            bed.current_crop_ids = bed.crop_ids.filtered(
                lambda crop: crop.state != 'cancelled'
                and crop.occupation_start and crop.occupation_start <= today
                and (not crop.occupation_end or crop.occupation_end >= today)
            )

    @api.model
    def get_occupancy_data(self, domain=None, season_id=False, site_id=False):
        """Données du Gantt d'occupation des planches.

        :param domain: domaine additionnel sur les planches
        :param season_id: ne retient que les cultures de cette saison
        :param site_id: ne retient que les planches de ce site
        :return: dict avec ``beds`` (à plat, compatible avec l'ancien format), ``groups`` (planches
            regroupées par îlot), ``families`` (légende), ``seasons`` et ``sites`` (filtres),
            ``start_date``, ``end_date`` et ``today``.
        """
        domain = list(domain or [])
        if site_id:
            domain.append(('site_id', '=', site_id))
        beds = self.search(domain)
        crop_domain = [('bed_id', 'in', beds.ids)]
        if season_id:
            crop_domain.append(('season_id', '=', season_id))
        crops = self.env['garden.crop'].search(crop_domain, order='planned_sowing_date, date_start, id')

        today = fields.Date.context_today(self)
        to_str = fields.Date.to_string
        family_labels = dict(self.env['garden.species']._fields['family'].selection)
        state_labels = dict(self.env['garden.crop']._fields['state'].selection)

        def crop_data(crop):
            planned_start = crop.planned_sowing_date or crop.planned_transplant_date or crop.planned_harvest_start
            planned_end = crop.planned_harvest_end or crop.planned_harvest_start
            real_start = crop.date_start
            real_end = crop.date_end or (today if real_start and crop.state not in ('done', 'cancelled') else False)
            starts = [d for d in (planned_start, real_start) if d]
            ends = [d for d in (planned_end, real_end, planned_start, real_start) if d]
            return {
                'id': crop.id,
                'name': crop.name,
                'label': crop.template_id.name or "",
                'variety': crop.variety_id.display_name or "",
                'family': crop.family or 'other',
                'family_label': family_labels.get(crop.family or 'other'),
                'state': crop.state,
                'state_label': state_labels.get(crop.state),
                'share': crop.bed_share,
                'planned_start': to_str(planned_start),
                'planned_end': to_str(planned_end),
                'real_start': to_str(real_start),
                'real_end': to_str(real_end),
                # compatibilité avec l'ancien format
                'date_start': to_str(real_start or planned_start),
                'date_end': to_str(real_end or planned_end or real_start or planned_start),
                'warnings': [w for w in (crop.overlap_warning, crop.rotation_warning) if w],
                '_span': (min(starts), max(ends)) if starts else None,
            }

        def assign_lanes(items):
            """Répartit les cultures d'une planche sur des lignes sans recouvrement visuel."""
            lane_ends = []
            for item in sorted((i for i in items if i['_span']), key=lambda i: i['_span']):
                first, last = item['_span']
                for lane, lane_end in enumerate(lane_ends):
                    if lane_end < first:
                        lane_ends[lane] = last
                        item['lane'] = lane
                        break
                else:
                    item['lane'] = len(lane_ends)
                    lane_ends.append(last)
            for item in items:
                item.setdefault('lane', 0)
            return max(len(lane_ends), 1)

        bed_data = []
        groups = {}
        all_dates = []
        used_families = {}
        for bed in beds:
            items = [crop_data(crop) for crop in crops.filtered(lambda c: c.bed_id == bed)]
            lanes = assign_lanes(items)
            for item in items:
                if item['_span']:
                    all_dates.extend(item.pop('_span'))
                else:
                    item.pop('_span')
                used_families[item['family']] = item['family_label']
            entry = {
                'id': bed.id,
                'name': bed.name,
                'code': bed.code or "",
                'area': bed.area,
                'garden_id': bed.garden_id.id,
                'lanes': lanes,
                'crops': items,
            }
            bed_data.append(entry)
            group = groups.setdefault(bed.garden_id.id, {
                'id': bed.garden_id.id,
                'name': "%s › %s" % (bed.site_id.name, bed.garden_id.name),
                'beds': [],
            })
            group['beds'].append(entry)

        season = self.env['garden.season'].browse(season_id) if season_id else self.env['garden.season']
        if season:
            all_dates.extend((season.date_start, season.date_end))
        if not all_dates:
            all_dates = [today, fields.Date.add(today, days=90)]
        return {
            'beds': bed_data,
            'groups': list(groups.values()),
            'families': [{'key': key, 'label': label} for key, label in sorted(used_families.items())],
            'seasons': [{'id': s.id, 'name': s.name} for s in self.env['garden.season'].search([])],
            'sites': [{'id': s.id, 'name': s.display_name} for s in self.env['garden.site'].search([])],
            'start_date': to_str(min(all_dates)),
            'end_date': to_str(max(all_dates)),
            'today': to_str(today),
        }
