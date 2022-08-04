# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

"""
REMOVE THIS MODEL AND FIELDS FROM ODOO VERSION 15
DUE TO EXISTING CUSTOMER NOT UPGRADE MODULE THAT'S WHY KEEP IN ODOO VERSION 14
Added class and methods to import amazon product in odoo.
"""

from odoo import models, fields


class AmazonProductImportSelectionWizard(models.TransientModel):
    """
    Added class to import amazon product and also added methods to import and  read csv file,
    create amazon listing.
    """
    _name = "amazon.import.product.wizard"
    _description = 'amazon.import.product.wizard'

    seller_id = fields.Many2one('amazon.seller.ept', string='Seller',
                                help="Select Seller Account to associate with this Instance")
    file_name = fields.Char(string='Name')
    choose_file = fields.Binary(string="Select File")
    delimiter = fields.Selection([('tab', 'Tab'), ('semicolon', 'Semicolon'), ('comma', 'Comma')],
                                 string="Separator", default='comma')
