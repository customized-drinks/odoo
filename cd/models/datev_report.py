from odoo import api, fields, models, tools


class DatevReport(models.Model):
    _name = 'datev.report'
    _auto = False

    id = fields.Many2one('account.move.line', string='Line ID')
    receivable_code = fields.Char(string='Receivable Code')
    invoice_date = fields.Date(string='Invoice Date')
    delivery_date = fields.Date(string='Delivery Date')  # Leistungsdatum
    move_id = fields.Many2one('account.move', string='Invoice No.')
    quantity = fields.Integer('Quantity')
    price_subtotal = fields.Float('Subtotal')
    tax_rate = fields.Integer('Tax Rate')
    tax_base_amount = fields.Float('Tax Amount')
    price_total = fields.Float('Total')
    currency_name = fields.Char('Currency')
    debit_credit = fields.Char('D/C')
    partner_id = fields.Many2one('res.partner', string='Customer')
    account_id = fields.Many2one('account.account', string='Account')
    country_code = fields.Char('Country')
    vat_id = fields.Char('VAT')

    def init(self):
        tools.drop_view_if_exists(self._cr, 'datev_report')
        self._cr.execute(""" CREATE VIEW datev_report AS (
            SELECT DISTINCT 
                move.date as invoice_date,
                move.delivery_date as delivery_date,
                line.id as id,
                line.move_id as move_id,
                line.move_id as debit_credit,
                line.account_id as account_id,
                line.partner_id as partner_id,
                line.quantity as quantity,
                line.price_subtotal as price_subtotal,
                line.tax_base_amount as tax_base_amount,
                line.price_total as price_total,
                tax.amount as tax_rate,
                currency.name as currency_name,
                country.code as country_code,
                partner.vat as vat_id,
                account.code as receivable_code
            FROM
                account_move_line as line
            LEFT JOIN
                account_move as move ON move.id = line.move_id
            LEFT JOIN
                account_tax as tax ON tax.id = line.tax_line_id
            LEFT JOIN
                res_currency as currency ON currency.id = line.currency_id
            LEFT JOIN
                res_partner as partner ON partner.id = move.partner_id
            LEFT JOIN
                    res_country as country ON country.id = partner.country_id
            LEFT JOIN
                ir_property as property ON (property.name = 'property_account_receivable_id' AND property.res_id = CONCAT('res.partner,', line.partner_id))
            LEFT JOIN
                account_account as account ON account.id = ALL(string_to_array(split_part(property.value_reference, ',', 2), ',')::smallint[])
            WHERE line.account_id IN (2510, 2511, 2512, 2513, 2514, 2515)
        )""")
