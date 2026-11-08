-- Schema for the sales_inventory database (MySQL 8): the six tables, no data.
-- Exported with mysqldump --no-data from a database built by the Alembic migrations
-- (flask db upgrade). The migrations are the source of truth. This file is for reading, or
-- for a manual setup instead of flask db upgrade:
--
--   1. Create an empty database:   CREATE DATABASE sales_inventory CHARACTER SET utf8mb4;
--   2. Load this file:             mysql -u app_user -p sales_inventory < sql/schema.sql
--   3. Tell Alembic the tables already exist, so a later flask db upgrade doesn't try to
--      create them again:          flask db stamp head
--   4. Add the sample data:        python scripts/seed.py
--
-- Foreign key checks are off while the tables are created, because the tables are in
-- alphabetical order and some point to a table created after them. They are back on at the end.

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

CREATE TABLE `customers` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(100) NOT NULL,
  `email` varchar(255) DEFAULT NULL,
  `mobile` varchar(20) DEFAULT NULL,
  `city` varchar(100) DEFAULT NULL,
  `is_active` tinyint(1) NOT NULL,
  `created_at` datetime NOT NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  KEY `ix_customers_email` (`email`),
  KEY `ix_customers_mobile` (`mobile`),
  KEY `ix_customers_name` (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `products` (
  `id` int NOT NULL AUTO_INCREMENT,
  `code` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_as_ci NOT NULL,
  `name` varchar(150) NOT NULL,
  `category` varchar(100) NOT NULL,
  `price` decimal(12,2) NOT NULL,
  `stock_quantity` int NOT NULL,
  `is_active` tinyint(1) NOT NULL,
  `created_at` datetime NOT NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_products_code` (`code`),
  KEY `ix_products_category` (`category`),
  KEY `ix_products_name` (`name`),
  CONSTRAINT `ck_products_price_not_negative` CHECK ((`price` >= 0)),
  CONSTRAINT `ck_products_stock_not_negative` CHECK ((`stock_quantity` >= 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `sales_order_items` (
  `id` int NOT NULL AUTO_INCREMENT,
  `order_id` int NOT NULL,
  `product_id` int NOT NULL,
  `quantity` int NOT NULL,
  `rate` decimal(12,2) NOT NULL,
  `amount` decimal(12,2) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_sales_order_items_order_id_product_id` (`order_id`,`product_id`),
  KEY `ix_sales_order_items_product_id` (`product_id`),
  CONSTRAINT `fk_sales_order_items_order_id_sales_orders` FOREIGN KEY (`order_id`) REFERENCES `sales_orders` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `fk_sales_order_items_product_id_products` FOREIGN KEY (`product_id`) REFERENCES `products` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `ck_sales_order_items_quantity_positive` CHECK ((`quantity` > 0)),
  CONSTRAINT `ck_sales_order_items_rate_not_negative` CHECK ((`rate` >= 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `sales_orders` (
  `id` int NOT NULL AUTO_INCREMENT,
  `order_number` varchar(20) DEFAULT NULL,
  `customer_id` int NOT NULL,
  `order_date` date NOT NULL,
  `status` varchar(10) NOT NULL,
  `discount_percent` decimal(5,2) NOT NULL,
  `subtotal` decimal(12,2) NOT NULL,
  `discount_amount` decimal(12,2) NOT NULL,
  `grand_total` decimal(12,2) NOT NULL,
  `created_by` int NOT NULL,
  `created_at` datetime NOT NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_sales_orders_order_number` (`order_number`),
  KEY `ix_sales_orders_created_by` (`created_by`),
  KEY `ix_sales_orders_customer_id` (`customer_id`),
  KEY `ix_sales_orders_status_order_date` (`status`,`order_date`),
  CONSTRAINT `fk_sales_orders_created_by_users` FOREIGN KEY (`created_by`) REFERENCES `users` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `fk_sales_orders_customer_id_customers` FOREIGN KEY (`customer_id`) REFERENCES `customers` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `ck_sales_orders_discount_range` CHECK (((`discount_percent` >= 0) and (`discount_percent` <= 20))),
  CONSTRAINT `ck_sales_orders_status_valid` CHECK ((`status` in (_utf8mb4'draft',_utf8mb4'confirmed',_utf8mb4'cancelled')))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `stock_movements` (
  `id` int NOT NULL AUTO_INCREMENT,
  `product_id` int NOT NULL,
  `movement_type` varchar(20) NOT NULL,
  `quantity_change` int NOT NULL,
  `order_id` int DEFAULT NULL,
  `reason` varchar(255) NOT NULL,
  `created_by` int NOT NULL,
  `created_at` datetime NOT NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  KEY `ix_stock_movements_created_by` (`created_by`),
  KEY `ix_stock_movements_order_id` (`order_id`),
  KEY `ix_stock_movements_product_id_created_at` (`product_id`,`created_at`),
  CONSTRAINT `fk_stock_movements_created_by_users` FOREIGN KEY (`created_by`) REFERENCES `users` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `fk_stock_movements_order_id_sales_orders` FOREIGN KEY (`order_id`) REFERENCES `sales_orders` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `fk_stock_movements_product_id_products` FOREIGN KEY (`product_id`) REFERENCES `products` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `ck_stock_movements_change_not_zero` CHECK ((`quantity_change` <> 0)),
  CONSTRAINT `ck_stock_movements_movement_type_valid` CHECK ((`movement_type` in (_utf8mb4'opening',_utf8mb4'adjustment',_utf8mb4'sale',_utf8mb4'cancellation')))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `users` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(100) NOT NULL,
  `email` varchar(255) NOT NULL,
  `password_hash` varchar(255) NOT NULL,
  `role` varchar(10) NOT NULL,
  `created_at` datetime NOT NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_users_email` (`email`),
  CONSTRAINT `ck_users_role_valid` CHECK ((`role` in (_utf8mb4'admin',_utf8mb4'sales')))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

SET FOREIGN_KEY_CHECKS = 1;
