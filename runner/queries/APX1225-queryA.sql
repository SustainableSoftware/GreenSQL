-- APX1225-queryA
EXPLAIN ANALYZE SELECT
    l_orderkey,
    SUM(l_extendedprice) AS total_price
FROM lineitem2_unindexed
WHERE l_orderkey BETWEEN 100000 AND 200000
GROUP BY l_orderkey;