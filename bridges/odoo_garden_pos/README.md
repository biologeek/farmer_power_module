# Odoo Garden - Point of Sale bridge (`odoo_garden_pos`)

Optional module, installed automatically (`auto_install`) when `odoo_garden` and `point_of_sale` are both
installed. It adds no dependency to `odoo_garden`.

## What it does

Market sales rung up in the Point of Sale are included in the revenue of the crops (`garden.crop.revenue`), the
profitability report (`garden.crop.profitability`), the dashboard (monthly revenue) and the **Sales** button of the
crop, exactly like customer invoices. It extends the revenue service `garden.revenue` through the hook
`get_extra_entries`.

- **Lines counted**: lines of POS orders in state *Paid* or *Posted* (draft and cancelled orders are ignored).
  Amount: tax-excluded subtotal, converted to the company currency. Refunds (negative quantity) count negatively.
- **Pro rata method** (default): for a product and a month, the revenue is split between the crops harvested that
  month, in proportion to the harvested quantities - same rule as for invoices.
- **By lot method**: lot names typed on the POS line (`pack_lot_ids`, `pos.pack.operation.lot.lot_name`) are
  matched with the crop lots (the lot of a crop is named after the crop) by product and name. The amount of the
  line is split equally between the lots entered; a lot that is not a crop lot gets nothing.

### No double counting with invoices

- *Pro rata*: a POS order that has a **posted** invoice is skipped (its invoice lines are already counted with the
  customer invoices). An order whose invoice is still a draft or was cancelled is counted by the POS.
- *By lot*: the invoice attribution goes through sale orders and delivery moves, which a POS invoice does not
  have. The POS lot is then the only source and the order is counted once, invoiced or not.

### Access rights

POS orders are read with `sudo()`; the crop manager only sees the attributed amounts per crop (Sales button),
never the orders themselves.

## Tests

`odoo-bin -d <db> -i odoo_garden_pos --test-enable --test-tags /odoo_garden_pos --stop-after-init`
