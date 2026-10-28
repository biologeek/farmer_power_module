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
    action_ids = fields.One2many('garden.action', 'bed_id', string='Actions')

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
    def get_occupancy_data(self, domain=None):
        domain = domain or []
        beds = self.search(domain, order='name')
        crops = self.env['garden.crop'].search([('bed_id', 'in', beds.ids)])

        start_dates = crops.mapped('date_start')
        end_dates = crops.mapped('date_end')
        today = fields.Date.today()
        start = min(start_dates) if start_dates else today
        end = max([d or start for d in end_dates]) if end_dates else start

        bed_data = []
        for bed in beds:
            bed_crops = crops.filtered(lambda crop: crop.bed_id == bed).sorted(key=lambda crop: crop.date_start or "")
            bed_data.append({
                'id': bed.id,
                'name': bed.name,
                'crops': [
                    {
                        'id': crop.id,
                        'label': crop.template_id.name or "",
                        'date_start': crop.date_start,
                        'date_end': crop.date_end or crop.date_start,
                    }
                    for crop in bed_crops
                ],
            })
        return {
            'beds': bed_data,
            'start_date': start,
            'end_date': end,
        }
