-- APX1092-queryA
EXPLAIN ANALYZE SELECT
    l_suppkey,
    SUM(l_quantity) AS total_quantity
FROM lineitem
GROUP BY l_suppkey
HAVING l_suppkey > 500 AND SUM(l_quantity) > 15000;