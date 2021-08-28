# -*- coding: utf-8 -*-

from odoo import models, fields, api
from collections import defaultdict
from odoo.tools.misc import format_date, OrderedSet


class StockMove(models.Model):
    _inherit = 'stock.move'

    state = fields.Selection([
        ('draft', 'New'), ('cancel', 'Cancelled'),
        ('waiting', 'Waiting Another Move'),
        ('confirmed', 'Waiting Availability'),
        ('partially_available', 'Partially Available'),
        ('assigned', 'Available'),
        ('processing', 'Processing'),
        ('done', 'Done')], string='Status',
        copy=False, default='draft', index=True, readonly=True,
        help="* New: When the stock move is created and not yet confirmed.\n"
             "* Waiting Another Move: This state can be seen when a move is waiting for another one, for example in a chained flow.\n"
             "* Waiting Availability: This state is reached when the procurement resolution is not straight forward. It may need the scheduler to run, a component to be manufactured...\n"
             "* Processing: When products are being processed, it is set to \'Processing\'.\n"
             "* Available: When products are reserved, it is set to \'Available\'.\n"
             "* Done: When the shipment is processed, the state is \'Done\'.")


    def _set_processing(self):
        moves_state_to_write = defaultdict(OrderedSet)
        for move in self:
            if move.state in ('cancel', 'done', 'draft'):
                continue
            else:
                moves_state_to_write['processing'].add(move.id)
        for state, moves_ids in moves_state_to_write.items():
            moves = self.env['stock.move'].browse(moves_ids)
            moves.write({'state': state})
        return True
