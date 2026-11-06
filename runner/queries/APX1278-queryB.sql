-- APX1278-queryB
EXPLAIN ANALYZE SELECT EXISTS (
    SELECT 1
    FROM lineitem
    WHERE l_discount > 0.05);