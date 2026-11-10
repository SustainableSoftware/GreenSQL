-- APX1130-queryA
EXPLAIN ANALYZE SELECT
    l_orderkey,
    l_shipmode,
    l_extendedprice
FROM lineitem
WHERE l_shipmode <> 'SHIP'
  AND l_shipmode <> 'RAIL';