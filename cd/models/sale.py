# -*- coding: utf-8 -*-

from odoo import models, fields, api


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _prepare_confirmation_values(self):
        return {
            'state': 'sale',
            # 'date_order': fields.Datetime.now()
        }

