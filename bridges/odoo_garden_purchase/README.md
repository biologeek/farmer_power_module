# Farmer Power - Purchase bridge (`odoo_garden_purchase`)

Optional module, installed automatically (`auto_install`) when `odoo_garden` and `purchase` are both installed.
It adds no dependency to `odoo_garden`.

## What it does

**Planning > Create Seed Requests for Quotation** (also a button on the season form) opens a wizard that turns the
seed needs of one season (`garden.crop.get_seed_needs`, the same figures as the "Seed Needs" report) into
**draft** requests for quotation (`purchase.order`):

- one request per supplier (`supplier_id` of the variety), one line per variety and product;
- seeds are ordered through `seed_product_id`; the quantity in grams is converted to the unit of measure of the
  product if it is a weight unit (g, kg...), or expressed as a number of seeds if the product is counted in
  Units; any other unit of measure is skipped with a warning;
- crops whose route is "bought plants" are ordered through the `plant_product_id` of the route, in plants
  (option "Include Bought Plants");
- a variety without supplier, a variety without seed product or a route without plant product is skipped and
  listed in the preview and in the result.

### Idempotence rule

Lines created by the wizard carry the season and the variety (`garden_season_id`, `garden_variety_id`). On every
run, the quantity already requested for the same season, variety and product (lines of non-cancelled orders, in any
state) is deducted from the need; only the missing quantity is requested. Running the wizard twice creates nothing
the second time; if the plan grows, only the difference is requested; cancelling an order makes its quantity
requestable again.

### Access rights

The wizard is available to the crop manager (`Chef de culture`) and the manager groups, who do not
necessarily have access to Purchase: the requests are created with a targeted `sudo()` (the user remains the
creator) and the user only sees the result message (and a button to open the requests if they can read Purchase).
Existing purchase orders stay invisible to them.

## Tests

`odoo-bin -d <db> -i odoo_garden_purchase --test-enable --test-tags /odoo_garden_purchase --stop-after-init`
