-- APX1145-queryA
EXPLAIN ANALYZE SELECT
    l_orderkey,
    l_comment
FROM lineitem
WHERE l_comment LIKE '%special%';