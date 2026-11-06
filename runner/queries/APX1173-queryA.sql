-- APX1173-queryA
EXPLAIN ANALYZE SELECT
    l.l_orderkey,
    l.l_partkey,
    l.l_suppkey,
    l.l_extendedprice
FROM lineitem l
WHERE l.l_suppkey NOT IN (
    SELECT s.s_suppkey
    FROM supplier s
    WHERE s.s_acctbal < 0
);