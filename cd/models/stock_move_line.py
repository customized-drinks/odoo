# -*- coding: utf-8 -*-

from odoo import models, fields, api


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    def _get_aggregated_product_quantities(self, **kwargs):
        """ Returns a dictionary of products (key = id+name+description+uom) and corresponding values of interest.

        Allows aggregation of data across separate move lines for the same product. This is expected to be useful
        in things such as delivery reports. Dict key is made as a combination of values we expect to want to group
        the products by (i.e. so data is not lost).

        returns: dictionary {product_id+name+lot+description+uom: {product, name, description, lot, qty_done, product_uom}, ...}
        """
        aggregated_move_lines = {}
        for move_line in self:
            name = move_line.product_id.display_name
            description = move_line.move_id.description_picking
            if description == name or description == move_line.product_id.name:
                description = False
            uom = move_line.product_uom_id
            lot = move_line.lot_id
            if lot.name:
                lot = lot.name
            else:
                lot = ""
            line_key = str(move_line.product_id.id) + "_" + str(name) + (str(description) or "") + str(lot) + "_uom_" + str(uom.id)

            if line_key not in aggregated_move_lines:
                aggregated_move_lines[line_key] = {'name': name,
                                                   'description': description,
                                                   'qty_done': int(move_line.qty_done),
                                                   'product_uom': uom.name,
                                                   'lot': lot,
                                                   'product': move_line.product_id}
            else:
                aggregated_move_lines[line_key]['qty_done'] += int(move_line.qty_done)
        return aggregated_move_lines
