-- APX1145-queryA
EXPLAIN ANALYZE SELECT
    o_orderkey,
    o_clerk
FROM orders
WHERE o_clerk LIKE '%Clerk#00000095%';