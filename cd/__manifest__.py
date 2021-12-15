# -*- coding: utf-8 -*-
{
    'name': "cd",

    'summary': """
        Short (1 phrase/line) summary of the module's purpose, used as
        subtitle on modules listing or apps.openerp.com""",

    'description': """
        Long description of module's purpose
    """,

    'author': "My Company",
    'website': "http://www.yourcompany.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/14.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Uncategorized',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['base', 'sale', 'account', 'stock', 'l10n_de', 'l10n_de_sale', 'l10n_de_stock'],

    # always loaded
    'data': [
        'views/assets.xml',
        'views/sale.xml',
        'views/account.xml',
        'views/stock.xml',
        'views/templates/contact.xml',
        'views/templates/external_layout_din5008.xml',
        'views/templates/mail_notification_light_inherit.xml',
        'views/templates/report_delivery_document.xml',
        'views/templates/report_invoice_document.xml',
        'views/templates/report_picking.xml',
        'views/templates/report_saleorder_document.xml',
        'views/templates/stock_report_delivery_aggregated_move_lines_inherit.xml',
        'views/templates/stock_report_delivery_package_section_line.xml',
        'views/templates/mail_quotation.xml',
        'views/templates/mail_quotation_du.xml',
        'views/templates/mail_prepayment_invoice.xml',
        'views/templates/mail_prepayment_invoice_du.xml',
        'views/templates/mail_order.xml',
        'views/templates/mail_order_du.xml',
        'views/templates/mail_invoice.xml',
        'views/templates/mail_invoice_du.xml',
        'views/templates/mail_delivery.xml',
        'views/templates/mail_delivery_du.xml',
        'views/templates/mail_refund.xml',
        'views/templates/mail_refund_du.xml',
        'security/ir.model.access.csv',
    ]
}
