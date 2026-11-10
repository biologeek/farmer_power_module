from datetime import datetime, time, timedelta

from odoo import api, fields, models
from odoo.tools import float_round, plaintext2html
from odoo.exceptions import UserError, ValidationError


class GardenOperation(models.Model):
    _name = 'garden.operation'
    _description = 'Operation (work on a crop, bed or block)'
    # Remplace les anciennes « actions » et le « post-process » : un travail planifié puis réalisé,
    # sur une ou plusieurs cultures, sur des planches ou sur un îlot entier.
    _inherit = ['mail.thread', 'hr.mixin']
    _order = 'planned_date desc, id desc'

    name = fields.Char(
        'Label', compute='_compute_name', store=True, readonly=False, tracking=True,
        help='Suggested automatically: operation type and target. Editable.',
    )
    type_id = fields.Many2one(
        'garden.operation.type', string='Operation Type', required=True, index=True, ondelete='restrict',
        tracking=True, help='Nature of the work (sowing, watering, harvest...).',
    )
    category = fields.Selection(
        related='type_id.category', string='Category', store=True, index=True,
    )
    type_icon = fields.Char(related='type_id.icon', string='Type Icon')
    requires_quantity = fields.Boolean(related='type_id.requires_quantity', string='Quantity Required')
    state = fields.Selection(
        [
            ('planned', 'Planned'),
            ('in_progress', 'In Progress'),
            ('done', 'Done'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status', required=True, default='planned', copy=False, tracking=True, index=True,
        help='Planned: to do. In progress: started. Done: finished, the time is allocated to the crops. '
             'Cancelled: will not be done.',
    )
    planned_date = fields.Date(
        'Planned Date', default=fields.Date.context_today, index=True, tracking=True,
        help='Day the operation must be done; it appears in "My Day" from that date.',
    )
    date = fields.Date(
        'Completion Date', copy=False, index=True, tracking=True,
        help='Day the operation was done (set when the operation is completed). Used to find the crops in '
             'place for the allocation.',
    )
    company_id = fields.Many2one(
        'res.company', string='Company', required=True, default=lambda self: self.env.company, index=True,
        help='Company owning the operation.',
    )

    # Périmètre
    scope = fields.Selection(
        [('crop', 'Crop'), ('bed', 'Bed'), ('garden', 'Block')],
        string='Scope', compute='_compute_scope', store=True, readonly=False, precompute=True,
        required=True,
        help='Target of the work: one or several crops, one or several beds, or a whole block. Suggested '
             'according to the operation type.',
    )
    crop_ids = fields.Many2many(
        'garden.crop', 'garden_operation_crop_rel', 'operation_id', 'crop_id', string='Crops',
        help='Crops concerned ("Crop" scope).',
    )
    bed_ids = fields.Many2many(
        'garden.bed', 'garden_operation_bed_rel', 'operation_id', 'bed_id', string='Beds',
        help='Beds concerned ("Bed" scope).',
    )
    garden_id = fields.Many2one(
        'garden.garden', string='Block', index=True, help='Block concerned ("Block" scope).',
    )
    garden_main_id = fields.Many2one(
        'garden.garden', string='Main Block', compute='_compute_garden_main', store=True, index=True,
        help='Block of the target (the first one if several); used to group the operations.',
    )

    # Travail
    employee_ids = fields.Many2many(
        'hr.employee', 'garden_operation_employee_rel', 'operation_id', 'employee_id', string='Employees',
        help='People who carry out the operation.',
    )
    duration = fields.Float(
        'Duration (per employee)',
        help='Work duration in hours for each employee (hh:mm). Without detailed entry, the total time is the '
             'duration multiplied by the number of employees.',
    )
    worker_ids = fields.One2many(
        'garden.operation.worker', 'operation_id', string='Details per Employee', copy=True,
        help='Detailed time entry per employee. When filled, it replaces "duration × number of employees".',
    )
    total_hours = fields.Float(
        'Total Time (h)', compute='_compute_total_hours', store=True,
        help='Sum of the details per employee if any, otherwise duration × number of employees (an operation '
             'without employee counts for one person).',
    )
    labour_cost = fields.Float(
        'Labor Cost', compute='_compute_labour_cost', store=True, digits='Product Price',
        groups='farmer_power.group_garden_chef',
        help='Sum of duration × hourly cost of each employee; without an hourly cost on the employee (or '
             'without employee), the default hourly rate of the settings applies.',
    )
    template_step_id = fields.Many2one(
        'garden.crop.template.step', string='Template Step', copy=False, index=True, ondelete='set null',
        help='Template step the planned operation comes from; prevents generating it twice.',
    )
    allocation_ids = fields.One2many(
        'garden.operation.allocation', 'operation_id', string='Allocation',
        help='Allocation of time and cost between crops, computed when the operation is done.',
    )
    allocation_warning = fields.Char(
        'Allocation Warning', compute='_compute_allocation_warning',
        help='Set if the operation is done but no crop was in place: nothing is allocated.',
    )
    timer_start = fields.Datetime(
        'Timer Start', copy=False, readonly=True,
        help='Time the timer was started; set as long as the timer runs.',
    )
    description = fields.Text('Description', help='Instructions or report of the work.')

    # Intrants et mouvements de stock
    input_ids = fields.One2many(
        'garden.operation.input', 'operation_id', string='Inputs', copy=True,
        help='Products consumed by the operation. Stock moves are created when it is done.',
    )
    input_cost = fields.Float(
        'Input Cost', compute='_compute_input_cost', store=True, digits='Product Price',
        groups='farmer_power.group_garden_chef',
        help='Sum of the input cost (quantity × product cost).',
    )
    move_ids = fields.One2many(
        'stock.move', 'garden_operation_id', string='Stock Moves', readonly=True,
        groups='farmer_power.group_garden_chef',
        help='Consumption and harvest moves created by the operation, with their cancellations.',
    )

    # Spécifique à la catégorie
    harvest_product_id = fields.Many2one(
        'product.product', string='Harvested Product', compute='_compute_harvest_product', store=True,
        readonly=False, help='Harvested product (suggested from the variety of the crop). Harvest only.',
    )
    harvest_qty = fields.Float('Harvested Quantity', digits='Product Unit', help='Harvested quantity (harvest only).')
    harvest_uom_id = fields.Many2one(
        'uom.uom', string='Harvest Unit', compute='_compute_harvest_uom', store=True, readonly=False,
        help='Unit of the harvested quantity (suggested from the product).',
    )
    water_volume = fields.Float(
        'Water Volume (L)', compute='_compute_water_volume', store=True, readonly=False,
        help='Duration × irrigation flow of the block (irrigation only). Editable if the volume is measured.',
    )
    target = fields.Char('Treatment Target', help='Targeted pest or disease (treatment only).')
    weather_notes = fields.Text('Weather Conditions', help='Weather at the time of the treatment (treatment only).')

    # Délai avant récolte (DAR, phase 6)
    dar_override = fields.Boolean(
        'Pre-Harvest Interval Waiver', copy=False, tracking=True, groups='farmer_power.group_garden_manager',
        help='Ticked by the manager to allow a harvest before the end of the pre-harvest interval (PHI) of a '
             'plant protection treatment. A reason is required; the waiver is traced in the chatter.',
    )
    dar_override_reason = fields.Char(
        'Waiver Reason', copy=False, tracking=True, groups='farmer_power.group_garden_manager',
        help='Justification of the pre-harvest interval waiver (required when it is ticked).',
    )
    dar_override_user_id = fields.Many2one(
        'res.users', string='Waiver Granted by', copy=False, readonly=True,
        groups='farmer_power.group_garden_manager',
        help='Manager who ticked the pre-harvest interval waiver.',
    )
    dar_warning = fields.Text(
        'PHI Warning', compute='_compute_dar_warning', compute_sudo=True,
        help='For a harvest not yet done: crops whose pre-harvest interval (PHI) has not elapsed on the '
             'harvest date. Validation will be blocked while the interval runs, unless the manager grants a '
             'waiver.',
    )

    # ------------------------------------------------------------------
    # Calculs
    # ------------------------------------------------------------------
    @api.model
    def _get_default_hourly_rate(self):
        """Taux horaire par défaut (paramètre système ``farmer_power.default_hourly_rate``, défaut 15)."""
        value = self.env['ir.config_parameter'].sudo().get_param('farmer_power.default_hourly_rate', '15')
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

    @api.depends('input_ids.cost')
    def _compute_input_cost(self):
        for operation in self:
            operation.input_cost = sum(operation.input_ids.mapped('cost'))

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

    def _get_target_area(self):
        """Surface (m²) de la cible : cultures (surface occupée), planches ou îlot (surface totale)."""
        self.ensure_one()
        if self.scope == 'crop':
            return sum(self.crop_ids.mapped('area'))
        if self.scope == 'bed':
            return sum(self.bed_ids.mapped('area'))
        return self.garden_id.area

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
            'crop': self.env._('Choose at least one crop for an operation with the "Crop" scope.'),
            'bed': self.env._('Choose at least one bed for an operation with the "Bed" scope.'),
            'garden': self.env._('Choose the block for an operation with the "Block" scope.'),
        }
        for operation in self:
            if not operation._get_target_records():
                raise ValidationError(messages[operation.scope])

    @api.constrains('dar_override', 'dar_override_reason')
    def _check_dar_override_reason(self):
        for operation in self.sudo():
            if operation.dar_override and not (operation.dar_override_reason or '').strip():
                raise ValidationError(self.env._(
                    'Enter the reason for the pre-harvest interval waiver (operation "%s").', operation.name,
                ))

    @api.constrains('duration')
    def _check_duration(self):
        if any(operation.duration < 0 for operation in self):
            raise ValidationError(self.env._('The duration cannot be negative.'))

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
                    'Enter the harvested quantity before completing operation "%s".', operation.name,
                ))
            if operation.category == 'harvest' and operation.harvest_qty > 0 and not operation.harvest_product_id:
                raise UserError(self.env._(
                    'Enter the harvested product before completing operation "%s".', operation.name,
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
    # Délai avant récolte (DAR)
    # ------------------------------------------------------------------
    # Une récolte « faite » à une date antérieure à la fin du DAR d'un traitement phytosanitaire de la même
    # culture est refusée (ValidationError), pour chaque culture concernée. Sont comptés les traitements
    # faits (opérations annulées ou planifiées ignorées), de date inférieure ou égale à la récolte, dont
    # le produit a un DAR > 0 ; la récolte est autorisée à partir du jour « traitement + DAR » inclus. Le
    # gérant lève le blocage par la dérogation (``dar_override`` + motif), tracée dans le fil de discussion.
    _DAR_CHECK_FIELDS = {'state', 'date', 'planned_date', 'type_id', 'scope', 'crop_ids', 'bed_ids', 'garden_id'}

    def _get_dar_date(self):
        """Date de récolte contrôlée : celle de réalisation, sinon le jour de la validation (ou la date prévue)."""
        self.ensure_one()
        if self.state == 'done':
            return self.date or self.planned_date or fields.Date.context_today(self)
        return self.date or fields.Date.context_today(self)

    def _get_dar_conflicts(self):
        """Délais non écoulés à la date de récolte : ``[(culture, date du traitement, fin du DAR, ligne d'intrant)]``."""
        self.ensure_one()
        if self.category != 'harvest' or not self.scope:
            return []
        harvest_date = self._get_dar_date()
        conflicts = []
        for crop in self.sudo()._get_allocation_crops():
            for day, end, line in crop._get_treatment_deadlines():
                if day <= harvest_date < end:
                    conflicts.append((crop, day, end, line))
        return conflicts

    def _format_dar_conflicts(self, conflicts):
        return "\n".join(
            self.env._(
                '%(crop)s: treated on %(day)s with "%(product)s" (interval %(days)s d), harvest possible from %(end)s.',
                crop=crop.name, day=fields.Date.to_string(day), product=line.product_id.display_name,
                days=line.product_id.pre_harvest_interval_days, end=fields.Date.to_string(end),
            )
            for crop, day, end, line in conflicts
        )

    @api.depends(
        'state', 'category', 'date', 'scope', 'crop_ids', 'bed_ids', 'garden_id', 'dar_override',
    )
    def _compute_dar_warning(self):
        for operation in self:
            conflicts = operation._get_dar_conflicts() if operation.state in ('planned', 'in_progress') else []
            operation.dar_warning = operation._format_dar_conflicts(conflicts) if conflicts else False

    def _check_dar(self):
        """Refuse les récoltes faites dans le délai avant récolte d'un traitement, sauf dérogation du gérant."""
        for operation in self.filtered(lambda o: o.state == 'done' and o.category == 'harvest'):
            conflicts = operation._get_dar_conflicts()
            if not conflicts:
                continue
            details = operation._format_dar_conflicts(conflicts)
            operation_sudo = operation.sudo()
            if operation_sudo.dar_override:
                operation.message_post(
                    body=plaintext2html(self.env._(
                        'Harvest validated with a pre-harvest interval waiver (waiver by %(user)s). Reason: %(reason)s',
                        user=operation_sudo.dar_override_user_id.name or "?", reason=operation_sudo.dar_override_reason,
                    ) + "\n" + details),
                    subtype_xmlid='mail.mt_note',
                )
                continue
            raise ValidationError(self.env._(
                'Pre-harvest interval (PHI) not respected, harvest "%(operation)s" is blocked:\n%(details)s\nOnly a '
                'manager can lift this block (waiver with a reason).',
                operation=operation.name, details=details,
            ))

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
                    'No crop in place on the date of the operation: time and cost are not allocated to any crop.',
                )
            else:
                operation.allocation_warning = False

    def _update_allocations(self):
        """(Re)calcule la répartition des opérations faites ; supprime celle des autres."""
        Allocation = self.env['garden.operation.allocation'].sudo()
        touched = self.env['garden.crop']
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
            touched |= crops
        touched._update_progress()

    @api.model_create_multi
    def create(self, vals_list):
        # les lignes d'intrants créées avec l'opération ne sont pas verrouillées (état « faite » dès la création)
        vals_list = [dict(v, dar_override_user_id=self.env.uid) if v.get('dar_override') else v for v in vals_list]
        operations = super(GardenOperation, self.with_context(garden_creating_operation=True)).create(vals_list)
        operations = operations.with_context(garden_creating_operation=False)
        done = operations.filtered(lambda o: o.state == 'done')
        for operation in operations.sudo().filtered('dar_override'):
            operation._post_dar_override()
        done._check_dar()
        done._update_allocations()
        done._sync_stock()
        return operations

    def write(self, vals):
        if self._STOCK_LOCKED_FIELDS & vals.keys():
            self._check_stock_unlocked(vals)
        if 'dar_override' in vals:
            vals = dict(vals, dar_override_user_id=self.env.uid if vals['dar_override'] else False)
        result = super().write(vals)
        if vals.get('dar_override'):
            self.sudo()._post_dar_override()
        if self._DAR_CHECK_FIELDS & vals.keys():
            self._check_dar()
        if self._ALLOCATION_FIELDS & vals.keys():
            self._update_allocations()
        if 'state' in vals:
            self._sync_stock()
        return result

    def _post_dar_override(self):
        """Trace dans le fil de discussion qui a accordé la dérogation au DAR, et pourquoi."""
        for operation in self:
            operation.message_post(
                body=plaintext2html(self.env._(
                    'Pre-harvest interval waiver granted by %(user)s. Reason: %(reason)s',
                    user=(operation.dar_override_user_id or self.env.user).name,
                    reason=operation.dar_override_reason or "-",
                )),
                subtype_xmlid='mail.mt_note',
            )

    def unlink(self):
        # les mouvements de stock d'une opération supprimée sont annulés (mouvements inverses)
        self.filtered(lambda o: o.state == 'done')._stock_reopen()
        return super().unlink()

    # ------------------------------------------------------------------
    # Stock : consommation des intrants et entrée en stock des récoltes
    # ------------------------------------------------------------------
    # À la validation (état « faite »), l'opération :
    # - consomme ses intrants : mouvement stock -> « Consommation maraîchage », au coût du produit ;
    # - pour une récolte, crée l'entrée en stock de `harvest_product_id` depuis « Production maraîchage »,
    #   répartie entre les cultures au prorata de la répartition (un mouvement et un lot par culture quand
    #   le produit est suivi par lots).
    # À la réouverture ou à la suppression, les mouvements ne sont jamais supprimés : un mouvement inverse
    # les annule (historique de stock conservé). Les mouvements sont créés en `sudo()` : l'ouvrier n'a
    # aucun droit sur le stock.
    _STOCK_LOCKED_FIELDS = {
        'harvest_qty', 'harvest_product_id', 'harvest_uom_id', 'scope', 'crop_ids', 'bed_ids', 'garden_id', 'date',
    }

    def _check_stock_unlocked(self, vals):
        """Refuse de modifier une récolte déjà passée en stock (sauf si l'état change dans le même temps)."""
        if vals.get('state', 'done') != 'done':
            return
        for operation in self.filtered(lambda o: o.state == 'done'):
            if operation._get_active_moves('harvest'):
                raise UserError(self.env._(
                    'Harvest "%s" is already in stock: set the operation back to planned before modifying it.',
                    operation.name,
                ))

    def _get_active_moves(self, kind=None):
        """Mouvements de l'opération en vigueur (non annulés par un mouvement inverse), éventuellement d'un type."""
        self.ensure_one()
        moves = self.sudo().move_ids
        reversed_moves = moves.garden_reverse_of_id
        return moves.filtered(lambda m: m not in reversed_moves and (not kind or m.garden_kind == kind)
                              and m.state == 'done')

    def _sync_stock(self):
        for operation in self:
            if operation.state == 'done':
                operation._stock_done()
            else:
                operation._stock_reopen()

    def _stock_done(self):
        self.ensure_one()
        self.input_ids._consume()
        self._stock_harvest()

    def _stock_reopen(self):
        for operation in self:
            operation.input_ids._unconsume()
            for move in operation._get_active_moves('harvest'):
                operation._reverse_stock_move(move, 'harvest_return')

    def _prepare_stock_move_vals(self, product, quantity, uom, source, destination, lot, kind, origin=None, crop=None):
        """Valeurs d'un mouvement terminé (quantité faite et cochée) pour ``stock.move``."""
        self.ensure_one()
        return {
            'origin': origin or self.name,
            'company_id': self.company_id.id,
            'product_id': product.id,
            'product_uom': uom.id,
            'product_uom_qty': quantity,
            'location_id': source.id,
            'location_dest_id': destination.id,
            'state': 'draft',
            'picked': True,
            'garden_operation_id': self.id,
            'garden_crop_id': crop.id if crop else False,
            'garden_kind': kind,
            'move_line_ids': [(0, 0, {
                'product_id': product.id,
                'product_uom_id': uom.id,
                'quantity': quantity,
                'location_id': source.id,
                'location_dest_id': destination.id,
                'lot_id': lot.id if lot else False,
                'picked': True,
            })],
        }

    def _set_move_date(self, move):
        """Date du mouvement (et de ses lignes) = date de réalisation de l'opération."""
        self.ensure_one()
        if self.date:
            moment = datetime.combine(self.date, time(12, 0))
            move.write({'date': moment})
            move.move_line_ids.write({'date': moment})

    def _reverse_stock_move(self, move, kind):
        """Crée le mouvement inverse d'un mouvement terminé (même lot, même quantité)."""
        self.ensure_one()
        move = move.sudo()
        lines = move.move_line_ids
        reverse = self.env['stock.move'].sudo().with_company(self.company_id).create(
            dict(
                self._prepare_stock_move_vals(
                    move.product_id, move.product_uom_qty, move.product_uom, move.location_dest_id,
                    move.location_id, lines[:1].lot_id, kind=kind,
                    origin=self.env._('Cancellation: %s', self.name), crop=move.garden_crop_id,
                ),
                garden_reverse_of_id=move.id,
            ),
        )
        reverse._action_done()
        self._set_move_date(reverse)
        return reverse

    # Récolte ------------------------------------------------------------
    def _get_harvest_shares(self):
        """Quantité récoltée par culture : ``[(culture, quantité)]``, au prorata de la répartition.

        Le reste d'arrondi va à la dernière culture pour conserver le total. Sans répartition
        (aucune culture en place), retourne ``[(culture vide, quantité totale)]``.
        """
        self.ensure_one()
        allocations = self.allocation_ids.sudo().sorted('id')
        if not allocations:
            return [(self.env['garden.crop'], self.harvest_qty)]
        total_share = sum(allocations.mapped('share')) or 100.0
        precision = self.env['decimal.precision'].precision_get('Product Unit')
        shares, assigned = [], 0.0
        for index, allocation in enumerate(allocations):
            if index == len(allocations) - 1:
                quantity = float_round(self.harvest_qty - assigned, precision_digits=precision)
            else:
                quantity = float_round(self.harvest_qty * allocation.share / total_share, precision_digits=precision)
            assigned += quantity
            shares.append((allocation.crop_id, quantity))
        return shares

    def _get_harvest_lot(self, product, crop):
        """Lot de récolte de la culture pour le produit (créé au besoin, nommé d'après la référence de la culture)."""
        self.ensure_one()
        Lot = self.env['stock.lot'].sudo()
        lot = Lot.search([
            ('product_id', '=', product.id), ('name', '=', crop.name),
            ('company_id', 'in', (self.company_id.id, False)),
        ], limit=1)
        if not lot:
            lot = Lot.create({
                'name': crop.name, 'product_id': product.id, 'company_id': self.company_id.id,
            })
        if lot.garden_crop_id != crop:
            lot.garden_crop_id = crop
        return lot

    def _stock_harvest(self):
        self.ensure_one()
        if self.category != 'harvest' or self.harvest_qty <= 0 or not self.harvest_product_id:
            return
        if self._get_active_moves('harvest'):
            return
        company = self.company_id
        source = company.garden_production_location_id
        destination = company._get_garden_stock_location()
        if not source or not destination:
            raise UserError(self.env._(
                'Configure the storage location and the "Market Gardening Production" location of company "%s".',
                company.name,
            ))
        product = self.harvest_product_id.sudo()
        uom = self.harvest_uom_id or product.uom_id
        if product.tracking == 'serial':
            raise UserError(self.env._(
                'A harvested product tracked by serial number is not supported ("%s").', product.display_name,
            ))
        shares = self._get_harvest_shares()
        if product.tracking == 'lot' and not all(crop for crop, _qty in shares):
            raise UserError(self.env._(
                'Product "%s" is tracked by lots: no crop in place on the date of the operation to name the lot.',
                product.display_name,
            ))
        Move = self.env['stock.move'].sudo().with_company(company)
        for crop, quantity in shares:
            if quantity <= 0:
                continue
            lot = self._get_harvest_lot(product, crop) if product.tracking == 'lot' else self.env['stock.lot']
            move = Move.create(self._prepare_stock_move_vals(
                product, quantity, uom, source, destination, lot, kind='harvest', crop=crop,
            ))
            move._action_done()
            self._set_move_date(move)
        if not all(crop for crop, _qty in shares):
            self.message_post(
                body=self.env._('Harvest put in stock without crop or lot: no crop in place on the date of the operation.'),
                subtype_xmlid='mail.mt_note',
            )
