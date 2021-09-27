from odoo import api, fields, models, tools
from odoo.addons.web.controllers.main import CSVExport
from odoo.tools import pycompat
import io
from babel.numbers import format_currency
from babel.dates import format_date

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
                SUM(line.id) as id,
                line.move_id as move_id,
                line.move_id as debit_credit,
                line.account_id as account_id,
                line.partner_id as partner_id,
                SUM(line.quantity) as quantity,
                SUM(line.price_subtotal) as price_subtotal,
                SUM(line.tax_base_amount) as tax_base_amount,
                SUM(line.price_total) as price_total,
                SUM(tax.amount) as tax_rate,
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
            GROUP BY
                line.move_id, move.delivery_date, move.date, line.account_id, line.partner_id, currency.name, country.code, partner.vat, account.code
            ORDER BY
                line.move_id
                
        )""")


class CustomCSVExport(CSVExport):

    def format_data(self, data):
        data[2] = format_date(data[2], locale='de_DE')
        if data[3] is not '':
            # d = datetime.strptime(data[3], "%Y-%m-%d")
            data[3] = format_date(data[3], locale='de_DE')
        account = data[12]
        tax_rate = 0
        if '4301' in account or '4311' in account:
            tax_rate = 7
        elif '4402' in account or '4316' in account:
            tax_rate = 19
        data[6] = tax_rate
        data[7] = data[8] - data[5]
        data[5] = format_currency(data[5], 'EUR', locale='de_DE')[:-2]
        if data[7] != 0:
            data[7] = format_currency(data[7], 'EUR', locale='de_DE')[:-2]
        data[8] = format_currency(data[8], 'EUR', locale='de_DE')[:-2]
        invoice_number = data[1]
        debit_credit = 'H'
        if 'RINV' in invoice_number:
            debit_credit = 'S'
        data[10] = debit_credit
        data[12] = data[12][0:4]
        data[14] = data[14][2:]
        return data

    def from_data(self, fields, rows):
        fp = io.BytesIO()
        writer = pycompat.csv_writer(fp, quoting=1)

        writer.writerow(fields)

        for data in rows:
            row = []
            if fields[0] == 'Receivable Code':
                data = self.format_data(data)
            for d in data:
                # Spreadsheet apps tend to detect formulas on leading =, + and -
                if isinstance(d, str) and d.startswith(('=', '-', '+')):
                    d = "'" + d

                row.append(pycompat.to_text(d))
            writer.writerow(row)

        return fp.getvalue()
