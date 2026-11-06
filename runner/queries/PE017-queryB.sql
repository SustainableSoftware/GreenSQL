-- PE017-queryB
EXPLAIN ANALYZE SELECT
    l_orderkey,
    l_extendedprice
FROM lineitem
WHERE l_tax > 0.07;