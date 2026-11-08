SELECT
    l_orderkey,
    SUM(l_extendedprice) AS total_price
FROM lineitem
WHERE l_orderkey BETWEEN 100000 AND 200000
GROUP BY l_orderkey;