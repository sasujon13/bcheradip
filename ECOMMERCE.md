# Cheradip eCommerce operations

The marketplace is available at `/ecommerce` and, after DNS/web-server setup, at
`ecommerce.cheradip.com`. Existing Cheradip applications and legacy routes remain
independent.

## First deployment

1. Create the MySQL database named `ecommerce` and grant the existing application
   database user access to it.
2. Set `DATABASE_ECOMMERCE_NAME=ecommerce` in the server environment.
3. Run `python manage.py migrate ecommerce --database=ecommerce`.
4. Optionally load replaceable sample inventory with
   `python manage.py seed_ecommerce --per-category 10`.

The seed command uses public placeholder product data and marks every generated
record as a sample, so administrators can archive, edit, or delete it.

## Catalog imports

Administrators can download the CSV template from the **Manage** section of the
storefront or directly from `/api/ecommerce/admin/import/sample.csv`. Save edited
files as UTF-8 CSV and retain the header names. Repeating a product `Handle` adds
another option/variant; `SKU` is the unique update key for inventory and prices.

## Daily operations

- Use **Manage** at `/ecommerce` for the summary, CSV import, order progress, and
  payment confirmation.
- Use `/admin?db=ecommerce` for full product, category, brand, variant, inventory,
  coupon, review, notification, shipment, and import-job administration.
- Customers track an order with both its order number and private tracking token.
- Physical orders below BDT 3,000 receive an BDT 80 delivery charge; shipping is
  free at or above that threshold. The backend calculates this value.

Back up the `ecommerce` database with the other configured databases before
deployments or bulk imports.
