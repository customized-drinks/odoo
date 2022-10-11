# -*- coding: utf-8 -*-
##############################################################################
#
# Copyright 2019 EquickERP
#
##############################################################################

{
    'name': "Email Bcc",
    'version': '14.0.1.0',
    'category': 'Discuss',
    'author': 'Equick ERP',
    'summary': """Email Bcc | Bcc on Mail | Send mail in bcc | Bcc Email | Mail with Bcc | Compose mail with Bcc | Allow Bcc in Wizard""" ,
    'description': """
        Email Bcc.
        * Allow users to send the emails as Bcc to configurable email addresses.
        * Dynamic Configuration for any models and Mail compose Wizard.
        * Mail template wise configuration.
    """,
    'license': 'OPL-1',
    'depends': ['base', 'mail', 'account'],
    'price': 12,
    'currency': 'EUR',
    'website': "",
    'data'   : [
        'views/mail_view.xml',
    ],
    'images': ['static/description/main_screenshot.png'],
    'installable': True,
    'auto_install': False,
    'application': False,
}

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: