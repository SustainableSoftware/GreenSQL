# GreenSQL

## Restore zipped files

Some of the logs were too large to push to GitHub, so they are stored as zip files. Run the following commands from the root of the repository to unpack them:

```bash

cd runner/logs/query_outputs_dell && unzip "query_outputs_dell_part*.zip"
cd ../query_outputs_thinkpad && unzip "query_outputs_thinkpad_part*.zip"

cd runner/logs
unzip sigless.dell.CH1-0.zip
unzip sigless.dell.CH2-0.zip
unzip sigless.thinkpad.CH1-0.zip
unzip sigless.thinkpad.CH2-0.zip
```

The first two commands restore the saved query outputs for each laptop. The last four restore the raw power readings that the Sigless logger recorded from the Siglent supply.

## What is in the repository

| File or folder | What it is |
|---|---|
| `query_runner.c`, `rapl.c`, `rapl.h` | The runner. It executes the queries and reads the RAPL energy counter. |
| `Makefile` | Compiles the runner, sets up the database and has a target for each kind of run. |
| `queries/` | The 22 query files, which are 11 pairs of A and B. |
| `tpch_schema.sql`, `tpch_prep.sql` | The TPC-H schema, and the preparation that runs after loading (indexes, a helper table and a helper function). |
| `post_to_sigless.sh` | Sends start and end messages to the Sigless logger. |
| `temp_controlled_run.sh` | A small wrapper around the temperature-controlled make targets. |
| `run_supplementary.sh` | Runs the supplementary measurements one after another. |
| `query_timing.csv` | The main results file. Every normal run appends to it. |
| `logs/` | Output of the supplementary runs. |

## Setting up a Machine

### What you will need

You will need a Linux machine with an Intel processor that RAPL. We used Ubuntu Server 24.04.4 LTS. The code reads from the processor's model-specific registers. You will need a user with `sudo` rights, since the runner starts PostgreSQL clients as the `postgres` user and reads the RAPL registers as root. Plan for at least 6 GB of free disk for the database and the generated data, and additional space for the output logs. 

The following software is needed:
  - `build-essential`, `git`, `postgresql`, and `postgresql-contrib`. which make setup installs for you.
  - `perf` and `turbostat` from the kernel tools. Install these with `sudo apt install linux-tools-common linux-tools-$(uname -r)` .

RAPL is read through the `msr` kernel module, so it is important to load before anything else:

```bash 
sudo modprobe msr
```
To make sure RAPL works on your machine, run the following command. It should print numbers in Joules:

```bash
sudo perf stat -a -e power/energy-pkg/ -- sleep 1
```

For external measurements, a programmable DC supply is required, and a second computer to log it. We used a Siglent SPD3303X-E that powers the laptop in place of its normal AC adapter, and a logging PC on the same network running the Sigless logger.

### Installation 

From the `runner` folder, run the commands below. The first one asks for your sudo password and will take a few minutes to run as it is installing packages, downloads and builds the TPC-H data generator, generates the dataset, creates a database `tpch`, loads the data, and runs `tpch_prep.sql`. The second command compiles the runner.

```bash
make setup
make
```
Run `make setup` on a machine with a fresh database. It stops at the first SQL error, so if a `tpch` database already exists, it fails at `CREATE TABLE`. If you need different settings, you can override them on the command line> `TPCH_SCALE`, `TPCH_DBGEN_DIR`, `TPCH_DBGEN_REPO`, `PGUSER` (default `postgres`), and `PGDATABSE` (default `tpch`).

### What the setup creates

Other than the eight standard TPC-H tables, the setup builds a few other things that the queries need:
  - `lineitem2_unindexed`, an unindexed copy of `lineitem`. This is necessary for APX1225-queryA to run successfully.
  - The indexes `idx_lineitem_order`, `idx_orders_cust`, and `idx_customer_nation`, and a `CLUSTER` of `lineitem` on `idx_lineitem_order`.
  - The function `get_tax_rate()`, which PE017-queryA calls.
  - The index `idx_orders_clerk` on `order (o_clerk bpchar_pattern_ops)`, which APX1225-queryB uses.

If you already have a `tpch` database and only need these extras, run the preparation script by itself:

```bash
sudo -u postgres psql -d tpch -f tpch_prep.sql
```

### PostgresSQL versions and port
The runner connects to the default port 5432 and database `tpch`. The study used PostgreSQL 16.15 with default settings (`shared_buffers` at 128MB and `max_parallel_workers_per_gather` at 2). If other versions are installed, run `pg_lsclusters` and make sure that the 16 cluster is on port 5432.

## Verify the Installation
Check that the cluster is online on port 5432, and that the tbales have the expected number of rows. TPC-H at scale factor 1 should give 25, 5, 10000, 150000,  200000, 800000, 1500000, 6001215 rows in that order.

```bash 
pg_lsclusters                                   # the cluster used for the runs is online on port 5432

sudo -u postgres psql -d tpch -c "select (select count(*) from nation) nation, (select count(*) from region) region,
  (select count(*) from supplier) supplier, (select count(*) from customer) customer, (select count(*) from part) part,
  (select count(*) from partsupp) partsupp, (select count(*) from orders) orders,
  (select count(*) from lineitem) lineitem, (select count(*) from lineitem2_unindexed) lineitem2_unindexed"
```
Next, check that the temperature and energy tools work, and that the postgres user can read the query files:

```bash
sudo turbostat --quiet --show PkgTmp,PkgWatt --num_iterations 1 --interval 1   # prints a temperature
sudo perf stat -a -x, -e power/energy-pkg/,power/energy-cores/ -- sleep 1       # prints Joules
chmod 755 queries                               # the queries are read by the postgres user
```
Then, do a very short end-to-end test. This runs one query twice and writes to a temporary file, so it does not touch your real results.

```bash
sudo env QUERY_FILTER=PE002-queryA LOG_FILE=/tmp/trial.csv RUNS_PER_LOOP=2 ./query_runner
```
Before a long run, also check that AC power is connected by running `cat /sys/class/power_supply/AC*/online`. This should print 1. To check nothing else is running by using `cat /proc/loadavg`. It should be near 0 and there is enough free disk. 

## Running the experiments

### The main run

Each query file is executed 35 loops of 100 runs. The runner takes the files in sorted order and finishes all loops of one file before moving to the next. After every loop, it waits 15 seconds, so that the cleanup activity from on loop does not affect the next loop. 

To run everything with the external meter logging, call the runner directly. Replace `SIGLESS_HOST` with the address of the logging PC:

```bash
sudo env SIGLESS_ADDR=SIGLESS_HOST:8000 SIGLESS_CHANNEL=CH1 LOOPS=35 ./query_runner
```
To run just one guideline, you add a filter. The filter is a substring of the file name, so `APX1130` retrieves both the A and B files, while `APX1130-queryA` only retrieves one:

```bash
sudo env QUERY_FILTER=APX1130 LOOPS=35 ./query_runner
```

A full pass of all 22 files takes about 30-45 minutes depending on the processor, thus 35 loops takes about 18-26 hours. To start long runs in a way that survives the closing of the terminal, refer to the supplementary section below.

The runner does not prompt for a password. When it starts it refreshes sudo for itself, and if you ever see `Failed to prime sudo credentials` you can pass your password with `SUDO_PASSWORD=YOUR_PASSWORD`. Be aware that the password then ends up in your shell history.

### What occurs in each loop

For every loop, the runner does the follow in this order:
1. It tells the Sigless logger that the loop is starting, so the external readings can be matched to this loop.
2. It reads the RAPL package energy counter.
3. It runs the query 100 times in a row with `psql`, throwing the output away.
4. It reads the RAPL counter again.
5. It tells Sigless that the loop has ended.
6. It appends one row to `query_timing.csv` with the runtime and the RAPL energy.

The external energy is not calculated by the runner. This is calculated by adding up the power samples that Sigless recorded between the start and end messages of each loop. We run 100 executions per loop, since the supply only updates its readings about once per second, so a loop needs to last at least a few seconds to give a reliable energy figure.

### Settings you can change

You pass these as environment variables in front of the runner, as in the examples above.

| Variable | What it does | Default |
|---|---|---|
| `QUERY_FILTER` | Only run files whose name contains this text. `all` or empty means everything. | all |
| `QUERY_DIR` | Folder with the `.sql` files. | `queries` |
| `LOG_FILE` | The CSV file to append results to. | `query_timing.csv` |
| `LOOPS` | How many loops per query file. | 1 |
| `RUNS_PER_LOOP` | How many executions in each loop. | 100 |
| `SIGLESS_ADDR` | Address of the Sigless server, as host and port. | `127.0.0.1:8000` |
| `SIGLESS_CHANNEL` | Which supply channel to log to. | `CH1` |
| `SUDO_PASSWORD` | Only needed if the runner cannot refresh sudo by itself. | none |

If you only want the RAPL numbers and have no external meter, leave the Sigless settings alone. The runner still works when the server cannot be reached.

### What is logged in the CSV

Each row of `query_timing.csv` is one loop of one query file. The columns are:

`timestamp_utc, run_id, test_name, loop_index, loops, runs_per_loop, total_runs, total_elapsed_sec, failures, rapl_package_j, rapl_core_j, rapl_gpu_j, rapl_dram_j, query_dir, query_filter, sigless_addr, run_started_utc`

The energy columns are in Joules. The package and core columns are always filled in. The GPU and DRAM columns are only filled when rapl.c recognises the processor as one of a short list of older Intel models: Sandy Bridge, Ivy Bridge, and Haswell for the GPU, and the server versions of Sandy Bridge, Ivy Bridge, and Haswell for the DRAM. Other models are left empty, which from the code includes the two laptops in our study. 

One thing to be aware of is that the RAPL package counter wraps around when it reaches about 262,144J, which at 12-13W happens every 5-6 hours. The runner does not correct this, so every now and then a row has a negative `rapl_package_j`. When you see this, add 262,144J to it. If you want the exact number, it is two to the power 32 times the energy unit that the processor reports.

The `query_timing.csv` file can also contain rows from earlier query sets. Use the `run_id` and `run_started_utc` columns to isolate the rows from the run you are investigating.

### Logging the external power meter with Sigless

Sigless runs on the logging PC and records the readings of the Siglent power supply. At the start and end of every loop, the runner sends a short message with `post_to_sigless.sh`. The following is what these messages will look like:

```
start,run_id=...,test=APX1130-queryA.sql,loop=3/35,runs=100
end,run_id=...,test=APX1130-queryA.sql,loop=3/35,runs=100,elapsed_sec=...,failures=0
```
Before a log run, you should test that the connection works. The following command should print `{"status":"ok"}`:

```bash
sh ./post_to_sigless.sh SIGLESS_HOST:8000 CH1 "start,TEST,cpu"
```
The script is called as `post_to_sigless.sh HOST:PORT CHANNEL "MESSAGE"`. The address and channel may only contain letters, digits and the characters `. : _ -`. The runner never waits for the answer, so if the server is down, the run carries on and the CSV simply records the address that was used. If you want to try the whole thing without any hardware, you can start a simulated Sigless with `make sigless-sim-start SIGLESS_BIN=PATH_TO_SIGLESS SIGLESS_OUT=./sigless_test_out` and stop it again with `make sigless-sim-end`.

### Other runs

The Makefile has a tartget for each of the supplmentary measurements. Every "run-*" target compiles the runner first, refreshes the sudo with `SUDO_PASSWORD`, and then starts `sudo ./query_runner`. The Makefile ships a placeholder password, so either you pass your own on the command line or run `sudo -v` just before.

The `run`, `run-single`, `run-perf`, and `run-output-capture` targets ignore "LOOPS" and "RUNS_PER_LOOP". That is why the main run above calls the runner directly. The targets below do pass them on 

```bash
make  run-perf-detailed LOOPS=10

make run-temp-controlled LOOPS=10

make run-planning-time LOOPS=1 RUNS_PER_LOOP=10
```
There is one more target, which saves the complete output of each query. It ignores `LOOPS` and `RUNS_PER_LOOP` as well, but that does not matter, as it always does exactly one executions per query:

```bash
make run-output-capture 
```
Each of these has a `-single` version that takes a `QUERY` filter, for example `make run-temp-controlled-single QUERY=APX1090 LOOPS=5`. For the temperature controlled runs, there is also a small wrapper, `./temp_controlled_run.sh [QUERY][LOOPS]`, which selects the right target for you.

Each mode writes to its own log files. The names are set by variables at the top of the `Makefile`, such as `TEMP_CONTROL_LOG_FILE`, `TEMP_CONTROL_SAMPLE_DIR`, `SINGLE_CORE_LOG_FILE`, `DETAILED_PERF_OUTPUT_DIR`, `OUTPUT_CAPTURE_DIR`, and `PLANNING_TIME_LOG_FILE`. These runs append to existing CSVs, so give each campaign fresh names. `make clean` removes the compiled runner.

If several modes are switched at once, only one of them wins, in this order: planning time, then temperature control, then detailed perf, then output capture, then plain perf. The plain `run-perf` target only counts the "psql" client and not the PostgreSQL backend doing the work, so you must use `run-perf-detailed`, which measures the whole system.

## Supplementary runs

`run_supplementary.sh` strings the extra measurements together, so that you can start them once and leave the machine alone. It runs the phases one after another, never in parallel, and writes everything to new files with a machine label in the name. It refuses to start if any of those files already exist, so it can never overwrite or append to earlier results.

The phases are:

| Phase | What it measures | Default size |
|---|---|---|
| `planning` | Planning time from `EXPLAIN ANALYZE` | 10 executions per query |
| `output` | The full query output and its size | 1 execution per query |
| `temp` | One execution per loop, cooling to 40 °C or below between runs | 10 loops |
| `detailed` | Whole-system perf and turbostat sampling | 10 loops of 100 runs |

Everything lands in `logs/`, and the label you choose is part of each name, for example `planning_time_LABEL.csv` and `temp_controlled_runs_LABEL.csv`. The console output of each phase goes to `supplementary_LABEL_PHASE.out`, and overall progress goes to `supplementary_master_LABEL.out`. You can change the sizes with `LOOPS` and `PLANNING_RUNS`, pick phases with `PHASES`, and set the pause between phases in seconds with `PHASE_GAP_SEC` (the default is 300). The planning and output phases take minutes, the temperature phase about an hour, and the detailed phase by far the longest, around 5 to 9 hours.

A few details worth knowing:

- In the `temp` phase, the runner waits until the CPU package is below `TEMP_CONTROL_THRESHOLD_C` (default 40 °C) before each execution, with a minimum pause of 15 seconds.
- In the `output` phase, the runner removes `EXPLAIN ANALYZE` so the real result is returned. For APX1186-queryA, it uses a cursor loop that prints every row as a `NOTICE`.
- APX1186 has no planning time, because it has no `EXPLAIN ANALYZE`.

Before it starts, the script checks that you gave it a `MACHINE` label, that none of the output files exist yet, that the laptop is on AC power, that the load average is below 0.5, and that it can query the `tpch` database and `lineitem2_unindexed`. If any check fails it stops and tells you why.

To start a long run so that it survives logging out and keeps the laptop awake, use a command like the one below. Replace `LABEL` with a short name for the machine, for example `dell`. The `sh -c` wrapper is there so that the output redirection also runs as root, which matters when `logs/` is owned by root.

```bash
sudo -v

sudo env MACHINE=LABEL setsid nohup sh -c 'exec systemd-inhibit --what=sleep:idle:handle-lid-switch --why="query_runner supplementary" ./run_supplementary.sh > logs/supplementary_master_LABEL.out 2>&1' < /dev/null > /dev/null 2>&1 &
```

You can follow the progress at any time with `cat logs/supplementary_master_LABEL.out`. When it is done, you can copy everything to another computer, since all new files contain the label in their name. You may want to leave out the large `query_outputs_LABEL/` folder:

```bash
scp -r "USER@HOST:PROJECT_FOLDER/logs/*_LABEL*" LOCAL_LOGS_FOLDER/
```
