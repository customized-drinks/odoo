from odoo import api, fields, models, tools


class DatevReport(models.Model):
    _name = 'datev.report'
    _auto = False

    id = fields.Many2one('account.move.line', string='Move Line Id')
    invoice_date = fields.Date(string='Invoice Date')
    delivery_date = fields.Date(string='Delivery Date')  # Leistungsdatum
    move_id = fields.Many2one('account.move', string='Invoice No.')
    price_subtotal = fields.Float('Subtotal')
    tax_base_amount = fields.Float('Tax Amount')
    price_total = fields.Float('Total')
    partner_id = fields.Many2one('res.partner', string='Customer')
    account_id = fields.Many2one('account.account', string='Account')

    def init(self):
        tools.drop_view_if_exists(self._cr, 'datev_report')
        self._cr.execute(""" CREATE VIEW datev_report AS (
            SELECT
                line.id as id,
                line.partner_id as partner_id,
                line.account_id as account_id,
                line.move_id as move_id,
                line.price_subtotal as price_subtotal,
                line.tax_base_amount as tax_base_amount,
                line.price_total as price_total,
                move.date as invoice_date,
                move.delivery_date as delivery_date
            FROM
                account_move_line as line
            LEFT JOIN
                account_move as move ON move.id = line.move_id
            GROUP BY
                line.id,
                line.move_id,
                line.account_id,
                line.partner_id,
                move.date,
                move.delivery_date 
        )""")
