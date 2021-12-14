# -*- coding: utf-8 -*-

import logging

_logger = logging.getLogger(__name__)

from odoo import _, api, fields, models
from odoo import tools


class MailMail(models.Model):
    _inherit = 'mail.mail'


    def _send_prepare_values(self, partner=None):
        """Return a dictionary for specific email values, depending on a
        partner, or generic to the whole recipients given by mail.email_to.

            :param Model partner: specific recipient partner
        """
        self.ensure_one()
        body = self._send_prepare_body()
        body_alternative = tools.html2plaintext(body)
        if partner:
            email_to = [tools.formataddr((partner.name or partner.commercial_company_name or partner.email or 'Partner', partner.email or 'Partner'))]
        else:
            email_to = tools.email_split_and_format(self.email_to)
        res = {
            'body': body,
            'body_alternative': body_alternative,
            'email_to': email_to,
        }
        return res
