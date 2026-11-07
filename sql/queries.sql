-- The five standalone report queries (MySQL 8).
-- Sales figures count confirmed orders only. Draft and cancelled orders are left out.
-- tests/test_sql_queries.py runs this file against the test database and checks each result.


-- 1. Top 3 customers by confirmed order grand total.
-- grand_total is stored on the order (after discount), so no join to the items is needed and
-- each order is counted once. Ties on total are broken by customer name.
SELECT c.id,
       c.name,
       COUNT(o.id)        AS confirmed_orders,
       SUM(o.grand_total) AS total_sales
FROM customers c
JOIN sales_orders o ON o.customer_id = c.id AND o.status = 'confirmed'
GROUP BY c.id, c.name
ORDER BY total_sales DESC, c.name
LIMIT 3;


-- 2. Top 3 products by quantity sold in confirmed orders.
-- Ties on quantity are broken by product code.
SELECT p.id,
       p.code,
       p.name,
       SUM(i.quantity) AS quantity_sold
FROM sales_order_items i
JOIN sales_orders o ON o.id = i.order_id AND o.status = 'confirmed'
JOIN products p ON p.id = i.product_id
GROUP BY p.id, p.code, p.name
ORDER BY quantity_sold DESC, p.code
LIMIT 3;


-- 3. Customers who have never placed any order.
-- "Any order" means any status: a customer with only a draft or a cancelled order HAS placed
-- an order, so they are not listed here.
SELECT c.id,
       c.name,
       c.email
FROM customers c
WHERE NOT EXISTS (
    SELECT 1 FROM sales_orders o WHERE o.customer_id = c.id
)
ORDER BY c.name;


-- 4. Month-wise confirmed sales totals, grouped by year and month (by order date).
-- Months with no confirmed orders don't appear.
SELECT YEAR(o.order_date)  AS order_year,
       MONTH(o.order_date) AS order_month,
       COUNT(*)            AS confirmed_orders,
       SUM(o.grand_total)  AS total_sales
FROM sales_orders o
WHERE o.status = 'confirmed'
GROUP BY YEAR(o.order_date), MONTH(o.order_date)
ORDER BY order_year, order_month;


-- 5. Active products with stock below a supplied threshold.
-- Change the number in the SET line, then run both lines together. "Below" means strictly
-- less than, so a product with exactly 10 in stock is not listed for a threshold of 10.
SET @threshold = 10;
SELECT p.id,
       p.code,
       p.name,
       p.stock_quantity
FROM products p
WHERE p.is_active = 1
  AND p.stock_quantity < @threshold
ORDER BY p.stock_quantity, p.code;
