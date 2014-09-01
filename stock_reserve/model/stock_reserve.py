# -*- coding: utf-8 -*-
##############################################################################
#
#    Author: Guewen Baconnier
#    Copyright 2013 Camptocamp SA
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

from openerp import models, fields, api
from openerp.exceptions import except_orm
from openerp.tools.translate import _


class StockReservation(models.Model):
    """ Allow to reserve products.

    The fields mandatory for the creation of a reservation are:

    * product_id
    * product_qty
    * product_uom
    * name

    The following fields are required but have default values that you may
    want to override:

    * company_id
    * location_id
    * dest_location_id

    Optionally, you may be interested to define:

    * date_validity  (once passed, the reservation will be released)
    * note
    """
    _name = 'stock.reservation'
    _description = 'Stock Reservation'
    _inherits = {'stock.move': 'move_id'}

    move_id = fields.Many2one(
        'stock.move',
        'Reservation Move',
        required=True,
        readonly=True,
        ondelete='cascade',
        select=1)
    date_validity = fields.Date('Validity Date')

    @api.model
    def get_location_from_ref(self, ref):
        """ Get a location from a xmlid if allowed
        :param ref: tuple (module, xmlid)
        """
        data_obj = self.env['ir.model.data']
        try:
            location = data_obj.xmlid_to_object(ref, raise_if_not_found=True)
            location.check_access_rule('read')
            location_id = location.id
        except (except_orm, ValueError):
            location_id = False
        return location_id

    @api.model
    def _default_location_id(self):
        move_obj = self.env['stock.move']
        return (move_obj
                .with_context(picking_type='internal')
                ._default_location_source())

    @api.model
    def _default_location_dest_id(self):
        ref = 'stock_reserve.stock_location_reservation'
        return self.get_location_from_ref(ref)

    _defaults = {
        'type': 'internal',
        'location_id': _default_location_id,
        'location_dest_id': _default_location_dest_id,
        'product_qty': 1.0,
    }

    @api.multi
    def reserve(self):
        """ Confirm a reservation

        The reservation is done using the default UOM of the product.
        A date until which the product is reserved can be specified.
        """
        move_recs = self.move_id
        move_recs.date_expected = fields.Datetime.now()
        move_recs.action_confirm()
        move_recs.force_assign()
        return True

    @api.multi
    def release(self):
        """
        Releas moves from reservation
        """
        move_recs = self.move_id
        move_recs.action_cancel()
        return True

    @api.model
    def release_validity_exceeded(self, ids=None):
        """ Release all the reservation having an exceeded validity date """
        domain = [('date_validity', '<', fields.date.today()),
                  ('state', '=', 'assigned')]
        if ids:
            domain.append(('id', 'in', ids))
        reserv_ids = self.search(domain)
        self.release(reserv_ids)
        return True

    @api.multi
    def unlink(self):
        """ Release the reservation before the unlink """
        self.release()
        return super(StockReservation, self).unlink()

    @api.onchange('product_id')
    def _onchange_product_id(self):
        """ set product_uom and name from product onchange """
        # save value before reading of self.move_id as this last one erase
        # product_id value
        product = self.product_id
        # WARNING this gettattr erase self.product_id
        move = self.move_id
        result = move.onchange_product_id(
            prod_id=product.id, loc_id=False, loc_dest_id=False,
            partner_id=False)
        if result.get('value'):
            vals = result['value']
            # only keep the existing fields on the view
            self.name = vals.get('name')
            self.product_uom = vals.get('product_uom')
            # repeat assignation of product_id so we don't loose it
            self.product_id = product.id

    @api.onchange('product_uom_qty')
    def _onchange_quantity(self):
        """ On change of product quantity avoid negative quantities """
        if not self.product_id or self.product_qty <= 0.0:
            self.product_qty = 0.0

    @api.multi
    def open_move(self):
        assert len(self._ids) == 1, "1 ID expected, got %r" % self._ids
        reserv = self[0].move_id
        data_obj = self.env['ir.model.data']
        ref_form2 = 'stock.action_move_form2'
        action = data_obj.xmlid_to_object(ref_form2)
        action_dict = action.read()
        action_dict['name'] = _('Reservation Move')
        # open directly in the form view
        ref_form = 'stock.view_move_form'
        view_id = data_obj.xmlid_to_res_id(ref_form)
        action['views'] = [(view_id, 'form')]
        action['res_id'] = reserv['move_id']
        return action
