-- APX1090-queryB
EXPLAIN ANALYZE SELECT
    l_orderkey,
    l_partkey,
    l_suppkey,
    l_linenumber,
    l_shipdate
FROM lineitem
WHERE l_shipdate >= DATE '1998-01-01';