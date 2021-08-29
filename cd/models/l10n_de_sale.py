# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.tools import format_date


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    l10n_de_template_data = fields.Binary(compute='_compute_l10n_de_template_data')
    l10n_de_document_title = fields.Char(compute='_compute_l10n_de_document_title')
    l10n_de_addresses = fields.Binary(compute='_compute_l10n_de_addresses')

    def _compute_l10n_de_template_data(self):
        for record in self:
            record.l10n_de_template_data = data = []
            if record.state in ('draft', 'sent'):
                if record.name:
                    data.append((_("Quotation No."), record.name))
                if record.validity_date:
                    data.append((_("Expiration Date"), format_date(self.env, record.validity_date)))
                if record.date_order:
                    data.append((_("Order Date"), format_date(self.env, record.date_order)))
            else:
                if record.name:
                    data.append((_("Order No."), record.name))
                if record.date_order:
                    data.append((_("Order Date"), format_date(self.env, record.date_order)))
            if record.client_order_ref:
                data.append((_('Customer Reference'), record.client_order_ref))
            if record.user_id:
                data.append((_("Salesperson"), record.user_id.name))
                data.append((_("Email"), record.user_id.login))
                data.append((_("Phone"), record.user_id.phone))


    def _compute_l10n_de_document_title(self):
        for record in self:
            if record.state == 'draft':
                record.l10n_de_document_title = _('Quotation')
            elif record.state == 'sent':
                record.l10n_de_document_title = _('Prepayment Invoice')
            elif record.state == 'sale':
                record.l10n_de_document_title = _('Order Confirmation')
            else:
                record.l10n_de_document_title = _('Order')


    def _compute_l10n_de_addresses(self):
        for record in self:
            record.l10n_de_addresses = data = []
            if record.partner_shipping_id == record.partner_invoice_id:
                data.append((_("Invoicing and Shipping Address:"), record.partner_shipping_id))
            else:
                data.append((_("Shipping Address:"), record.partner_shipping_id))
                data.append((_("Invoicing Address:"), record.partner_invoice_id))
