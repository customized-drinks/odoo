"""
Added fields in AccountFiscalPosition related to vat config and amazon fiscal position
configuration.
"""

# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models, _
from odoo.exceptions import UserError


class AccountFiscalPosition(models.Model):
    """
    Inherited this model for relating with vat configuration and added
    amazon configurations.
    @author: Maulik Barad on Date 15-Jan-2020.
    """
    _inherit = "account.fiscal.position"

    vat_config_id = fields.Many2one("vat.config.ept", "VAT Configuration", readonly=True)
    is_amazon_fpos = fields.Boolean(string="Is Amazon Fiscal Position", default=False)

    def unlink(self):
        """
        This Method if report is processed then raise UserError.
        """
        for fpos in self:
            if fpos.is_amazon_fpos:
                raise UserError(_('You cannot delete Amazon fiscal position. However, you can archive it.'))
        return super(AccountFiscalPosition, self).unlink()
