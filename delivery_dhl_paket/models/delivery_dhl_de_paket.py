# -*- coding: utf-8 -*-
##############################################################################
#
#    ODOO, Open Source Management Solution
#    Copyright (C) 2016 - 2020 Steigend IT Solutions (Omal Bastin)
#    Copyright (C) 2020 - Today O4ODOO (Omal Bastin)
#    For more details, check COPYRIGHT and LICENSE files
#
##############################################################################
import time

from .dhl_de_paket_client import DHLPaketProvider

import base64
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import ustr


class StockPicking(models.Model):
    _inherit = 'stock.picking'
    dhl_paket_label_url = fields.Char('Label URL')
    
#     @api.multi
    def print_dhl_paket_label(self):
        self.ensure_one()
        return {
            'url': self.dhl_paket_label_url,
            'type': 'ir.actions.act_url'
        }


class ProviderDhlDe(models.Model):
    _inherit = 'delivery.carrier'

    @api.depends('dhl_de_paket_developer_id', 'dhl_de_paket_portal_password', 
                 'dhl_de_paket_test_user', 'dhl_de_paket_test_signature',
                 'dhl_de_paket_application_id', 'dhl_de_paket_application_token', 'prod_environment')
    def _compute_username_password(self):
        for record in self:
            if not record.prod_environment:
                record.dhl_de_paket_username = record.dhl_de_paket_developer_id
                record.dhl_de_paket_password = record.dhl_de_paket_portal_password
                record.dhl_de_paket_user = record.dhl_de_paket_test_user
                record.dhl_de_paket_signature = record.dhl_de_paket_test_signature
            else:
                record.dhl_de_paket_username = record.dhl_de_paket_application_id
                record.dhl_de_paket_password = record.dhl_de_paket_application_token
                record.dhl_de_paket_user = record.dhl_de_paket_intraship_user
                record.dhl_de_paket_signature = record.dhl_de_paket_intraship_signature

    delivery_type = fields.Selection(selection_add=[('dhl_de_paket', "DHL DE Paket(Business Customer API)")],
                                     ondelete={'dhl_de_paket': lambda recs: recs.write({
                                         'delivery_type': 'fixed', 'fixed_price': 0, })}
                                     )
    dhl_de_paket_developer_id = fields.Char(string="Developer ID", groups="base.group_system", help="Developer ID",)
    dhl_de_paket_portal_password = fields.Char(string="Password", groups="base.group_system", help="Portal Password",)
    dhl_de_paket_test_user = fields.Char(string="Test User", groups="base.group_system",
                                         help="Test User", default="2222222222_01")
    dhl_de_paket_test_signature = fields.Char(string="Test Signature", groups="base.group_system",
                                              help="Test Signature", default="pass")
    dhl_de_paket_application_id = fields.Char(string="Application ID", groups="base.group_system",
                                              help="Application ID")
    dhl_de_paket_application_token = fields.Char(string="Application Token", groups="base.group_system",
                                                 help="Application Token")
    dhl_de_paket_intraship_user = fields.Char(string="User", groups="base.group_system",
                                              help="Username")
    dhl_de_paket_intraship_signature = fields.Char(string="Signature",
                                                   groups="base.group_system", help="Password")
    dhl_de_paket_username = fields.Char(compute=_compute_username_password, string="Username",
                                        groups="base.group_system", store=True)
    dhl_de_paket_password = fields.Char(compute=_compute_username_password, string="Password",
                                        groups="base.group_system", store=True)
    dhl_de_paket_user = fields.Char(compute=_compute_username_password, string="User",
                                    groups="base.group_system", store=True)
    dhl_de_paket_signature = fields.Char(compute=_compute_username_password, string="Signature",
                                         groups="base.group_system", store=True)
    dhl_de_paket_account_number = fields.Char(string="DHL EKP number", groups="base.group_system",
                                              help="10 digit account number")
    dhl_de_paket_partner_no = fields.Char(string="DHL Partner Number", groups="base.group_system",
                                          default="01")
    dhl_de_paket_dimension_unit = fields.Selection([('IN', 'Inches'),
                                                   ('CM', 'Centimeters')],
                                                   default='CM', string='Package Dimension Unit')
    dhl_de_paket_package_weight_unit = fields.Selection([('LB', 'Pounds'), ('KG', 'Kilograms')],
                                                        default='KG', string="Package Weight Unit")
    dhl_de_paket_default_packaging_id = fields.Many2one('product.packaging', string='Default Packaging Type',
                                                        # default=lambda self: self.env.ref('delivery_dhl_paket.dhl_de_paket_packaging')
                                                        )
    # dhl_de_paket_package_type = fields.Selection([('PK', 'Paket')], default='PK', string='Package Type')
    dhl_de_paket_product_code = fields.Selection([
        ('V01PAK', 'DHL PAKET'),
        # ('V01PRIO', 'DHL PAKET Prio( Germany )'),
        ('V53WPAK', 'DHL PAKET International'),
        ('V54EPAK', 'DHL Europaket'),
        ('V55PAK', 'DHL Paket Connect'),
        ('V62WP', 'Warenpost'),
        ('V66WPI', 'Warenpost International'),
        # ('V06PAK', 'DHL PAKET Taggleich( Germany )'),
        # ('V06TG', 'Kurier Taggleich( Germany )'),
        # ('V06WZ', 'Kurier Wunschzeit( Germany )'),
        # ('V86PARCEL', 'DHL PAKET( Austria )'),
        # ('V87PARCEL', 'DHL PAKET Connect( Austria )'),
        # ('V82PARCEL', 'DHL PAKET International( Austria )'),
        ], default='V01PAK', string='Product')

    dhl_de_paket_endorsement_type = fields.Selection([('IMMEDIATE', 'IMMEDIATE'),
                                                      ('AFTER_DEADLINE', 'AFTER_DEADLINE')], 'Endorsement Type',
                                                     help="It defines the handling of parcels that cannot be delivered."
                                                          " The definition of undeliverability is country-specific and "
                                                          "depends on the regulations of the postal company of the "
                                                          "receiving country. Usually, if parcels cannot be delivered "
                                                          "at first try, recipients receive a notification card and can"
                                                          " pick up their shipment at a local postal office. After the "
                                                          "storage period has expired, the shipment will be handled "
                                                          "according to your choosen endorsement option. Shipments that"
                                                          " cannot be delivered due to address problems or active "
                                                          "refusal will be either returned immediately or treated "
                                                          "as abandoned")
    dhl_de_paket_package_height = fields.Integer(string="Package Height(Deprecated)")#Deprecated use dhl_de_paket_default_packaging_id
    dhl_de_paket_package_width = fields.Integer(string="Package Width(Deprecated)")#Deprecated
    dhl_de_paket_package_length = fields.Integer(string="Package Length(Deprecated)")#Deprecated
    dhl_de_paket_dutiable = fields.Boolean(string="Dutiable Material",
                                           help="Check this if your package is dutiable.")
    dhl_de_paket_label_response_type = fields.Selection([('URL', 'URL'), ('B64', 'PDF File'),
                                                         ('ZPL2', 'ZPL2')], 'Output Formats', default='B64')
    dhl_de_paket_label_format = fields.Selection([('A4', 'A4 plain paper'),
                                                  ('910-300-700', 'A5 sheet 105 x 205 mm (910-300-700)'),
                                                  ('910-300-700-oz', 'A5 sheet 105 x 205 mm (910-300-700) without '
                                                                     'additional label'),
                                                  ('910-300-710', 'Laser printing105x209mm (910-300-710)'),
                                                  ('910-300-600', 'Thermal print (folding tape labels) '
                                                                  '103x199mm (910-300-600)'),
                                                  ("910-300-610", "Thermal print (roll) 103x199mm (910-300-610)"),
                                                  ("910-300-400", "Thermal print (folding tape labels) "
                                                                  "103x150mm (910-300-400)"),
                                                  ("910-300-410", "Thermal print (roll) 103x150mm (910-300-410)"),
                                                  ("910-300-300", "Laser printing (sheet A5) 105x148mm (910-300-300)"),
                                                  ("910-300-300-oz", " laser printing (sheet A5) 105x148mm, without "
                                                                     "additional labels (910-300-300)"),
                                                  ('100x70mm', '100x70mm (only for Warenpost, Warenpost International)')],
                                                 'Common Label Printing Formats', default='A4')
    dhl_de_paket_shipping_cost = fields.Float(string="Fixed Shipping Cost",
                                              help='As DHL Intraship doesnot provide the shipping cost, '
                                                   'you can manually specify the shipping price here.')
    dhl_de_paket_shipper_id = fields.Many2one("res.partner", "Shipper Address",
                                              help="If not set, shipper address is taken from warehouse address and "
                                                   "if warehouse address not set then company address will be taken.")
    dhl_de_paket_return_account_number = fields.Char(string="DHL Return Account Number",help="14 digit retour account number")

    @api.depends('delivery_type')
    def _compute_can_generate_return(self):
        super(ProviderDhlDe, self)._compute_can_generate_return()
        for carrier in self:
            if carrier.delivery_type == 'dhl_de_paket':
                carrier.can_generate_return = True

    def dhl_de_paket_rate_shipment(self, order):
        res = dict()
        res['price'] = self.dhl_de_paket_shipping_cost or 0.0
        res['success'] = True
        res['warning_message'] = False
        res['error_message'] = False
        return res

    def _dhl_de_paket_convert_weight(self, weight, unit):
        weight_uom_id = self.env['product.template']._get_weight_uom_id_from_ir_config_parameter()
        if unit == 'LB':
            return weight_uom_id._compute_quantity(weight, self.env.ref('uom.product_uom_lb'), round=False)
        else:
            return weight_uom_id._compute_quantity(weight, self.env.ref('uom.product_uom_kgm'), round=False)

    def dhl_de_paket_send_shipping(self, pickings):
        res = []
        dhl_label_format = self.dhl_de_paket_label_response_type == 'B64' and 'PDF' or \
                           self.dhl_de_paket_label_response_type
        self_su = self.sudo()
        if not self.prod_environment:
            dhl_de_paket_username = self_su.dhl_de_paket_developer_id
            dhl_de_paket_password = self_su.dhl_de_paket_portal_password
            dhl_de_paket_user = self_su.dhl_de_paket_test_user
            dhl_de_paket_signature = self_su.dhl_de_paket_test_signature
        else:
            dhl_de_paket_username = self_su.dhl_de_paket_application_id
            dhl_de_paket_password = self_su.dhl_de_paket_application_token
            dhl_de_paket_user = self_su.dhl_de_paket_intraship_user
            dhl_de_paket_signature = self_su.dhl_de_paket_intraship_signature
        if not all([dhl_de_paket_username, dhl_de_paket_password,
                    dhl_de_paket_user, dhl_de_paket_signature]):
            if self.prod_environment:
                raise UserError(
                    _("DHL Configuration Not Complete for %s\nPlease check Application ID, Application Token, "
                      "Intraship User and Intraship Signature fields are set correctly" % self.name))
            else:
                raise UserError(
                    _("Test Envirnoment for DHL Configuration %s Not Complete\nPlease check Developer ID, Password, "
                      "Test User and Test Signature fields are set correctly" % self.name))

        try:
            srm = DHLPaketProvider(username=dhl_de_paket_username,
                                   password=dhl_de_paket_password,
                                   user=dhl_de_paket_user,
                                   signature=dhl_de_paket_signature,
                                   test_mode=not self.prod_environment,
                                   debug_logger=self.log_xml)
            srm.login()
            for picking in pickings:
                shipping_data = {
                    'tracking_number': "",
                    'dhl_paket_label_url': "",
                    'exact_price': 0.0
                }
                response = srm.validate_shipping(picking, self)
                validation_failed = True

                if response and response.Status and response.Status.statusCode == 0:
                    validation_failed = False
                else:
                    if not response:
                        logmessage = (_("No Response from DHL"))
                    else:
                        logmessage = "An error occurred. \nStatus Code: %s, Status Text: %s" % (
                            ustr(response.Status.statusCode),
                            ustr(response.Status.statusText))
                        logmessage += "\nFull Response:\n %s" % (ustr(response))
                    picking.message_post(body=logmessage)
                    picking.sudo().sale_id.message_post(body=logmessage)
                    raise UserError(_(logmessage))

                if not validation_failed:
                    response = srm.send_shipping(picking, self)
                    # carrier_tracking_ref = []
                    label_urls = []
                    label_pdfs = []
                    track_numbers = []
                    carrier_tracking_link = []
                    ret_tracking_number_dict = {}
                    ret_label_dict = {}
                    for creationState in response.CreationState:
                        if creationState.LabelData.Status.statusCode in ["0", 0]:
                            tracking_number = creationState.shipmentNumber
                            if self.return_label_on_delivery:
                                ret_tracking_number_dict.update({tracking_number: creationState.returnShipmentNumber})
                            track_numbers.append(tracking_number)
                            tracker_url = 'https://nolp.dhl.de/nextt-online-public/en/search?piececode=%s' % tracking_number
                            carrier_tracking_link.append('<a href=' + tracker_url + '>' + tracking_number + '</a><br/>')

                            if hasattr(creationState.LabelData, 'labelUrl'):
                                label_urls.append('<a href=' + creationState.LabelData.labelUrl + '>' + tracking_number +
                                                  '</a><br/>')
                            elif dhl_label_format == 'PDF':
                                label_pdfs.append(('LabelDHL-%s.%s' % (tracking_number, dhl_label_format),
                                                   base64.b64decode(creationState.LabelData.labelData)))
                            else:
                                label_pdfs.append(('LabelDHL-%s.%s' % (tracking_number, dhl_label_format),
                                                   creationState.LabelData.labelData))
                            if self.return_label_on_delivery:
                                ret_tracking_number = creationState.returnShipmentNumber
                                ret_tracking_number_dict.update({tracking_number: ret_tracking_number})
                                if hasattr(creationState.LabelData, 'returnlabelUrl'):
                                    ret_label_dict.update({
                                        ret_tracking_number: '<a href=' + creationState.LabelData.returnLabelUrl + '>' +
                                                             ret_tracking_number + '</a><br/>'
                                    })
                                elif dhl_label_format == 'PDF':
                                    ret_label_dict.update({
                                        ret_tracking_number: ('%s-%s-%s.%s' % (self.get_return_label_prefix(), ret_tracking_number,
                                                                              tracking_number, dhl_label_format),
                                                       base64.b64decode(creationState.LabelData.returnLabelData))
                                    })
                                else:
                                    ret_label_dict.update({
                                        ret_tracking_number:('%s-%s-%s.%s' % (self.get_return_label_prefix(), ret_tracking_number,
                                                                              tracking_number, dhl_label_format),
                                                       creationState.LabelData.returnLabelData)
                                    })

                            picking.dhl_paket_label_url = tracker_url

                        else:
                            logmessage = (_("Failed Creating Label <br/> %s : %s") % (
                                creationState.StatusCode,
                                ustr(creationState)))
                            picking.message_post(body=logmessage)
                            picking.sudo().sale_id.message_post(body=logmessage)
                            raise UserError(_(logmessage))
    #                         raise except_orm(_("Error!!"), logmessage)
                    if not label_pdfs and not label_urls:
                        raise UserError(_("Labels could not be transferred for this tracking number: " + str("".join(track_numbers))))

                    logmessage = _("Shipment created into DHL <br/> <b>Tracking Number(s): </b>%s<br/>\n") % (
                                      ', '.join(carrier_tracking_link))
                    if label_urls:
                        logmessage += _("<b>Label Url(s): </b>  %s" % ', '.join(label_urls))
                        picking.message_post(body=logmessage)
                        if picking.sale_id:
                            picking.sudo().sale_id.message_post(body=logmessage)
                    if label_pdfs:
                        picking.message_post(body=logmessage, attachments=label_pdfs)
                        if picking.sale_id:
                            picking.sudo().sale_id.message_post(body=logmessage, attachments=label_pdfs)
                    if ret_label_dict:
                        logmessage = _("<b>Return Label Generated. Return Tracking Number(s): </b>  %s" % ', '.join(list(ret_label_dict.keys())))
                        picking.message_post(body=logmessage, attachments=list(ret_label_dict.values()))
                        picking.sudo().sale_id.message_post(body=logmessage, attachments=list(ret_label_dict.values()))
                    time.sleep(5)

                    attachment_ids = self.env['ir.attachment'].search(
                        [('res_model', '=', 'stock.picking'), ('res_id', '=', picking.id),
                         ('mimetype', '=', 'application/pdf')])

                    if not attachment_ids:
                        raise UserError(_("No shipping labels available for selected records."))

                    shipping_data = {
                        'tracking_number': ', '.join(track_numbers),
                        'exact_price': 0.0,
                        'dhl_paket_label_url': ', '.join(label_urls)
                    }

                picking.dhl_paket_label_url = shipping_data['dhl_paket_label_url']
                res = res + [shipping_data]

            return res
        except Exception as e:
            raise UserError(_(e))

    def dhl_de_paket_get_tracking_link(self, pickings):
        res = []
        for picking in pickings:
            res = res + ['https://nolp.dhl.de/nextt-online-public/en/search?piececode=%s' %
                         picking.carrier_tracking_ref]
        return res

    def dhl_de_paket_cancel_shipment(self, picking):
        self_su = self.sudo()
        if not self.prod_environment:
            dhl_de_paket_username = self_su.dhl_de_paket_developer_id
            dhl_de_paket_password = self_su.dhl_de_paket_portal_password
            dhl_de_paket_user = self_su.dhl_de_paket_test_user
            dhl_de_paket_signature = self_su.dhl_de_paket_test_signature
        else:
            dhl_de_paket_username = self_su.dhl_de_paket_application_id
            dhl_de_paket_password = self_su.dhl_de_paket_application_token
            dhl_de_paket_user = self_su.dhl_de_paket_intraship_user
            dhl_de_paket_signature = self_su.dhl_de_paket_intraship_signature
        srm = DHLPaketProvider(username=dhl_de_paket_username,
                                password=dhl_de_paket_password,
                                user=dhl_de_paket_user,
                                signature=dhl_de_paket_signature,
                                test_mode=not self.prod_environment,
                                debug_logger=self.log_xml)
        srm.login()
        response = srm.delete_shipment(picking, self)
        if response and response.Status and response.Status.statusCode == 0:
            logmessage = _("Shipment has been successfully deleted")
            picking.message_post(body=logmessage)
            picking.sudo().sale_id.message_post(body=logmessage)
            picking.dhl_paket_label_url = False
        else:
            if response:
                logmessage = '\n'.join(['%s - %s: %s' % (
                    deletionState.shipmentNumber,
                    deletionState.Status.statusCode,
                    deletionState.Status.statusText) for deletionState in response.DeletionState])
                # error_message = logmessage
                logmessage += "\nFull Response:\n" + ustr(response)
            else:
                logmessage = "No response receive from DHL."
                # error_message = logmessage
            picking.message_post(body=logmessage)
            picking.sudo().sale_id.message_post(body=logmessage)
#             raise except_orm("Error !!!", error_message)
        return True

    def dhl_de_paket_get_return_label(self, picking, tracking_number=None, origin_date=None):
        raise ValidationError(_('Creating new DHL return label not implemented.'))

        # self_su = self.sudo()
        # if not self.prod_environment:
        #     dhl_de_paket_username = self_su.dhl_de_paket_developer_id
        #     dhl_de_paket_password = self_su.dhl_de_paket_portal_password
        #     dhl_de_paket_user = self_su.dhl_de_paket_test_user
        #     dhl_de_paket_signature = self_su.dhl_de_paket_test_signature
        # else:
        #     dhl_de_paket_username = self_su.dhl_de_paket_application_id
        #     dhl_de_paket_password = self_su.dhl_de_paket_application_token
        #     dhl_de_paket_user = self_su.dhl_de_paket_intraship_user
        #     dhl_de_paket_signature = self_su.dhl_de_paket_intraship_signature
        # srm = DHLPaketProvider(username=dhl_de_paket_username,
        #                        password=dhl_de_paket_password,
        #                        user=dhl_de_paket_user,
        #                        signature=dhl_de_paket_signature,
        #                        test_mode=not self.prod_environment,
        #                        debug_logger=self.log_xml)
        # srm.login()
        # if not tracking_number:
        #     tracking_number = picking.carrier_tracking_ref
        # if not tracking_number:
        #     raise ValidationError(_('Not possible to create new DHL Retour Label. Please provide the return tracking number already created in the delivery order.'))
        # response = srm.get_label(picking, self, tracking_number)

