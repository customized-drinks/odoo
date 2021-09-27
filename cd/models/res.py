# -*- coding: utf-8 -*-

from odoo import models, fields, api


class ResPartner(models.Model):
    _inherit = 'res.partner'

    customer_id = fields.Char(string='Customer ID', readonly=False, index=True)
    name_2 = fields.Char(string='Name 2', readonly=False)
    name_3 = fields.Char(string='Name 3', readonly=False)

    @api.model
    def create(self, vals):
        vals['customer_id'] = self.env['ir.sequence'].next_by_code('res.partner')
        return super(ResPartner, self).create(vals)

