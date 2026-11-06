-- APX1092-queryB
EXPLAIN ANALYZE SELECT
    l_suppkey,
    SUM(l_quantity) AS total_quantity
FROM lineitem
WHERE l_suppkey > 500
GROUP BY l_suppkey
HAVING SUM(l_quantity) > 15000;