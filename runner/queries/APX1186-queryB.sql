-- APX1186-queryB
SELECT
    l_orderkey,
    l_extendedprice
FROM lineitem
WHERE l_extendedprice > 100000;