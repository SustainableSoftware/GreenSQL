-- PE017-queryA
EXPLAIN ANALYZE SELECT
    l_orderkey,
    l_extendedprice
FROM lineitem
WHERE l_tax > get_tax_rate();