# -*- coding: utf-8 -*-

from odoo import models, fields, api


class AccountMove(models.Model):
    _inherit = 'account.move'

    delivery_date = fields.Date(string='Delivery Date')

    def _find_mail_template(self, force_confirmation_template=False):
        template_id = False

        if self.state == 'draft':
            template_id = 26
        elif self.state == 'sent':
            template_id = 17
        elif self.state == 'sale':
            template_id = 18

        return template_id
