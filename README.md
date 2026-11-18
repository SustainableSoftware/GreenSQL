# GreenSQL


## Restore zipped files
cd runner/logs/query_outputs_dell && unzip "query_outputs_dell_part*.zip"

cd ../query_outputs_thinkpad && unzip "query_outputs_thinkpad_part*.zip"

cd runner/logs
unzip sigless.dell.CH1-0.zip
unzip sigless.dell.CH2-0.zip
unzip sigless.thinkpad.CH1-0.zip
unzip sigless.thinkpad.CH2-0.zip


Setting up a Machine

1. Requirements
  - This study uses Ubuntu Server 24.04.4 LTS on an Intel CPU with RAPL. To check this use the command "sudo perf stat -a -e power/energy-pkg/ -- sleep 1". The correct output is Joules.
  - As the tests run with sudo prefix, a sudo user is needed.
  - A clone of the github repository and the tpch-dbgen.
  - Hardware: A minimum of 6 GB of free disk for the database and generated data.
  - Packages: "build-essential git postgresql postgreswl-contrib" which can be installed by "make setup"; the kernel tools providing "perf" and "turbostat" use the command "sudo apt install linux-tools-common linux-tools-$(uname -r)
  - etc...

For the external measurement, a programmable DC supply is necessary. A Siglent SPD3303X-E was used to power the laptop in place of its AC adapter and a logging PC running the Sigless logger on the same LAN. 

1.2 Initial Setup (Initialization)
In the designated project folder in a terminal:
  "make setup    # apt packages, clone + build tpch-dbgen, generate SF1 data, create DB "tpch",   
                 # load schema + data, run tpch_prep.sql 
                 
  make           # = make compile -> ./query_runner (gcc -02, needs rapl.c)
  "
  "make setup" needs a fresh database: it stops at the first SQL error, so running it again on an existing "tpch" database fails at "CREATE TABLE". Settings can be overidden on the command line: "TPCH_SCALE (default 1), "TPCH_DBGEN_DIR", "TPCH_DBGEN_REPO", "PGUSER" (default postgres), "PGDATABASE" (default "tpch") 

  What is created in the "tpch" database:
    - the eight TPC-H tables ("tpch_schema.sql"), loaded from the "dbgen" output
    - "lineitem2_unindexed", a copy of "lineitem", without indexes for example APX1225-queryA
    - indexes "idx_lineitem_order", "idx_orders_cust", "idx_customer_nation", and "CLUSTER lineitem     USING idx_lineitem_order"
    - the function "get_tax_rate(), which is used by PE017-queryA.
    - "idx_orders_clerk ON orders ("o_clerk bpchar_pattern_ops"), which is used by APX1145-queryB

To add only the prep to an existing database: "sudo -u postgres psql -d tpch -f tpch_prep.sql".

1.3 PostgresSQL versions and port
The runner connects to the default port 5432 and database "tpch". The study used PostgreSQL 16.15 with default settings ("shared_buffers" 128MB, "max_parallel_workers_per_gather" 2). If other versions are installed, make sure the 16 cluster is the one on 5432 ("pg_lsclusters") and that it has not been tuned, otherwise results are not comparable.

1.4 Verify the Installation

bash 
pg_lsclusters                                   # the cluster used for the runs is online on port 5432
sudo -u postgres psql -d tpch -c "select (select count(*) from nation) nation, (select count(*) from region) region,
  (select count(*) from supplier) supplier, (select count(*) from customer) customer, (select count(*) from part) part,
  (select count(*) from partsupp) partsupp, (select count(*) from orders) orders,
  (select count(*) from lineitem) lineitem, (select count(*) from lineitem2_unindexed) lineitem2_unindexed"
# expect: 25, 5, 10000, 150000, 200000, 800000, 1500000, 6001215, 6001215
sudo turbostat --quiet --show PkgTmp,PkgWatt --num_iterations 1 --interval 1   # prints a temperature
sudo perf stat -a -x, -e power/energy-pkg/,power/energy-cores/ -- sleep 1       # prints Joules
chmod 755 queries                               # the queries are read by the postgres user

A quick end-to-end that does not write to the logs
bash
sudo env QUERY_FILTER=PE002-queryA LOG_FILE=/tmp/trial.csv RUNS_PER_LOOP=2 ./query_runner

Before a long run also check that AC power is connected by running "cat /sys/class/power_supply/AC*/online prints 1", nothing else is running by using "cat /proc/loadavg near 0" and there is enough free disk. 

2. Make
All "run-*" targets compile first, prime sudo with "SUDO_PASSWORD" and run "sudo ./query_runner". The Makefile ships a placeholder default for "SUDO_PASSWORD"; override it on the command line or edit the Makefile.

"LOOPS" and "RUNS_PER_LOOP" are passed through by "run-single-core", "run-perf-detailed", "run-planning-time" and "run-temp-controlled", which forces 1 run per loop. "run", "run-single", "run-perf" and "run-output-capture" do not pass them: for N loops of the main run call the runner directly.

"run-perf" runs "perf stat" without "-a", so it only counts the "psql" client and not the PostgreSQL backend doing the work. Use "run-perf-detailed", which measures the whole system.

Each mode writes to its own log files, set by Makefile variables such as "TEMP_CONTROL_LOG_FILE", "TEMP_CONTROL_SAMPLE_DIR", "SINGLE_CORE_LOG_FILE", "DETAILED_PERF_OUTPUT_DIR", "OUTPUT_CAPTURE_DIR" and "PLANNING_TIME_LOG_FILE". Targets append to existing CSVs, so give each campaign fresh names.

Other targets: "make clean" removes the binary; "make sigless-sim-start" / "sigless-sim-end" start and stop a Sigless simulator for testing.

Wrapper scripts
./temp_controlled_run.sh QUERY LOOPS runs run-temp-controlled, or run-temp-controlled-single when a query is given.
./run_single_core.sh QUERY CPU LOG_FILE SAMPLE_DIR RAPL_INTERVAL_MS PERF_DIR PERF_LOG PERF_INTERVAL_SEC runs run-single-core. Defaults: CPU 0, log logs/query_timing_single_core.csv, sample dir logs/single_core_rapl_samples, RAPL interval 100 ms, perf dir logs/single_core_perf_runs, perf log logs/single_core_perf_runs.csv, perf interval 1 s.

3. Main run, the N loops of 100 runs
This is the run used for the energy comparison in the paper: 35 loops of 100 executions per query variant. The runner goes file by file in sorted order and completes all N loops of a file before the next, with a 15 s pause between loops and between files. It writes one CSV row query_timing.csv per file per loop.

bash 
# full suite, 22 files, 35 loops, with the external meter logger
sudo env SUDO_PASSWORD=<sudo-password> SIGLESS_ADDR=<sigless-host>:8000 SIGLESS_CHANNEL=CH1 LOOPS=35 ./query_runner

# a subset: QUERY_FILTER=APX1130 (one group), or QUERY_DIR=<folder with copies of some files>
sudo env SUDO_PASSWORD=<sudo-password> QUERY_FILTER=APX1130 LOOPS=35 ./query_runner

A full pass of 22 files x 100 runs takes about 30 to 45 minutes depending on the CPU, so 35 loops take roughly 19 to 27 hours. Start long runs under nohup/setsid (section 4.3). query_timing.csv may contain rows from earlier query sets: filter by run_id / run_started_utc.


Sigless (external energy meter, optional)

For every loop of every file the runner posts start,... / end,... to a Sigless server (POST http://<addr>/api/log) using post_to_sigless.sh. Posts are fire-and-forget: if the server is unreachable the run still completes and the CSV still records the address. Test the connection first; it should print {"status":"ok"}:

bash 
sh ./post_to_sigless.sh <sigless-host>:8000 CH1 "start,TEST,cpu"
