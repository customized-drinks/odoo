# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.


"""
Main Model for Vat Configuration.
"""
import random
import logging
from odoo import api, fields, models

_logger = logging.getLogger("Amazon")

# List of Europe countries with its Standard VAT rates
COUNTRY_STANDARD_VAT_RATES = {'base.at': 20.00, 'base.be': 21.00, 'base.cz': 21.00, 'base.dk': 25.00,
                              'base.ee': 20.00, 'base.fi': 24.00, 'base.fr': 20.00, 'base.de': 19.00,
                              'base.gr': 24.00, 'base.hu': 27.00, 'base.bg': 20.00, 'base.hr': 25.00,
                              'base.cy': 19.00, 'base.ie': 23.00, 'base.it': 22.00, 'base.lv': 21.00,
                              'base.lt': 21.00, 'base.lu': 17.00, 'base.mt': 18.00, 'base.nl': 21.00,
                              'base.pl': 23.00, 'base.pt': 23.00, 'base.ro': 19.00, 'base.sk': 20.00,
                              'base.si': 22.00, 'base.es': 21.00, 'base.se': 25.00}

class VatConfigLineEpt(models.Model):
    """
    For Setting VAT number for Country.
    @author: Maulik Barad on Date 11-Jan-2020.
    """
    _name = "vat.config.line.ept"
    _description = "VAT Configuration Line EPT"

    def _get_country_domain(self):
        """
        Creates domain to only allow to select company from allowed companies in switchboard.
        @author: Maulik Barad on Date 11-Jan-2020.
        """
        country_list = []
        europe_group = self.env.ref("base.europe", raise_if_not_found=False)
        uk_ref = self.env.ref("base.uk", raise_if_not_found=False)
        if europe_group:
            country_list = europe_group.country_ids.ids
        if uk_ref:
            country_list += uk_ref.ids
        return [("id", "in", country_list)]

    vat_config_id = fields.Many2one("vat.config.ept", ondelete="cascade")
    vat = fields.Char("VAT Number")
    country_id = fields.Many2one("res.country", domain=_get_country_domain)

    _sql_constraints = [
        ("unique_country_vat_config", "UNIQUE(vat_config_id,country_id)",
         "VAT configuration is already added for the country.")]

    @api.model
    def create(self, values):
        """
        Inherited the create method for updating the VAT number and creating Fiscal positions.
        @author: Maulik Barad on Date 13-Jan-2020.
        @author: Twinkal Chandarana on date 12-FEB-2021
        MOD : Create an VCS FPOS based on VAT number configurations.
        updated by: Kishan Sorani on date 25-Jun-2021
        MOD : update data dict
        """
        result = super(VatConfigLineEpt, self).create(values)
        warehouse_obj = self.env["stock.warehouse"]

        data = {"company_id": result.vat_config_id.company_id.id,
                "vat_config_id": values["vat_config_id"], "is_amazon_fpos": True,
                "is_union_oss_vat_declaration": result.vat_config_id.is_union_oss_vat_declaration}

        country_id = result.country_id
        excluded_vat_registered_europe_group = self.env.ref("amazon_ept.excluded_vat_registered_europe")
        if country_id.id in excluded_vat_registered_europe_group.country_ids.ids:
            excluded_vat_registered_europe_group.country_ids = [(3, country_id.id, 0)]
            _logger.info("COUNTRY REMOVED FROM THE EUROPE GROUP ")

        # Updating the VAT number into warehouse's partner of the same country.
        warehouses = warehouse_obj.search([("company_id", "=", data["company_id"])])
        warehouse_partners = warehouses.partner_id.filtered(
            lambda x: x.country_id.id == country_id.id and not x.vat)
        if warehouse_partners:
            warehouse_partners.write({"vat": values["vat"]})
            _logger.info("VAT Number Updated OF Warehouse's Partner Which Belongs To Country %s." % (country_id.id))

        # Creating Amazon Fiscal positions.
        self.create_amazon_fpos_ept(data, country_id)

        return result

    def create_amazon_fpos_ept(self, data, country_id):
        """
        Create Fiscal Positions Automatically as per VAT number Configurations.
        For Ex. France VAT
            - Deliver to France(B2C)
            - VCS - Deliver to France(VAT Required)(B2B)
            - Deliver from France to Europe(Exclude VAT registered country)(B2C)
            - VCS - Deliver from France to Europe(VAT Required)(B2B)
            - VCS - Deliver from France to Outside Europe (B2C)
            - VCS - Deliver from France to Outside Europe (VAT Required)(B2B)

        updated by : Kishan Sorani on Date 10-JUN-2021
        MOD : if is_union_oss_vat_declaration true the no need
              to create Delivered Country to EU(Exclude VAT registered country)
              fiscal position for VAT number configure country
        """
        fiscal_position_obj = self.env["account.fiscal.position"]
        excluded_vat_registered_europe_group = self.env.ref("amazon_ept.excluded_vat_registered_europe")
        europe_group = self.env.ref('base.europe', raise_if_not_found=False)
        country_name = country_id.name
        union_oss_vat_declaration = data["is_union_oss_vat_declaration"]
        del data["is_union_oss_vat_declaration"]

        # Delivered Country to Country
        existing_fiscal_position = fiscal_position_obj.search( [("company_id", "=", data["company_id"]),
                                                                ('vat_required', '=', False),
                                                                ("country_id", "=", country_id.id)], limit=1)
        if not existing_fiscal_position:
            data.update({'name': "Deliver to %s[B2C]" % country_name,
                         'country_id': country_id.id})
            fpos_record = fiscal_position_obj.create(data)
            # create automatic tax record for fiscal position if is_auto_create_taxes true
            if fpos_record.vat_config_id.is_auto_create_taxes:
                self.create_automatic_tax_record(fpos_record)
            _logger.info("Fiscal Position Created For Country %s[B2C]." % country_name)
        elif not existing_fiscal_position.is_amazon_fpos:
            existing_fiscal_position.is_amazon_fpos = True

        # VCS - Vat Required - Delivered Country to Country
        vat_fiscal_position = fiscal_position_obj.search([("company_id", "=", data["company_id"]),
                                                          ("country_id", "=", country_id.id),
                                                          ('vat_required', '=', True)], limit=1)
        if not vat_fiscal_position:
            data.update({'name': "Deliver to %s[B2B]" % country_name,
                         'country_id': country_id.id, 'vat_required': True})
            fpos_record = fiscal_position_obj.create(data)
            # create automatic tax record for fiscal position if is_auto_create_taxes true
            if fpos_record.vat_config_id.is_auto_create_taxes:
                self.create_automatic_tax_record(fpos_record)
            _logger.info("Fiscal Position Created For Country %s[B2B]." % country_name)
        elif not vat_fiscal_position.is_amazon_fpos:
            vat_fiscal_position.is_amazon_fpos = True

        if not union_oss_vat_declaration:
            # VAT Required False - Delivered Country to EU(Exclude VAT registered country)
            existing_excluded_fiscal_position = fiscal_position_obj.search(
                [("company_id", "=", data["company_id"]), ("origin_country_ept", "=", country_id.id),
                 ('vat_required', '=', False), ("country_group_id", "=", excluded_vat_registered_europe_group.id if
                excluded_vat_registered_europe_group else False)], limit=1)
            if not existing_excluded_fiscal_position:
                data.update({"name": "Deliver from %s to Europe(Exclude VAT registered country)[B2C]" % country_name,
                             "origin_country_ept": country_id.id, 'vat_required': False,
                             "country_group_id": excluded_vat_registered_europe_group.id if
                             excluded_vat_registered_europe_group else False})
                if 'country_id' in data.keys():
                    del data['country_id']
                fpos_record = fiscal_position_obj.create(data)
                # create automatic tax record for fiscal position if is_auto_create_taxes true
                if fpos_record.vat_config_id.is_auto_create_taxes:
                    self.create_automatic_tax_record(fpos_record)
                _logger.info("Fiscal Position Created From %s To Excluded Country Group[B2C]." % country_name)
            elif not existing_excluded_fiscal_position.is_amazon_fpos:
                existing_excluded_fiscal_position.is_amazon_fpos = True

        # VAT REquired - VCS Delivered Country to EU
        existing_europe_vat_fpos = fiscal_position_obj.search([
            ("company_id", "=", data["company_id"]), ('vat_required', '=', True),
            ("origin_country_ept", "=", country_id.id),
            ("country_group_id", "=", europe_group.id if europe_group else False)], limit=1)
        if not existing_europe_vat_fpos:
            data.update({"name": "Deliver from %s to Europe[B2B]" % country_name,
                         "origin_country_ept": country_id.id, "vat_required": True,
                         "country_group_id": europe_group.id if europe_group else False})
            if 'country_id' in data.keys():
                del data['country_id']
            fpos_record = fiscal_position_obj.create(data)
            # create automatic tax record for fiscal position if is_auto_create_taxes true
            if fpos_record.vat_config_id.is_auto_create_taxes:
                self.create_automatic_tax_record(fpos_record)
            _logger.info("Fiscal Position Created From %s To Europe Country Group[B2B]." % country_name)
        elif not existing_europe_vat_fpos.is_amazon_fpos:
            existing_europe_vat_fpos.is_amazon_fpos = True

        # VCS - Delivered Country to Outside EU
        outside_eu_fiscal_position = fiscal_position_obj.search([("company_id", "=", data["company_id"]),
                                                                 ("origin_country_ept", "=", country_id.id),
                                                                 ('vat_required', '=', False),
                                                                 ('country_group_id', '=', False)], limit=1)

        if not outside_eu_fiscal_position:
            data.update({"name": "Deliver from %s to Outside Europe[B2C]" % country_name,
                         'origin_country_ept': country_id.id, "vat_required": False})
            if 'country_group_id' in data.keys():
                del data['country_group_id']
            if 'country_id' in data.keys():
                del data['country_id']
            fpos_record = fiscal_position_obj.create(data)
            # create automatic tax record for fiscal position if is_auto_create_taxes true
            if fpos_record.vat_config_id.is_auto_create_taxes:
                self.create_automatic_tax_record(fpos_record)
            _logger.info("Fiscal Position Created From %s To Outside EU[B2C]." % country_name)
        elif not outside_eu_fiscal_position.is_amazon_fpos:
            outside_eu_fiscal_position.is_amazon_fpos = True

        # VCS - Delivered Country to Outside EU(VAT Required)
        vcs_outside_eu_fiscal_position = fiscal_position_obj.search([("company_id", "=", data["company_id"]),
                                                                      ("origin_country_ept", "=", country_id.id),
                                                                      ('vat_required', '=', True),
                                                                      ('country_group_id', '=', False)], limit=1)

        if not vcs_outside_eu_fiscal_position:
            data.update({"name": "Deliver from %s to Outside Europe(VAT Required)[B2B]" % country_name,
                         'origin_country_ept': country_id.id, "vat_required": True})
            if 'country_group_id' in data.keys():
                del data['country_group_id']
            if 'country_id' in data.keys():
                del data['country_id']
            fpos_record = fiscal_position_obj.create(data)
            # create automatic tax record for fiscal position if is_auto_create_taxes true
            if fpos_record.vat_config_id.is_auto_create_taxes:
                self.create_automatic_tax_record(fpos_record)
            _logger.info("Fiscal Position Created From %s To Outside EU(VAT Required)[B2B]." % country_name)
        elif not vcs_outside_eu_fiscal_position.is_amazon_fpos:
            vcs_outside_eu_fiscal_position.is_amazon_fpos = True

        return True

    def create_union_oss_vat_country_fiscal_position(self, data):
        """
        Define method for creating Country to Country[B2C] fiscal position for those
        all countries which present in excluded_vat_registered_europe_group
        :param data: required data dictionary for creating fiscal position record
        :return:
        @author: Kishan Sorani on date 10-JUN-2021
        """
        fiscal_position_obj = self.env["account.fiscal.position"]
        country_obj = self.env["res.country"]
        uk_ref = self.env.ref("base.uk", raise_if_not_found=False)
        excluded_vat_group = self.env.ref("amazon_ept.excluded_vat_registered_europe", raise_if_not_found=False)
        country_ids = excluded_vat_group.country_ids.ids
        for country_id in country_ids:
            country = country_obj.browse(country_id)
            # skip country if it United Kingdom
            if country.id == uk_ref.id:
                continue
            country_name = country.name
            existing_fiscal_position = fiscal_position_obj.search([("company_id", "=", data["company_id"]),
                                                                   ('vat_required', '=', False),
                                                                   ("country_id", "=", country.id)], limit=1)

            if not existing_fiscal_position:
                data.update({'name': "Deliver to %s[B2C]" % country_name,
                             'country_id': country.id})
                fpos_record = fiscal_position_obj.create(data)
                # create automatic tax record for fiscal position if is_auto_create_taxes true
                if fpos_record.vat_config_id.is_auto_create_taxes:
                    self.create_automatic_tax_record(fpos_record)
                _logger.info("Fiscal Position Created For Country %s[B2C]." % country_name)
            elif not existing_fiscal_position.is_amazon_fpos:
                existing_fiscal_position.is_amazon_fpos = True
        return True

    def create_automatic_tax_record(self, fpos_record):
        """
        Define method for create automatic taxes records for automatic
        created fiscal positions and set created taxes in fiscal position
        for Tax Mapping with default tax of product in sale order line
        :param fpos_record: fiscal position record
        :return
        @author: Kishan Sorani on date 19-JUN-2021
        """
        tax_group = self.env['account.tax.group'].search([], limit=1)
        company_id = fpos_record.vat_config_id.company_id
        # prepare common data
        tax_data, tax_search_domain = self.prepare_tax_create_search_data(tax_group, company_id)
        country_id = fpos_record.country_id if fpos_record.country_id else fpos_record.origin_country_ept
        # create tax record if required else return exist tax record
        tax_record = self.create_tax_record(country_id, tax_data, tax_search_domain)
        # map created tax with default product taxes and set account in tax
        self.map_tax_and_set_account(tax_record, fpos_record)

    def prepare_tax_create_search_data(self, tax_group, company_id):
        """
        Define method for prepare common data for creating or searching
        taxes records
        :param tax_group: tax group record
        :param company_id: company record
        :return: prepared common data dict for create or
                 common search domain for search taxes records
        @author: Kishan Sorani on date 21-JUN-2021
        """
        tax_data = {'amount_type': 'percent', 'type_tax_use': 'sale',
                    'tax_group_id': tax_group.id if tax_group else False,
                    'company_id': company_id.id if company_id else False, 'price_include': True}

        tax_search_domain = [('amount_type', '=', 'percent'), ('type_tax_use', '=', 'sale'),
                             ('company_id', '=', company_id.id if company_id else False),
                             ('price_include', '=', True)]
        return tax_data, tax_search_domain

    def create_tax_record(self, country_id, tax_data, tax_search_domain):
        """
        Define method for create tax record for fiscal position
        :param country_id: country record
        :param tax_data: required data for create tax record
        :param tax_search_domain: required data for search exist tax record
        :return: tax record
        @author: Kishan Sorani on date 22-JUN-2021
        """
        account_tax_obj = self.env['account.tax']
        # get country ref
        country_ref_dict = country_id.get_external_id()
        country_ref = country_ref_dict.get(country_id.id)
        # get country standard VAT rate by using country ref
        tax_amount = COUNTRY_STANDARD_VAT_RATES.get(country_ref, 0.0)
        tax_name = "Tax(%s%s) %s (incl)" % (str(tax_amount), '%', str(country_id.code))
        search_domain = tax_search_domain + [('name', '=', tax_name), ('amount', '=', tax_amount)]
        tax_record = account_tax_obj.search(search_domain, limit=1)
        if not tax_record:
            tax_data.update({'name': tax_name, 'amount': tax_amount})
            tax_record = account_tax_obj.create(tax_data)
        return tax_record

    def map_tax_and_set_account(self, tax_record, fiscal_position):
        """
        Define method which map created tax record with default product
        taxes in fiscal position and set account record in tax
        invoice and refund lines
        :param tax_record: created tax record
        :param fiscal_position: created fiscal position record
        :return:
        @author: Kishan Sorani on date 22-JUN-2021
        """
        account_id = fiscal_position.vat_config_id.account_id
        # set account record in invoice lines of tax record
        invoice_lines = tax_record.invoice_repartition_line_ids.filtered(lambda line: line.repartition_type == 'tax')
        for invoice_line in invoice_lines:
            if not invoice_line.account_id or invoice_line.account_id.id != account_id.id:
                invoice_line.write({'account_id': account_id.id})
        # set account record in refund lines of tax record
        refund_lines = tax_record.refund_repartition_line_ids.filtered(lambda line: line.repartition_type == 'tax')
        for refund_line in refund_lines:
            if not refund_line.account_id or refund_line.account_id.id != account_id.id:
                refund_line.write({'account_id': account_id.id})

        # Map account default tax with newly created tax in fiscal position
        if self.env.company.account_sale_tax_id:
            default_sale_tax = self.env.company.account_sale_tax_id
            fiscal_position.write({'tax_ids': [(0, 0, {'tax_src_id': default_sale_tax.id,
                                                       'tax_dest_id': tax_record.id})]})
        return True
