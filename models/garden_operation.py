from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class GardenOperation(models.Model):
    _name = 'garden.operation'
    _description = 'Opération (travail sur culture, planche ou îlot)'
    # Remplace les anciennes « actions » et le « post-process » : un travail planifié puis réalisé,
    # sur une ou plusieurs cultures, sur des planches ou sur un îlot entier.
    _inherit = ['mail.thread', 'hr.mixin']
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
    worker_ids = fields.One2many(
        'garden.operation.worker', 'operation_id', string='Détail par employé', copy=True,
        help="Saisie détaillée du temps par employé. Quand elle est renseignée, elle remplace "
             "« durée × nombre d'employés ».",
    )
    total_hours = fields.Float(
        'Temps total (h)', compute='_compute_total_hours', store=True,
        help="Somme du détail par employé s'il existe, sinon durée × nombre d'employés "
             "(une opération sans employé compte pour une personne).",
    )
    labour_cost = fields.Float(
        'Coût main-d\'œuvre', compute='_compute_labour_cost', store=True, digits='Product Price',
        groups='odoo_garden.group_garden_chef',
        help="Somme de la durée × coût horaire de chaque employé ; à défaut de coût horaire sur l'employé "
             "(ou sans employé), le taux horaire par défaut des paramètres s'applique.",
    )
    template_step_id = fields.Many2one(
        'garden.crop.template.step', string="Étape d'itinéraire", copy=False, index=True, ondelete='set null',
        help="Étape de l'itinéraire à l'origine de l'opération planifiée ; évite de la générer deux fois.",
    )
    allocation_ids = fields.One2many(
        'garden.operation.allocation', 'operation_id', string='Répartition',
        help="Répartition du temps et du coût entre les cultures, calculée quand l'opération est faite.",
    )
    allocation_warning = fields.Char(
        'Avertissement de répartition', compute='_compute_allocation_warning',
        help="Renseigné si l'opération est faite mais qu'aucune culture n'était en place : rien n'est alloué.",
    )
    timer_start = fields.Datetime(
        'Début du chronomètre', copy=False, readonly=True,
        help="Heure de démarrage du chronomètre ; renseigné tant que le chronomètre tourne.",
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
    @api.model
    def _get_default_hourly_rate(self):
        """Taux horaire par défaut (paramètre système ``odoo_garden.default_hourly_rate``, défaut 15)."""
        value = self.env['ir.config_parameter'].sudo().get_param('odoo_garden.default_hourly_rate', '15')
        try:
            return float(value)
        except ValueError:
            return 15.0

    @api.depends('duration', 'employee_ids', 'worker_ids.duration')
    def _compute_total_hours(self):
        for operation in self:
            if operation.worker_ids:
                operation.total_hours = sum(operation.worker_ids.mapped('duration'))
            else:
                operation.total_hours = operation.duration * (len(operation.employee_ids) or 1)

    @api.depends('duration', 'employee_ids.garden_hourly_cost', 'worker_ids.labour_cost')
    def _compute_labour_cost(self):
        default_rate = self._get_default_hourly_rate()
        for operation in self:
            if operation.worker_ids:
                operation.labour_cost = sum(operation.worker_ids.mapped('labour_cost'))
            elif operation.employee_ids:
                operation.labour_cost = operation.duration * sum(
                    employee.garden_hourly_cost or default_rate for employee in operation.employee_ids
                )
            else:
                operation.labour_cost = operation.duration * default_rate

    def _recompute_labour_cost(self):
        """Force le recalcul du coût (changement du taux horaire par défaut)."""
        self.env.add_to_compute(self._fields['labour_cost'], self)
        self.worker_ids._recompute_labour_cost()

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
    # Chronomètre
    # ------------------------------------------------------------------
    def action_start_timer(self):
        """Démarre le chronomètre ; l'employé de l'utilisateur est ajouté si personne n'est affecté."""
        now = fields.Datetime.now()
        employee = self.env.user.sudo().employee_id
        for operation in self.filtered(lambda o: o.state in ('planned', 'in_progress') and not o.timer_start):
            vals = {'timer_start': now, 'state': 'in_progress'}
            if employee and not operation.employee_ids and not operation.worker_ids:
                vals['employee_ids'] = [(4, employee.id)]
            operation.write(vals)

    def action_stop_timer(self):
        """Arrête le chronomètre et ajoute le temps écoulé à la durée (par employé)."""
        now = fields.Datetime.now()
        for operation in self.filtered('timer_start'):
            elapsed = (now - operation.timer_start).total_seconds() / 3600.0
            operation.write({
                'duration': operation.duration + round(max(elapsed, 0.0), 4),
                'timer_start': False,
            })

    # ------------------------------------------------------------------
    # Changement d'état
    # ------------------------------------------------------------------
    def action_start(self):
        """Bouton « Démarrer » : passe en cours et lance le chronomètre."""
        self.action_start_timer()

    def action_done(self):
        self.action_stop_timer()
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
        self.filtered(lambda o: o.state != 'done').write({'state': 'cancelled', 'timer_start': False})

    def action_reset_planned(self):
        self.write({'state': 'planned', 'timer_start': False})

    # ------------------------------------------------------------------
    # Répartition sur les cultures
    # ------------------------------------------------------------------
    # Une opération « faite » est répartie entre les cultures concernées au prorata de leur surface
    # occupée (``garden.crop.area``) :
    # - périmètre « culture » : les cultures choisies ;
    # - périmètre « planche » ou « îlot » : les cultures en place sur ces planches (ou sur les planches
    #   de l'îlot) à la date de l'opération, hors cultures annulées.
    # La répartition est recalculée quand l'opération est modifiée, et supprimée si elle est rouverte.
    # Sans culture en place, rien n'est alloué (avertissement non bloquant).
    _ALLOCATION_FIELDS = {'state', 'date', 'planned_date', 'scope', 'crop_ids', 'bed_ids', 'garden_id'}

    def _get_allocation_date(self):
        self.ensure_one()
        return self.date or self.planned_date or fields.Date.context_today(self)

    def _get_allocation_crops(self):
        """Cultures sur lesquelles l'opération est répartie."""
        self.ensure_one()
        if self.scope == 'crop':
            return self.crop_ids
        beds = self.bed_ids if self.scope == 'bed' else self.garden_id.bed_ids
        day = self._get_allocation_date()
        return beds.crop_ids.filtered(
            lambda crop: crop.state != 'cancelled'
            and crop.occupation_start and crop.occupation_start <= day
            and (not crop.occupation_end or crop.occupation_end >= day)
        )

    @api.depends('state', 'allocation_ids')
    def _compute_allocation_warning(self):
        for operation in self:
            if operation.state == 'done' and not operation.allocation_ids:
                operation.allocation_warning = self.env._(
                    "Aucune culture en place à la date de l'opération : le temps et le coût ne sont alloués à aucune culture.",
                )
            else:
                operation.allocation_warning = False

    def _update_allocations(self):
        """(Re)calcule la répartition des opérations faites ; supprime celle des autres."""
        Allocation = self.env['garden.operation.allocation'].sudo()
        for operation in self:
            operation.allocation_ids.sudo().unlink()
            if operation.state != 'done':
                continue
            crops = operation._get_allocation_crops()
            if not crops:
                operation.message_post(
                    body=operation.allocation_warning, subtype_xmlid='mail.mt_note',
                )
                continue
            total = sum(crops.mapped('area'))
            Allocation.create([
                {
                    'operation_id': operation.id,
                    'crop_id': crop.id,
                    'share': (crop.area / total if total > 0 else 1.0 / len(crops)) * 100.0,
                }
                for crop in crops
            ])

    @api.model_create_multi
    def create(self, vals_list):
        operations = super().create(vals_list)
        operations.filtered(lambda o: o.state == 'done')._update_allocations()
        return operations

    def write(self, vals):
        result = super().write(vals)
        if self._ALLOCATION_FIELDS & vals.keys():
            self._update_allocations()
        return result
