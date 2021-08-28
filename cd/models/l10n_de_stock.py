from odoo import models, fields, api, _


class StockInventory(models.Model):
    _inherit = 'stock.inventory'

    l10n_de_document_title = fields.Char(compute='_compute_l10n_de_document_title')

    def _compute_l10n_de_document_title(self):
        for record in self:
            record.l10n_de_document_title = _('Delivery Note')
