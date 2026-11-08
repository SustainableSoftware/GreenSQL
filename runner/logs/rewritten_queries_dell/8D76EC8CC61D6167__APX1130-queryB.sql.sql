SELECT
    l_orderkey,
    l_shipmode,
    l_extendedprice
FROM lineitem
WHERE l_shipmode IN ('AIR', 'FOB', 'MAIL', 'REG AIR', 'TRUCK');