# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.


from odoo import models, fields, osv, api
from odoo.exceptions import Warning
from collections import namedtuple

from dateutil.relativedelta import relativedelta
from datetime import  datetime
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT, DEFAULT_SERVER_DATETIME_FORMAT
from odoo.tools.float_utils import float_is_zero, float_compare


class StockRule(models.Model):
    _inherit = 'stock.rule'
    
    def _get_stock_move_values(self, product_id, product_qty, product_uom, location_id, name, origin, company_id, values):
        result = super(StockRule, self)._get_stock_move_values(product_id, product_qty, product_uom, location_id, name, origin, company_id, values)
        result.update({
                'product_description':result.get('name',False),
            })
        return result

    
class SaleOrderLine(models.Model):
    
    _inherit = 'sale.order.line'
    

    def _prepare_procurement_values(self,group_id):
        res = super(SaleOrderLine,self)._prepare_procurement_values(group_id=group_id)
        res.update({
            'product_description':self.name,
            })
        return res

    product_description = fields.Char(string="Description")




class stock_move(models.Model):

    _inherit = 'stock.move'

    product_description = fields.Char(string="Description")

    def _prepare_procurement_values(self):
        res = super(stock_move,self)._prepare_procurement_values()
        res.update({'product_description' : self.product_description or ''})
        return res


class stock_move_line(models.Model):

    _inherit = 'stock.move.line'

    product_description = fields.Char(related='move_id.product_description', string="Description", store=True, related_sudo=False, readonly=False)


class purchase_order(models.Model):

    _inherit = 'purchase.order.line'


    def _create_stock_moves(self, picking):
       moves = self.env['stock.move']
       done = self.env['stock.move'].browse()
       for line in self:
           for val in line._prepare_stock_moves(picking):
               val.update({
                        'product_description':line.name,
                    })
                
               done += moves.create(val)
       return done

