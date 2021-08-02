# -*- coding: utf-8 -*-
{
    'name': "Product Customer Code",
    'summary': "Allows to manage customer specific product code and product name",

    'description': """
        This module will introduce a new feature to manage customer specific product code and product name. those product code and product name will be displayed in description(name) field of product lines.
        This description(name) field is display on reports(quotation and invoice).
    """,
    'author': 'ErpMstar Solutions',
    'category': 'Sales',
    'version': '1.0',
    'depends': ['sale_management'],
    'data': [
        'security/ir.model.access.csv',
        'views/views.xml',
    ],
    'images': [
        'static/description/name_code_added.jpg',
    ],
    'installable': True,
    'website': '',
    'auto_install': False,
    'price': 20,
    'currency': 'EUR',
    'live_test_url': "https://www.youtube.com/watch?v=Z9xdFv7XenQ",
}
