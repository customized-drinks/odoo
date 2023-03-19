# -*- coding: utf-8 -*-
##############################################################################
# Copyright (c) 2015-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>)
# See LICENSE file for full copyright and licensing details.
# License URL : <https://store.webkul.com/license.html/>
##############################################################################
import binascii
import logging
import requests
from dateutil import parser
from odoo import fields, models, api, _
from ...tools import ReverseDict
_logger = logging.getLogger(__name__)

HelpImportOrderDate  = _(
"""A date used for selecting orders created after (or at) a specified time."""
)

HelpUpdateOrderDate = _(
"""
	A date used for selecting orders that were last updated after (or at) a specified time.
	 An update is defined as any change in order status,includes updates made by the seller.
"""
)
DefaultStore = _("""***While using multi store***\n
Select the default store/parent store
from where the order and partner will imported for this child store.
""")

STATE = [
	('draft', 'Draft'),
	('validate', 'Validate'),
	('error', 'Error')
]
DEBUG = [
	('enable', 'Enable'),
	('disable', 'Disable')
]
ENVIRONMENT = [
	('production', 'Production Server'),
	('sandbox', 'Testing(Sandbox) Server)')
]
FEED = [
	('all', 'For All Models'),
	('order', 'For Order Only'),
]

MAPPINGMODEL = {
	'product.product' : 'channel.product.mappings',
	'product.template': 'channel.template.mappings',
	'res.partner'     : 'channel.partner.mappings',
	'product.category': 'channel.category.mappings',
	'sale.order'      : 'channel.order.mappings',
}
TaxType = [
	('include','Include In Price'),
	('exclude','Exclude In Price')
]

METAMAP = {
	'product.category': {
		'mapping'       : 'channel.category.mappings',
		'local_field' 	: 'odoo_category_id',
		'channel_field'	: 'store_category_id',
		'feed'        	: 'category.feed'
	},
	'product.template': {
		'mapping'       : 'channel.template.mappings',
		'local_field' 	: 'odoo_template_id',
		'channel_field'	: 'store_product_id',
		'feed'        	: 'product.feed'
	},
	'product.product': {
		'mapping'       : 'channel.product.mappings',
		'local_field' 	: 'erp_product_id',
		'channel_field'	: 'store_variant_id'
	}
}



class MultiChannelSale(models.Model):
	_name = 'multi.channel.sale'
	_description = 'Multi Channel Sale'
	_inherit = ['mail.thread', 'mail.activity.mixin']

	import_order_cron = fields.Boolean("Import Orders")
	import_product_cron = fields.Boolean("Import Products")
	import_partner_cron = fields.Boolean("Import Customers")
	import_category_cron = fields.Boolean("Import Categories")

	channel_stock_action = fields.Selection([
		('qoh', 'Quantity on hand'),
		('fq', 'Forecast Quantity')
		],
		default='qoh',
		string='Stock Management',
		help="Manage Stock")

	@api.model
	def create(self, vals):
		res = super().create(vals)
		if 'install_mode' in self._context or 'create_order_states' in self._context:
			res._on_change_channel()
		channels = self.get_core_feature_compatible_channels()
		if res.channel in channels:
			res.use_core_feature = True
		return res

	url     = fields.Char("URL")
	email   = fields.Char(string='Api User')
	api_key = fields.Char("Password")

	def test_connection(self):
		self.ensure_one()
		if hasattr(self, 'connect_%s' % self.channel):
			res,msg = getattr(self, 'connect_%s' % self.channel)()
			self.state = 'validate' if res else 'error'
			return self.display_message(msg)
		elif hasattr(self, 'test_%s_connection' % self.channel):
			_logger.warn(
				'Error in use of MultiChannelSale class: '
				'use of test_connection function to establish connection to Channel.'
			)
			return getattr(self, 'test_%s_connection' % self.channel)()
		else:
			return self.display_message('Connection protocol missing.')

	@api.onchange('channel')
	def _on_change_channel(self):
		if self.channel:
			if self.order_state_ids:
				rec = self.env['channel.order.states'].search([('channel_id','=',self._origin.id),('channel_name','=',self.channel)])

				if rec:
					self.order_state_ids = [(6,0,rec.ids)]
				else:
					self.order_state_ids = [(5,0,0)]
					if hasattr(self,'%s_default_order_state'%self.channel):
						"""
						Add default values to order state ids
						@field channel_state: state of the channel
						@field default_order_state: True or False
						@field odoo_create_invoice: True or False
						@field odoo_ship_order: True or False
						@field odoo_order_state: draft or shipped or done etc.
						@field odoo_set_invoice_state: paid or open
						@return: A list dictionarys of the default values
						"""
						values = getattr(self,'%s_default_order_state'%self.channel)()
						rec_val = []
						for rec in values:
							rec_val.append((0,0,rec))
						self.order_state_ids = rec_val
			else:
				if hasattr(self,'%s_default_order_state'%self.channel):
					"""
					Add default values to order state ids
					@field channel_state: state of the channel
					@field default_order_state: True or False
					@field odoo_create_invoice: True or False
					@field odoo_ship_order: True or False
					@field odoo_order_state: draft or shipped or done etc.
					@field odoo_set_invoice_state: paid or open
					@return: A list dictionarys of the default values
					"""
					values = getattr(self,'%s_default_order_state'%self.channel)()
					rec_val = []
					for rec in values:
						rec_val.append((0,0,rec))
					self.order_state_ids = rec_val




	def set_to_draft(self):
		self.state = 'draft'

	def open_mapping_view(self):
		self.ensure_one()
		res_model = self._context.get('mapping_model')
		mapping_ids = self.env[res_model].search([('channel_id', '=', self.id)]).ids
		return {
			'name': ('Mapping'),
			'type': 'ir.actions.act_window',
			'view_mode': 'tree,form',
			'res_model': res_model,
			'view_id': False,
			'domain': [('id', 'in', mapping_ids)],
			'target': 'current',
		}

	def open_record_view(self):
		self.ensure_one()
		res_model = self._context.get('mapping_model')
		domain = [('channel_id', '=', self.id)]
		erp_ids = self.env[res_model].search(domain).mapped(self._context.get('odoo_mapping_field'))
		erp_model = ReverseDict(MAPPINGMODEL).get(res_model)
		domain = [('id', 'in', erp_ids)]
		if erp_model == 'res.partner':
			domain.append(('parent_id', '=', False))
		return {
			'name': ('Record'),
			'type': 'ir.actions.act_window',
			'view_mode': 'tree,form',
			'res_model': erp_model,
			'view_id': False,
			'domain': domain,
			'target': 'current',
		}

	def _get_count(self):
		for rec in self:
			domain = [('channel_id', '=', rec.id)]
			rec.channel_products   = self.env['channel.template.mappings'].search_count(domain)
			rec.channel_categories = self.env['channel.category.mappings'].search_count(domain)
			rec.channel_orders     = self.env['channel.order.mappings'].search_count(domain)
			domain.append(('odoo_partner.parent_id', '=', False))
			rec.channel_customers  = self.env['channel.partner.mappings'].search_count(domain)

	active = fields.Boolean(default=True)
	color_index = fields.Integer(string='Color Index')

	def set_info_urls(self):
		for instance in self:
			url_info = self.get_info_urls().get(instance.channel,{})
			instance.blog_url = url_info.get('blog','https://webkul.com/blog/odoo-multi-channel-sale/')
			instance.store_url = url_info.get('store','https://store.webkul.com/Odoo-Multi-Channel-Sale.html')

	use_core_feature = fields.Boolean(readonly=True)
	channel = fields.Selection(selection='get_channel', required=True, inverse=set_info_urls)
	name = fields.Char('Name', required=True)
	state = fields.Selection(STATE, default='draft')
	color = fields.Char(default='#000000')
	image = fields.Image(max_width=256, max_height=256)
	blog_url = fields.Char()
	store_url = fields.Char()
	debug = fields.Selection(DEBUG, default='enable', required=True)

	environment = fields.Selection(
		selection=ENVIRONMENT,
		string='Environment',
		default='sandbox',
		help="""Set environment to  production while using live credentials.""",
	)
	is_child_store = fields.Boolean(string = 'Is Child-Store')
	default_store_id =fields.Many2one(
		comodel_name = 'multi.channel.sale',
		string='Parent Store',
		help = DefaultStore,
	)
	sku_sequence_id = fields.Many2one(
		comodel_name='ir.sequence',
		string='Sequence For SKU',
		help="""Default sequence used as sku/default code for product(in case product not have sku/default code).""",
	)
	language_id = fields.Many2one(
		comodel_name='res.lang',
		default = lambda self: self.env['res.lang'].search([], limit=1),
		help="""The language used over e-commerce store/marketplace.""",
	)

	pricelist_id = fields.Many2one('channel.pricelist.mappings','Pricelist Mapping')

	pricelist_name = fields.Many2one(
		comodel_name='product.pricelist',
		string='Default Pricelist',
		default=lambda self: self.env['product.pricelist'].search([], limit=1),
		help="""Select the same currency of pricelist used  over e-commerce store/marketplace.""",
	)
	default_category_id = fields.Many2one(
		comodel_name='product.category',
		string='Category',
		default=lambda self: self.env['product.category'].search([], limit=1),
		help="""Default category used as product internal category for imported products.""",
	)
	channel_default_product_categ_id = fields.Many2one(
		comodel_name = 'channel.category.mappings',
		string = 'Channel Category'
	)
	default_tax_type = fields.Selection(
		selection = TaxType,
		string = 'Tax Type',
		default = 'exclude',
		required = 1
	)
	delivery_product_id = fields.Many2one(
		comodel_name='product.product',
		string='Delivery Product',
		default=lambda self: self.env.ref('odoo_multi_channel_sale.delivery_product').id,
		domain=[('type', '=', 'service')],
		help="""Delivery product used in sale order line.""",
	)
	discount_product_id = fields.Many2one(
		comodel_name='product.product',
		string='Discount Product',
		default=lambda self: self.env.ref('odoo_multi_channel_sale.discount_product').id,
		domain=[('type', '=', 'service')],
		help="""Discount product used in sale order line.""",
	)
	warehouse_id = fields.Many2one(
		comodel_name='stock.warehouse',
		string='Warehouse',
		default=lambda self: self.env['stock.warehouse'].search([], limit=1),
		help='Warehouse used for imported product.',
	)
	location_id = fields.Many2one(
		related='warehouse_id.lot_stock_id',
		string='Stock Location',
		help='Stock Location used for imported product.',
	)
	company_id = fields.Many2one(
		related='warehouse_id.company_id',
		string='Company Id',
	)
	crm_team_id = fields.Many2one(
		comodel_name='crm.team',
		string='Sales Team',
		default=lambda self: self.env['crm.team'].search([], limit=1),
		help='Sales Team used for imported order.',
	)
	payment_term_id = fields.Many2one(
		'account.payment.term',
		string="Ecommerce Payment Term",
		help="""Default Payment Term Used In Sale Order.""")
	sales_person_id = fields.Many2one(
		'res.users',
		string="Sales Person",
		help="""Default Sales Person Used In Sale Order.""")
	order_state_ids = fields.One2many(
		comodel_name='channel.order.states',
		inverse_name='channel_id',
		string='Default Odoo Order States',
		help='Imported order will process in odoo on basis of these state mappings.',
		copy = True,
	)

	feed = fields.Selection(FEED,default='all', required=True)

	auto_evaluate_feed = fields.Boolean(
		string='Auto Evaluate Feed',
		default=1,
		help='Auto Evaluate Feed Just After Import.',
	)
	auto_sync_stock = fields.Boolean(
		string='Auto Sync Stock',
		help='Enable this for real time stock sync over channel.',
	)

	sync_cancel = fields.Boolean(
		string='Cancel Status',
		help='Enable for cancel status at E-commerce',
	)
	sync_invoice = fields.Boolean(
		string='Invoice Status',
		help='Enable for update invoice status at E-commerce',
	)
	sync_shipment = fields.Boolean(
		string='Shipment Status',
		help='Enable for update shipment status at E-commerce',
	)

	import_order_date =  fields.Datetime(
		string='Order Imported',
		help = HelpImportOrderDate
	)

	update_order_date =  fields.Datetime(
		string='Order Updated',
		help = HelpUpdateOrderDate
	)

	import_product_date =  fields.Datetime(string='Product Imported')
	update_product_price = fields.Boolean(string='Update Price')
	update_product_stock = fields.Boolean(string='Update Stock')
	update_product_image = fields.Boolean(string='Update Image')
	update_product_date =  fields.Datetime(string='Product Updated')

	import_customer_date =  fields.Datetime(string='Customer Imported')
	update_customer_date =  fields.Datetime(string='Customer Updated')
	use_api_limit = fields.Boolean(string = 'Use API Limit', default = True)
	api_record_limit = fields.Integer(string = 'API Record Limit', default = 100)

	channel_products   = fields.Integer(compute='_get_count')
	channel_categories = fields.Integer(compute='_get_count')
	channel_orders     = fields.Integer(compute='_get_count')
	channel_customers  = fields.Integer(compute='_get_count')

	@api.constrains('api_record_limit')
	def check_api_record_limit(self):
		if self.api_record_limit<=0:
			raise Warning("""The api record limit should be postive.""")

	@api.model
	def set_channel_date(self, operation = 'import',record = 'product'):
		current_date = fields.Datetime.now()
		if operation == 'import':
			if record == 'order':
				self.import_order_date = current_date
			elif record == 'product':
				self.import_product_date = current_date
			elif record == 'customer':
				self.import_customer_date = current_date
		else:
			if record == 'order':
				self.update_order_date = current_date
			elif record == 'product':
				self.update_product_date = current_date
			elif record == 'customer':
				self.update_customer_date = current_date
		return True

	def toggle_enviroment_value(self):
		production = self.filtered(
			lambda channel: channel.environment == 'production')
		production.write({'environment': 'sandbox'})
		(self - production).write({'environment': 'production'})
		return True

	def toggle_debug_value(self):
		enable = self.filtered(lambda channel: channel.debug == 'enable')
		enable.write({'debug': 'disable'})
		(self - enable).write({'debug': 'enable'})
		return True

	def toggle_active_value(self):
		for record in self:
			record.write({'active': not record.active})
		return True

	@api.model
	def om_format_date(self, date_string):
		om_date_time = None
		message = ''
		try:
			if date_string:
				om_date_time = parser.parse(date_string).astimezone().replace(tzinfo=None)
		except Exception as e:
			message += '%r'%e
		return dict(
			message = message,
			om_date_time = om_date_time
		)

	@api.model
	def create_model_objects(self, model_name, vals, **kwargs):
		"""
			model_name:'res.partner'
			vals:[{'name':'demo','type':'customer'},{'name':'portal':'type':'contact'}]
		"""
		message = ''
		data = None
		try:
			ObjModel = self.env[model_name]
			data = self.env[model_name]
			for val in vals:
				if kwargs.get('extra_val'):
					val.update( kwargs.get('extra_val'))
				match =False
				if val.get('store_id'):
					obj = ObjModel.search([('store_id', '=', val.get('store_id'))], limit= 1)
					if obj:
						obj.write(val)
						data += obj
						match = True
				if not match:
					data += ObjModel.create(val)
		except Exception as e:
			_logger.error("#1CreateModelObject Error  \n %r"%(e))
			message += "%r"%(e)
		return dict(
			data = data,
			message = message,
		)

	@api.model
	def create_product(self, name, _type='service', vals=None):
		vals = vals or {}
		vals['name'] = name
		vals['type'] = _type
		return self.env['product.product'].create(vals)

	@api.model
	def create_tax(self, name, amount, amount_type='percent', price_include=False):
		raise NotImplementedError

	@api.model
	def _create_sync(self, vals):
		if self.debug=='enable':
			nvals = vals.copy()
			channel_vals = self.get_channel_vals()
			nvals.update(channel_vals)
			return self.env['channel.synchronization'].create(nvals)
		return self.env['channel.synchronization']

	@api.model
	def default_multi_channel_values(self):
		return self.env['res.config.settings'].sudo().get_values()

	def open_website_url(self, url, name='Open Website URL'):
		self.ensure_one()
		return {
			'name': name,
			'url': url,
			'type': 'ir.actions.act_url',
			'target': 'new',
		}

	@staticmethod
	def read_website_image_url(image_url):
		data = None
		try:
			res = requests.get(image_url)
			if res.status_code == 200:
				data = binascii.b2a_base64((res.content))
		except Exception as e:
			_logger.error("#1ReadImageUrlError  \n %r"%(e))
		return data

	@api.model
	def set_order_by_status(self,channel_id,store_id,
			status,order_state_ids,default_order_state,
			payment_method = None):
		result = dict(
			order_match  = None,
			message = ''
		)
		order_match = channel_id.match_order_mappings(store_id)
		order_state_ids = order_state_ids.filtered(
			lambda state: state.channel_state == status)
		state = order_state_ids[0] if order_state_ids else default_order_state
		if order_match  and order_match.order_name.state =='draft' and (
				state.odoo_create_invoice or state.odoo_ship_order):
			result['message'] += self.env['multi.channel.skeleton']._SetOdooOrderState(
				order_match.order_name, channel_id,  status, payment_method
			)
			result['order_match']=order_match
		return result

	def unlink_feeds_mapping(self, channel_mapping_objs, model_obj):
		model = model_obj._name
		model_dict = METAMAP.get(model)
		mapping_model = model_dict.get('mapping')
		feed_model = model_dict.get('feed')
		for channel_mapping_obj in channel_mapping_objs:
			channel_store_id = eval('channel_mapping_obj.{}'.format(model_dict.get('channel_field')))
			feed_objs = self.env[feed_model].search([
				('store_id', '=', channel_store_id)
			])
			for feed_obj in feed_objs:
				feed_obj.unlink()

	def _core_pre_post_write(self, obj, opr, core_model, mapping_objs, vals):
		_channel_ids = self.env['multi.channel.sale']

		for mapping_obj in mapping_objs:
			channel_id = mapping_obj.channel_id
			_channel_ids |= channel_id
			if hasattr(channel_id,'%s_mapped_%s_%s_write'%(channel_id.channel, opr, core_model)):
				vals.update(getattr(
					channel_id,'%s_mapped_%s_%s_write'%(channel_id.channel, opr, core_model)
				)(obj, mapping_obj, vals) or vals)

		channel_ids = self.search([
				('state','=','validate'),
				('id', 'not in', _channel_ids.ids)
		])
		for channel_id in channel_ids:
			if hasattr(channel_id,'%s_%s_%s_write'%(channel_id.channel, opr, core_model)):
				vals.update(getattr(
					channel_id,'%s_%s_%s_write'%(channel_id.channel, opr, core_model)
				)(obj, vals) or vals)
		return vals
