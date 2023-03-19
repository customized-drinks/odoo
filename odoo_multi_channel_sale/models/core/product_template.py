# -*- coding: utf-8 -*-
##############################################################################
# Copyright (c) 2015-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>)
# See LICENSE file for full copyright and licensing details.
# License URL : <https://store.webkul.com/license.html/>
##############################################################################
from odoo import fields,models


class ProductTemplate(models.Model):
	_inherit = 'product.template'

	wk_parent_default_code = fields.Char('Parent Code')
	wk_length              = fields.Float('Length')
	width                  = fields.Float('Width')
	height                 = fields.Float('Height')

	dimensions_uom_id = fields.Many2one(
		comodel_name = 'uom.uom',
		string       = 'Default Unit of Measure',
		help         = "Default Unit of Measure used for dimension."
	)

	channel_mapping_ids = fields.One2many(
		string       = 'Mappings',
		comodel_name = 'channel.template.mappings',
		inverse_name = 'template_name',
		copy         = False
	)

	channel_category_ids = fields.One2many(
		string       = 'Extra Categories',
		comodel_name = 'extra.categories',
		inverse_name = 'product_id',
	)

	channel_ids = fields.Many2many(
		comodel_name = 'multi.channel.sale',
		relation     = 'product_tmp_channel_rel',
		column1      = 'product_tmpl_id',
		column2      = 'channel_id',
		string       = 'Channel(s)'
	)

	wk_product_id_type = fields.Selection(
		selection=[
			('wk_upc','UPC'),
			('wk_ean','EAN'),
			('wk_isbn','ISBN'),
		],
		string  = 'Product ID Type',
		default = 'wk_upc',
	)

	def _create_variant_ids(self):
		if 'channel' in self._context:
			return True
		return super(ProductTemplate, self)._create_variant_ids()

	def write(self, vals):
		for record in self:
			mapping_objs = record.channel_mapping_ids
			vals = self.env['multi.channel.sale']._core_pre_post_write(record, 'pre', 'template', mapping_objs, vals)
			mapping_objs.write({'need_sync': 'yes'})
			super(ProductTemplate, record).write(vals)
			self.env['multi.channel.sale']._core_pre_post_write(record, 'post', 'template', mapping_objs, vals)

	def unlink(self):
		for obj in self:
			self.env['multi.channel.sale'].unlink_feeds_mapping(obj.channel_mapping_ids, obj)
		return super(ProductTemplate, self).unlink()
