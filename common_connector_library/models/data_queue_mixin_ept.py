# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.
""" Mixin class for deleting unused data queue from database."""
import itertools
from odoo import models

class DataQueueMixinEpt(models.AbstractModel):
    """ Mixin class for deleting unused data queue from database."""
    _name = 'data.queue.mixin.ept'
    _description = 'Data Queue Mixin'

    def delete_data_queue_ept(self, queue_detail=[], is_delete_queue=False):
        """
        Usage: Method for deleting unused data queues from connectors after 7 days.
        @author: Dipak Gogiya
        :param is_delete_queue: Delete all data form queue table.
        :param queue_detail: ['sample_data_queue_ept1','sample_data_queue_ept2']
        :return: True

        Changes done by twinkalc on 3rd FEB 2021 to delete log book data and process
        the unique list to delete datas from the database.
        """
        if queue_detail:
            try:
                queue_detail += ['common_log_book_ept']
                queue_detail = list(set(queue_detail))
                for tbl_name in queue_detail:
                    self.delete_data_queue_schedule_activity_ept(tbl_name, is_delete_queue)
                    if is_delete_queue:
                        self._cr.execute("""delete from %s """ % str(tbl_name))
                        continue
                    self._cr.execute(
                        """delete from %s where cast(create_date as Date) <= current_date - %d""" % (str(tbl_name), 7))
            except Exception as error:
                return error
        return True

    def delete_data_queue_schedule_activity_ept(self, tbl_name, is_delete_queue=False):
        """
        Define this method for delete schedule activity for the deleted data queues or
        log book records.
        :param tbl_name: deleted table name
        :param is_delete_queue: True or False
        :return: Boolean (TRUE/FALSE)
        """
        log_line_obj = self.env['common.log.lines.ept']
        model_name = tbl_name.replace('_', '.')
        model_id = log_line_obj.get_model_id(model_name)
        if is_delete_queue:
            self._cr.execute(f"delete from mail_activity where res_model_id={model_id}")
        else:
            self._cr.execute(
                """select id from %s where cast(create_date as Date) <= current_date - %d""" % (str(tbl_name), 7))
            results = self._cr.fetchall()
            records = tuple(set(list(itertools.chain(*results))))
            if records:
                if len(records) == 1:
                    delete_activity = f"delete from mail_activity where res_id={records[0]} and res_model_id={model_id}"
                else:
                    delete_activity = f"delete from mail_activity where res_id in {records} and res_model_id={model_id}"
                self._cr.execute(delete_activity)
        return True
