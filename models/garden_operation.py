from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class GardenOperation(models.Model):
    _name = 'garden.operation'
    _description = 'Opération (travail sur culture, planche ou îlot)'
    # Remplace les anciennes « actions » et le « post-process » : un travail planifié puis réalisé,
    # sur une ou plusieurs cultures, sur des planches ou sur un îlot entier.
    _inherit = ['mail.thread']
    _order = 'planned_date desc, id desc'

    name = fields.Char(
        'Libellé', compute='_compute_name', store=True, readonly=False, tracking=True,
        help="Proposé automatiquement : type d'opération et cible. Modifiable.",
    )
    type_id = fields.Many2one(
        'garden.operation.type', string="Type d'opération", required=True, index=True, ondelete='restrict',
        tracking=True, help="Nature du travail (semis, arrosage, récolte...).",
    )
    category = fields.Selection(
        related='type_id.category', string='Catégorie', store=True, index=True,
    )
    state = fields.Selection(
        [
            ('planned', 'Planifiée'),
            ('in_progress', 'En cours'),
            ('done', 'Faite'),
            ('cancelled', 'Annulée'),
        ],
        string='État', required=True, default='planned', copy=False, tracking=True, index=True,
        help="Planifiée : à faire. En cours : commencée. Faite : terminée, le temps est réparti sur les cultures. "
             "Annulée : ne sera pas faite.",
    )
    planned_date = fields.Date(
        'Date prévue', default=fields.Date.context_today, index=True, tracking=True,
        help="Jour où l'opération doit être faite ; elle apparaît dans « Ma journée » à partir de cette date.",
    )
    date = fields.Date(
        'Date de réalisation', copy=False, index=True, tracking=True,
        help="Jour où l'opération a été faite (renseigné à la fin de l'opération). "
             "Sert à retrouver les cultures en place pour la répartition.",
    )
    company_id = fields.Many2one(
        'res.company', string='Société', required=True, default=lambda self: self.env.company, index=True,
        help="Société propriétaire de l'opération.",
    )

    # Périmètre
    scope = fields.Selection(
        [('crop', 'Culture'), ('bed', 'Planche'), ('garden', 'Îlot')],
        string='Périmètre', compute='_compute_scope', store=True, readonly=False, precompute=True,
        required=True,
        help="Cible du travail : une ou plusieurs cultures, une ou plusieurs planches, ou un îlot entier. "
             "Proposé selon le type d'opération.",
    )
    crop_ids = fields.Many2many(
        'garden.crop', 'garden_operation_crop_rel', 'operation_id', 'crop_id', string='Cultures',
        help="Cultures concernées (périmètre « Culture »).",
    )
    bed_ids = fields.Many2many(
        'garden.bed', 'garden_operation_bed_rel', 'operation_id', 'bed_id', string='Planches',
        help="Planches concernées (périmètre « Planche »).",
    )
    garden_id = fields.Many2one(
        'garden.garden', string='Îlot', index=True, help="Îlot concerné (périmètre « Îlot »).",
    )
    garden_main_id = fields.Many2one(
        'garden.garden', string='Îlot principal', compute='_compute_garden_main', store=True, index=True,
        help="Îlot de la cible (le premier si plusieurs) ; sert à regrouper les opérations.",
    )

    # Travail
    employee_ids = fields.Many2many(
        'hr.employee', 'garden_operation_employee_rel', 'operation_id', 'employee_id', string='Employés',
        help="Personnes qui réalisent l'opération.",
    )
    duration = fields.Float(
        'Durée (par employé)',
        help="Durée de travail en heures pour chaque employé (hh:mm). Sans saisie détaillée, "
             "le temps total est la durée multipliée par le nombre d'employés.",
    )
    description = fields.Text('Description', help="Consignes ou compte rendu du travail.")

    # Spécifique à la catégorie
    harvest_product_id = fields.Many2one(
        'product.product', string='Produit récolté', compute='_compute_harvest_product', store=True,
        readonly=False, help="Produit récolté (proposé d'après la variété de la culture). Récolte uniquement.",
    )
    harvest_qty = fields.Float('Quantité récoltée', digits='Product Unit', help="Quantité récoltée (récolte uniquement).")
    harvest_uom_id = fields.Many2one(
        'uom.uom', string='Unité de récolte', compute='_compute_harvest_uom', store=True, readonly=False,
        help="Unité de la quantité récoltée (proposée d'après le produit).",
    )
    water_volume = fields.Float(
        "Volume d'eau (L)", compute='_compute_water_volume', store=True, readonly=False,
        help="Durée × débit d'irrigation de l'îlot (irrigation uniquement). Modifiable si le volume est mesuré.",
    )
    target = fields.Char('Cible du traitement', help="Ravageur ou maladie visé (traitement uniquement).")
    weather_notes = fields.Text('Conditions météo', help="Météo au moment du traitement (traitement uniquement).")

    # ------------------------------------------------------------------
    # Calculs
    # ------------------------------------------------------------------
    @api.depends('type_id.default_scope')
    def _compute_scope(self):
        for operation in self:
            operation.scope = operation.type_id.default_scope or operation.scope or 'crop'

    def _get_target_records(self):
        """Cible de l'opération selon son périmètre (cultures, planches ou îlot)."""
        self.ensure_one()
        return {'crop': self.crop_ids, 'bed': self.bed_ids, 'garden': self.garden_id}[self.scope]

    def _get_gardens(self):
        """Îlots concernés par l'opération."""
        self.ensure_one()
        if self.scope == 'garden':
            return self.garden_id
        if self.scope == 'bed':
            return self.bed_ids.garden_id
        return self.crop_ids.bed_id.garden_id

    @api.depends('type_id', 'scope', 'crop_ids.name', 'bed_ids.name', 'garden_id.name')
    def _compute_name(self):
        for operation in self:
            targets = operation._get_target_records() if operation.scope else operation.crop_ids
            names = [t.name for t in targets[:3]]
            if len(targets) > 3:
                names.append("+%d" % (len(targets) - 3))
            label = ", ".join(n for n in names if n)
            type_name = operation.type_id.name or ""
            operation.name = "%s - %s" % (type_name, label) if type_name and label else (type_name or label)

    @api.depends('scope', 'crop_ids.bed_id.garden_id', 'bed_ids.garden_id', 'garden_id')
    def _compute_garden_main(self):
        for operation in self:
            operation.garden_main_id = operation._get_gardens()[:1] if operation.scope else False

    @api.depends('category', 'crop_ids.variety_id.harvest_product_id')
    def _compute_harvest_product(self):
        for operation in self:
            if operation.category == 'harvest':
                products = operation.crop_ids.variety_id.harvest_product_id
                operation.harvest_product_id = operation.harvest_product_id or products[:1]
            else:
                operation.harvest_product_id = False

    @api.depends('harvest_product_id')
    def _compute_harvest_uom(self):
        for operation in self:
            operation.harvest_uom_id = operation.harvest_product_id.uom_id

    @api.depends('category', 'duration', 'scope', 'crop_ids.bed_id.garden_id', 'bed_ids.garden_id',
                 'garden_id.irrigation_flow')
    def _compute_water_volume(self):
        for operation in self:
            if operation.category == 'irrigation' and operation.scope:
                flow = sum(operation._get_gardens().mapped('irrigation_flow'))
                operation.water_volume = operation.duration * flow
            else:
                operation.water_volume = 0.0

    @api.constrains('scope', 'crop_ids', 'bed_ids', 'garden_id')
    def _check_scope_target(self):
        messages = {
            'crop': self.env._("Choisissez au moins une culture pour une opération de périmètre « Culture »."),
            'bed': self.env._("Choisissez au moins une planche pour une opération de périmètre « Planche »."),
            'garden': self.env._("Choisissez l'îlot pour une opération de périmètre « Îlot »."),
        }
        for operation in self:
            if not operation._get_target_records():
                raise ValidationError(messages[operation.scope])

    @api.constrains('duration')
    def _check_duration(self):
        if any(operation.duration < 0 for operation in self):
            raise ValidationError(self.env._("La durée ne peut pas être négative."))

    # ------------------------------------------------------------------
    # Changement d'état
    # ------------------------------------------------------------------
    def action_start(self):
        self.filtered(lambda o: o.state == 'planned').write({'state': 'in_progress'})

    def action_done(self):
        for operation in self.filtered(lambda o: o.state in ('planned', 'in_progress')):
            if operation.type_id.requires_quantity and operation.harvest_qty <= 0:
                raise UserError(self.env._(
                    "Renseignez la quantité récoltée avant de terminer l'opération « %s ».", operation.name,
                ))
            operation.write({
                'state': 'done',
                'date': operation.date or fields.Date.context_today(operation),
            })

    def action_cancel(self):
        self.filtered(lambda o: o.state != 'done').write({'state': 'cancelled'})

    def action_reset_planned(self):
        self.write({'state': 'planned'})

    # ------------------------------------------------------------------
    # Statistiques
    # ------------------------------------------------------------------
    @api.model
    def get_statistics_data(self, params=None):
        """Temps de travail par type d'opération pour les écrans de statistiques.

        Retourne ``pie`` (liste de ``{label, value}``) et ``stacked`` (``categories`` et ``series``).
        """
        pie = [
            {'label': operation_type.name, 'value': hours}
            for operation_type, hours in self._read_group([('state', '=', 'done')], ['type_id'], ['duration:sum'])
        ]
        return {'pie': pie, 'stacked': {'categories': [], 'series': []}}
