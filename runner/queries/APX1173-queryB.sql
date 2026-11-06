-- APX1173-queryB
EXPLAIN ANALYZE SELECT
    l.l_orderkey,
    l.l_partkey,
    l.l_suppkey,
    l.l_extendedprice
FROM lineitem l
WHERE NOT EXISTS (
    SELECT s.s_suppkey
    FROM supplier s
    WHERE s.s_suppkey = l.l_suppkey
      AND s.s_acctbal < 0
);