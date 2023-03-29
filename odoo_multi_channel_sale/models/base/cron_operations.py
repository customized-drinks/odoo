# -*- coding: utf-8 -*-
##############################################################################
# Copyright (c) 2015-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>)
# See LICENSE file for full copyright and licensing details.
# License URL : <https://store.webkul.com/license.html/>
##############################################################################

from odoo import models, api, _

class MultiChannelSale(models.Model):
	_inherit = 'multi.channel.sale'

	@api.model
	def cron_feed_evaluation(self):
		for object_model in  ["product.feed","order.feed","category.feed","partner.feed"]:
			records = self.env[object_model].search([
				("state","!=","done"),
				("channel_id.state","=","validate")
			], limit=500)
			records.with_context(channel_id=records.mapped("channel_id")).import_items()
		return True

	@api.model
	def cron_import_all(self, model):
		config_ids = self.env['multi.channel.sale'].search([("state","=","validate")])
		for config_id in config_ids:
			if model == "order" and config_id.import_order_cron:
				if hasattr(config_id, "{}_import_order_cron".format(config_id.channel)):
					getattr(config_id,"{}_import_order_cron".format(config_id.channel))()
				else:
					_logger.warn('Error in use of MultiChannelSale class : use of (%r)_import_order_cron function to import orders from channel to odoo',config_id.channel)
			elif model == "product" and config_id.import_product_cron:
				if hasattr(config_id, "{}_import_product_cron".format(config_id.channel)):
					getattr(config_id,"{}_import_product_cron".format(config_id.channel))()
				else:
					_logger.warn('Error in use of MultiChannelSale class : use of (%r)_import_product_cron function to import orders from channel to odoo',config_id.channel)
			elif model == "partner" and config_id.import_partner_cron:
				if hasattr(config_id, "{}_import_partner_cron".format(config_id.channel)):
					getattr(config_id,"{}_import_partner_cron".format(config_id.channel))()
				else:
					_logger.warn('Error in use of MultiChannelSale class : use of (%r)_import_partner_cron function to import orders from channel to odoo',config_id.channel)
			elif model == "category" and config_id.import_category_cron:
				if hasattr(config_id, "{}_import_category_cron".format(config_id.channel)):
					getattr(config_id,"{}_import_category_cron".format(config_id.channel))()
				else:
					_logger.warn('Error in use of MultiChannelSale class : use of (%r)_import_category_cron function to import orders from channel to odoo',config_id.channel)
		return True

	@api.model
	def set_channel_cron(self,ref_name='',active=False):
		try:
			cron_obj= self.env.ref(ref_name,False)
			if cron_obj:
				cron_obj.sudo().write(dict(active=active))
		except Exception as e:
			_logger.error("#1SetCronError  \n %r"%(e))
			raise Warning(e)
