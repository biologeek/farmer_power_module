-- Renomme les modules odoo_garden* en farmer_power* dans une base existante.
-- À exécuter UNE FOIS, serveur arrêté, AVANT la mise à jour (-u farmer_power) et après la sauvegarde de la base :
--   psql -d <base> -f tools/rename_odoo_garden_to_farmer_power.sql
-- Les nouvelles installations n'en ont pas besoin.
BEGIN;
UPDATE ir_module_module SET name = 'farmer_power' || substr(name, 12) WHERE name LIKE 'odoo\_garden%';
UPDATE ir_module_module_dependency SET name = 'farmer_power' || substr(name, 12) WHERE name LIKE 'odoo\_garden%';
UPDATE ir_model_data SET module = 'farmer_power' || substr(module, 12) WHERE module LIKE 'odoo\_garden%';
UPDATE ir_config_parameter SET key = 'farmer_power' || substr(key, 12) WHERE key LIKE 'odoo\_garden.%';
UPDATE ir_ui_view SET key = 'farmer_power' || substr(key, 12) WHERE key LIKE 'odoo\_garden.%';
DELETE FROM ir_attachment WHERE url LIKE '/web/assets/%';  -- bundles d'assets, régénérés
COMMIT;
