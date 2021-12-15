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
            template_id = self.env['ir.model.data'].xmlid_to_res_id('cd.mail_quotation',
                                                                    raise_if_not_found=False)
        elif self.state == 'sent':
            template_id = self.env['ir.model.data'].xmlid_to_res_id('cd.mail_prepayment_invoice',
                                                                    raise_if_not_found=False)
        elif self.state == 'sale':
            template_id = self.env['ir.model.data'].xmlid_to_res_id('cd.mail_order',
                                                                    raise_if_not_found=False)

        return template_id

    def action_quotation_send(self):
        ''' Opens a wizard to compose an email, with relevant mail template loaded by default '''
        self.ensure_one()
        template_id = self._find_mail_template()
        lang = self.env.context.get('lang')
        template = self.env['mail.template'].browse(template_id)
        if template.lang:
            lang = template._render_lang(self.ids)[self.id]
        ctx = {
            'default_model': 'sale.order',
            'default_res_id': self.ids[0],
            'default_use_template': bool(template_id),
            'default_template_id': template_id,
            'default_composition_mode': 'comment',
            'mark_so_as_sent': False,
            'custom_layout': "mail.mail_notification_light",
            'proforma': self.env.context.get('proforma', False),
            'force_email': True,
            'model_description': self.with_context(lang=lang).type_name,
        }
        return {
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'mail.compose.message',
            'views': [(False, 'form')],
            'view_id': False,
            'target': 'new',
            'context': ctx,
        }

    def _prepare_invoice(self):
        self.ensure_one()
        invoice_vals = super(SaleOrder, self)._prepare_invoice()
        if self.effective_date:
            invoice_vals['delivery_date'] = self.effective_date
        return invoice_vals
