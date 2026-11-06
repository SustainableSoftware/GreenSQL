-- APX1145-queryB
EXPLAIN ANALYZE SELECT
    l_orderkey,
    l_comment
FROM lineitem
WHERE l_comment LIKE 'special%';