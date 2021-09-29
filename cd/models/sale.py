# -*- coding: utf-8 -*-

from odoo import models, fields, api


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    invoice_status = fields.Selection([
        ('upselling', 'Upselling Opportunity'),
        ('invoiced', 'Fully Invoiced'),
        ('to invoice', 'To Invoice'),
        ('no', 'Nothing to Invoice')
    ], string='Invoice Status', compute='_get_invoice_status', store=True, readonly=False)

    def _prepare_confirmation_values(self):
        return {
            'state': 'sale',
            # 'date_order': fields.Datetime.now()
        }

    def _find_mail_template(self, force_confirmation_template=False):
        template_id = False

        if self.state == 'draft':
            template_id = 26
        elif self.state == 'sent':
            template_id = 17
        elif self.state == 'sale':
            template_id = 18

        return template_id

    def _prepare_invoice(self):
        self.ensure_one()
        invoice_vals = super(SaleOrder, self)._prepare_invoice()
        if self.effective_date:
            invoice_vals['delivery_date'] = self.effective_date
        return invoice_vals
