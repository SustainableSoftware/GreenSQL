-- APX1130-queryB
EXPLAIN ANALYZE SELECT
    l_orderkey,
    l_shipmode,
    l_extendedprice
FROM lineitem
WHERE l_shipmode = 'SHIP' OR l_shipmode = 'RAIL';