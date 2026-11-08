DO $$
DECLARE
    rec RECORD;
    cur_lineitems CURSOR FOR
        SELECT l_orderkey, l_extendedprice
        FROM lineitem
        WHERE l_extendedprice > 100000;
BEGIN
    OPEN cur_lineitems;
    LOOP
        FETCH cur_lineitems INTO rec;
        EXIT WHEN NOT FOUND;

        RAISE NOTICE 'Order: %, Price: %', rec.l_orderkey, rec.l_extendedprice;
    END LOOP;
    CLOSE cur_lineitems;
END $$;
