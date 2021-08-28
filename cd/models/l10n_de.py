# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.tools import format_date


class AccountMove(models.Model):
    _inherit = 'account.move'

    delivery_date = fields.Date(string='Delivery Date')

    l10n_de_template_data = fields.Binary(compute='_compute_l10n_de_template_data')
    l10n_de_document_title = fields.Char(compute='_compute_l10n_de_document_title')

    def _compute_l10n_de_template_data(self):
        for record in self:
            record.l10n_de_template_data = data = []
            if record.name:
                data.append((_("Invoice No."), record.name))
            if record.invoice_origin:
                data.append((_("Source"), record.invoice_origin))
            if record.name:
                data.append((_("Customer No."), record.partner_id.customer_id))
            if record.ref:
                data.append((_("Reference"), record.ref))
            if record.invoice_date:
                data.append((_("Invoice Date"), format_date(self.env, record.invoice_date)))
            if record.invoice_date_due:
                data.append((_("Due Date"), format_date(self.env, record.invoice_date_due)))
            if record.delivery_date:
                data.append((_("Delivery Date"), format_date(self.env, record.delivery_date)))

    def _compute_l10n_de_document_title(self):
        for record in self:
            record.l10n_de_document_title = ''
            if record.move_type == 'out_invoice':
                if record.state == 'posted':
                    record.l10n_de_document_title = _('Invoice')
                elif record.state == 'draft':
                    record.l10n_de_document_title = _('Draft Invoice')
                elif record.state == 'cancel':
                    record.l10n_de_document_title = _('Cancelled Invoice')
            elif record.move_type == 'out_refund':
                record.l10n_de_document_title = _('Credit Note')
            elif record.move_type == 'in_refund':
                record.l10n_de_document_title = _('Vendor Credit Note')
            elif record.move_type == 'in_invoice':
                record.l10n_de_document_title = _('Vendor Bill')
