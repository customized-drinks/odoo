# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.
{
    'name': 'Sale/Purchase order Line Description to Pickings(Shipment/Delivery)',
    'version': '14.0.0.1',
    'category': 'Warehouse',
    'summary': 'Apps Sale order Line Description in picking purchase order Line Description in picking Sale Line Description in picking purchase Line Description in picking Sale order Line Description in delivery purchase order Line Description in receipt line description',
    'description': """
      odoo Sale Line Description to Picking purchase Line Description to Pickings
      odoo purchases Line Description to Pickings Sales Line Description to Picking
      odoo Sale order Line Description to Picking purchase order Line Description to Pickings
      odoo Sales order Line Description to Picking Sale Line Description to delivery order purchase Line Description to incoming shipment
      odoo picking description from sales picking description from purchase  
      odoo picking description from sales order picking description from purchase order
	   odoo Description on Picking report Description on delivery order Description on delivery order report
     odoo Description on delivery report Description on shipment shipping description  Sale Description to Picking
    odoo purchase Description to Pickings Sales Description to Picking purchases Description to Pickings
    odoo purchase line Description on picking purchase order line Description on picking
    odoo sale order line Description on picking sale order line Description on picking
    odoo SO line Description on picking SO Description on picking PO line Description on picking SO Description on picking
This odoo apps helps automatically pass description of sales order line and purchase order line to picking-receipt/delivery order. 
By default on Odoo there is no product description available on incoming shipment and delivery order while received products and deliver products. 
And its very important to see the goods/product description on picking orders when received and delivered goods. 
This odoo module make this possible, so when picking created from the sales or purchase , sales order line and purchase order line description is automatically pass on each operation lines of purchase receipt and delivery orders. 
It also helps to print those description on picking operation reports.
	
     
""",
    'author': 'BrowseInfo',
    'website': 'https://www.browseinfo.in',
    'depends': ['base','stock','sale_management','purchase'],
    'data': [
        'views/stock_view.xml',
    ],
    'demo': [],
    "price": 19,
    "currency": 'EUR',
    'js': [],
    'qweb': [],
    'installable': True,
    'auto_install': False,
    "live_test_url":'https://youtu.be/TXj1zsHjwac',
    "images":['static/description/Banner.png'],
}
