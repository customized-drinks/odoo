# -*- coding: utf-8 -*-

from odoo import models, fields, api


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _prepare_confirmation_values(self):
        return {
            'state': 'sale',
            # 'date_order': fields.Datetime.now()
        }

    # def _find_mail_template(self, force_confirmation_template=False):
    #     template_id = False
    #
    #     if self.state == 'draft':
    #         template_id = self.env['ir.model.data'].xmlid_to_res_id('sale.mail_template_sale_confirmation', raise_if_not_found=False)
    #
    #     return template_id
