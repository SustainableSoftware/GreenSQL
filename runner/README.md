# Query energy/timing runner

`query_runner` runs every SQL file in `queries/` against a PostgreSQL `tpch` database (TPC-H, scale
factor 1) and writes one CSV row per file per loop with the elapsed time and RAPL energy
(package/core/GPU/DRAM). Optional modes add `perf`, `turbostat`, interval RAPL sampling, temperature
gating, query-output capture and planning-time logging.

Queries come in A/B pairs (`<ID>-queryA.sql`, `<ID>-queryB.sql`): A uses the pattern a SQL guideline
warns against, B the recommended alternative. Both return identical rows. There are 11 pairs (22 files):
APX1090, APX1092, APX1130, APX1145, APX1173, APX1186, APX1225, APX1278, PE002, PE017, PE019. All files
start with `EXPLAIN ANALYZE` except APX1186 (a cursor `DO` block).

---

## 1. Setting up a machine

### 1.1 Requirements

- Linux (tested on Ubuntu) on an **Intel CPU with RAPL** (`sudo perf stat -a -e power/energy-pkg/ -- sleep 1`
  must print Joules).
- A user with `sudo`. The runner is started with `sudo` (RAPL and `perf` need root) and runs the queries with
  `sudo -u postgres psql`.
- Internet access during setup (apt packages, and `git clone` of tpch-dbgen).
- About 6 GB of free disk for the database plus the generated data files, more for logs
  (a full supplementary campaign writes about 1.5 GB, almost all query-output files).
- Packages: `build-essential git postgresql postgresql-contrib` (installed by `make setup`) and the kernel
  tools that provide `perf` and `turbostat` (Ubuntu: `sudo apt install linux-tools-common linux-tools-$(uname -r)`).
- Plug in AC power and prevent sleep for long runs (section 4.3).

### 1.2 One-time setup

Run this from the project folder in a normal terminal (it calls `sudo`, which will prompt for your password):

```bash
make setup     # apt packages, clone + build tpch-dbgen, generate SF1 data, create DB "tpch",
               # load schema + data, run tpch_prep.sql (takes a few minutes)
make           # = make compile -> ./query_runner (gcc -O2, needs rapl.c)
```

`make setup` needs a **fresh database**: it stops at the first SQL error (`ON_ERROR_STOP`), so running it
again on an existing `tpch` database fails at `CREATE TABLE`. Settings can be overridden on the command
line: `TPCH_SCALE`, `TPCH_DBGEN_DIR`, `TPCH_DBGEN_REPO`, `PGUSER`, `PGDATABASE`.

What it creates in the `tpch` database (`tpch_prep.sql` runs last):

- the eight TPC-H tables (`tpch_schema.sql`), loaded from the `dbgen` output,
- `lineitem2_unindexed`, a copy of `lineitem` without indexes (used by APX1225-queryA; **that query fails
  without it**),
- indexes `idx_lineitem_order`, `idx_orders_cust`, `idx_customer_nation`, and `CLUSTER lineitem USING idx_lineitem_order`,
- the function `get_tax_rate()` (used by one query),
- `idx_orders_clerk ON orders (o_clerk bpchar_pattern_ops)` (used by APX1145-queryB; `o_clerk` is `char(15)`, so
  the operator class is `bpchar_pattern_ops`).

To add only the prep to an existing database: `sudo -u postgres psql -d tpch -f tpch_prep.sql`.

### 1.3 PostgreSQL version and port

The runner connects to the **default port (5432)** and database `tpch`. The original study used
**PostgreSQL 16 with default settings** (`shared_buffers` 128MB, `max_parallel_workers_per_gather` 2). If other
PostgreSQL versions are installed, make sure the 16 cluster is the one on 5432 (`pg_lsclusters`) and that
it has not been tuned, otherwise results are not comparable.

### 1.4 Verify the installation

```bash
pg_lsclusters                                   # the cluster used for the runs is online on port 5432
sudo -u postgres psql -d tpch -c "select (select count(*) from nation) nation, (select count(*) from region) region,
  (select count(*) from supplier) supplier, (select count(*) from customer) customer, (select count(*) from part) part,
  (select count(*) from partsupp) partsupp, (select count(*) from orders) orders,
  (select count(*) from lineitem) lineitem, (select count(*) from lineitem2_unindexed) lineitem2_unindexed"
# expect: 25, 5, 10000, 150000, 200000, 800000, 1500000, 6001215, 6001215
sudo turbostat --quiet --show PkgTmp,PkgWatt --num_iterations 1 --interval 1   # prints a temperature
sudo perf stat -a -x, -e power/energy-pkg/,power/energy-cores/ -- sleep 1       # prints Joules
chmod 755 queries                               # the queries are read by the postgres user
```

Quick end-to-end test that writes nothing to the real logs:

```bash
sudo env QUERY_FILTER=PE002-queryA LOG_FILE=/tmp/trial.csv RUNS_PER_LOOP=2 ./query_runner
```

Before a long run also check: AC power connected (`cat /sys/class/power_supply/AC*/online` prints 1), nothing else
running (`cat /proc/loadavg` near 0) and enough free disk.

---

## 2. Make targets

All `run-*` targets compile first, prime sudo with `SUDO_PASSWORD` (default `a`; change it in the Makefile or on
the command line) and run `sudo ./query_runner`. `QUERY` is a **substring** match on the file name
(`QUERY=APX1130` runs A and B; `QUERY=APX1130-queryA` runs one file; there is no OR).

| Goal | Command |
|---|---|
| All queries (main log, 1 loop of 100 runs) | `make run` / `make run-single QUERY=APX1130` |
| Pinned to one logical CPU (+ interval RAPL, perf, turbostat) | `make run-single-core CPU_AFFINITY=0 LOOPS=10` |
| Interval perf + turbostat (system-wide) | `make run-perf-detailed LOOPS=10` / `run-perf-detailed-single QUERY=...` |
| Cooldown between runs (1 run per loop, 1 ms RAPL) | `make run-temp-controlled LOOPS=10` / `run-temp-controlled-single QUERY=... LOOPS=5` |
| Save full query output (1 run per query) | `make run-output-capture` / `run-output-capture-single QUERY=...` |
| Planning time from `EXPLAIN ANALYZE` | `make run-planning-time LOOPS=1 RUNS_PER_LOOP=10` / `run-planning-time-single QUERY=...` |
| `perf stat` per run (**not recommended**, see 5.2) | `make run-perf` / `run-perf-single QUERY=...` |

`LOOPS` and `RUNS_PER_LOOP` (default 100) are passed through by `run-single-core`, `run-perf-detailed`,
`run-planning-time` and `run-temp-controlled` (which forces 1 run per loop). `run`, `run-single`, `run-perf` and
`run-output-capture` do **not** pass them: for N loops of the main run call the runner directly (section 3).

Each mode writes to its own log files, set by Makefile variables such as `TEMP_CONTROL_LOG_FILE`,
`TEMP_CONTROL_SAMPLE_DIR`, `SINGLE_CORE_LOG_FILE`, `DETAILED_PERF_OUTPUT_DIR`, `OUTPUT_CAPTURE_DIR`,
`PLANNING_TIME_LOG_FILE` (see the top of `Makefile`). Targets **append** to existing CSVs, so give each campaign
fresh names (section 4). `temp_controlled_run.sh [QUERY] [LOOPS]` and `run_single_core.sh [QUERY] [CPU] ...` are
thin wrappers around the make targets.

---

## 3. Main run (N loops of 100 runs)

The runner goes file by file in sorted order and does all N loops of a file before the next file, with a 15 s
pause between loops and between files. One CSV row (`query_timing.csv`) per file per loop.

```bash
# full suite, 22 files, 35 loops
sudo env SUDO_PASSWORD=a SIGLESS_ADDR=<sigless-host>:8000 SIGLESS_CHANNEL=CH1 LOOPS=35 ./query_runner

# a subset: QUERY_FILTER=APX1130 (one group), or QUERY_DIR=<folder with copies of some files>
sudo env SUDO_PASSWORD=a QUERY_FILTER=APX1130 LOOPS=35 ./query_runner
```

Time per full pass of 22 files x 100 runs is about 30 to 45 minutes depending on the CPU, so 35 loops take
roughly 19 to 27 hours. Start long runs under `nohup`/`setsid` (section 4.3). `query_timing.csv` may contain
rows from earlier query sets: always filter by `run_id` / `run_started_utc`.

| Variable | Meaning | Default |
|---|---|---|
| `QUERY_FILTER` | substring match on file name (`all` or empty = everything) | all |
| `QUERY_DIR` | directory of `.sql` files | `queries` |
| `LOG_FILE` | CSV to append to | `query_timing.csv` |
| `LOOPS` / `RUNS_PER_LOOP` | loops per query / executions per loop | 1 / 100 |
| `SIGLESS_ADDR`, `SIGLESS_CHANNEL` | Sigless server `host:port` and channel | `127.0.0.1:8000`, `CH1` |
| `CPU_AFFINITY` | pin runner and PostgreSQL to one logical CPU (`-1` = off) | off |
| `SUDO_PASSWORD` | used by the runner to prime sudo | none |

Mode switches (`PERF_ENABLE`, `OUTPUT_CAPTURE_ENABLE`, `DETAILED_PERF_ENABLE`, `TEMP_CONTROL_ENABLE`,
`RAPL_SAMPLE_ENABLE`, `PLANNING_TIME_ENABLE`) are read at the top of `main()` in `query_runner.c`. When several
are set the priority is planning > temp-control > detailed perf > output capture > perf.

### Sigless (external energy meter, optional)

For every loop of every file the runner posts `start,...` / `end,...` to a Sigless server
(`POST http://<addr>/api/log`, via `post_to_sigless.sh`). Posts are fire-and-forget: if the server is unreachable
the run still completes and the CSV still records the address. Test the connection first; it should print
`{"status":"ok"}`:

```bash
sh ./post_to_sigless.sh <sigless-host>:8000 CH1 "start,TEST,cpu"
```

Only letters, digits and `. : _ -` are accepted in the address and channel. Runs that do not need the external
meter can use the default `127.0.0.1:8000`. A simulator can be used for testing:
`make sigless-sim-start SIGLESS_BIN=<path-to-sigless> SIGLESS_OUT=./sigless_test_out`, then `make sigless-sim-end`.

### Output columns (`query_timing.csv`)

`timestamp_utc, run_id, test_name, loop_index, loops, runs_per_loop, total_runs, total_elapsed_sec, failures,
rapl_package_j, rapl_core_j, rapl_gpu_j, rapl_dram_j, query_dir, query_filter, sigless_addr, run_started_utc`

**RAPL counter wrap:** the package counter wraps at 262,143.33 J (about every 6 h at 12 W) and `rapl.c` does
not handle it, so an occasional row has a negative `rapl_package_j`. Add 262,143.33 J to any negative value.

---

## 4. Supplementary analysis runs

`run_supplementary.sh` runs the extra configurations one after another (never in parallel on the same machine)
and writes everything to **new** files with a machine label in the name. It refuses to start if any target file
already exists, so nothing is appended to earlier logs.

### 4.1 Phases

| Phase | Command it runs | Default count | Output (in `logs/`, `<m>` = machine label) |
|---|---|---|---|
| planning | `run-planning-time` | 10 executions per query | `planning_time_<m>.csv` |
| output | `run-output-capture` | 1 execution per query | `query_outputs_<m>/`, `rewritten_queries_<m>/`, `query_output_sizes_<m>.csv` |
| temp | `run-temp-controlled` | 10 loops, 1 run each, cool to <= 40 C | `temp_controlled_runs_<m>.csv`, `temp_controlled_samples_<m>/` |
| single | `run-single-core CPU_AFFINITY=0` | 10 loops x 100 runs | `query_timing_single_core_<m>.csv`, `single_core_perf_runs_<m>.csv`, `single_core_perf_runs_<m>/`, `single_core_rapl_samples_<m>/` |
| detailed | `run-perf-detailed` | 10 loops x 100 runs | `detailed_perf_runs_<m>.csv`, `detailed_perf_runs_<m>/` |

Console output of each phase goes to `supplementary_<m>_<phase>.out`, overall progress to
`supplementary_master_<m>.out`. Override with `LOOPS=`, `PLANNING_RUNS=`, `PHASES="planning output temp single
detailed"`, `PHASE_GAP_SEC=300` (cool-down between phases).

Rough duration of all phases at 10 loops: 12 to 19 hours depending on the CPU (single and detailed take about
5 to 9 hours each, temp about 1 hour, planning and output minutes). Single and detailed scale linearly with `LOOPS`.

### 4.2 Pre-flight checks done by the script

It aborts if `MACHINE` is not set, if any output path exists, if the machine is not on AC power, if the load
average is above 0.5, or if `tpch` / `lineitem2_unindexed` cannot be queried.

### 4.3 Starting it

`MACHINE` is a short label for the machine (for example its model name) and ends up in every file name. This keeps
the laptop awake and survives logout:

```bash
echo <sudo-password> | sudo -S -v
sudo env MACHINE=<label> setsid nohup sh -c 'exec systemd-inhibit --what=sleep:idle:handle-lid-switch --why="query_runner supplementary" ./run_supplementary.sh > logs/supplementary_master_<label>.out 2>&1' < /dev/null > /dev/null 2>&1 &
```

(The `sh -c` wrapper makes the redirection run as root, which is needed when `logs/` is root-owned.) Progress:
`cat logs/supplementary_master_<label>.out`.

### 4.4 Copying results to another computer

All new files contain the label in their name. From the computer that will keep them, for example:

```bash
scp -r "<user>@<host>:<project-folder>/logs/*_<label>*" <local-logs-folder>/
```

(In PowerShell quote both paths.) Skip the large `query_outputs_<label>/` folder if the output files are not needed.

### 4.5 Notes for the analysis

- **Single-core pins PostgreSQL.** With `CPU_AFFINITY` the runner restarts the `postgresql` service, pins the
  postmaster of the cluster on port 5432 with `taskset` (backends inherit it), and restarts the service again at
  the end. `supplementary_<m>_single.out` should show `new affinity list: 0`. Parallel queries are expected to
  slow down (for example APX1145-A).
- **Detailed perf files span loops.** Files are `<run_id>__<query>.perf.csv` / `.turbostat.csv` without a loop
  number, so all loops of a query are concatenated; the interval counter restarts at 1.0 in each loop. Single-core
  RAPL samples are one file per loop (`..._loop<N>_run1.rapl.csv`).
- **Perf events:** the detailed modes use the runner's default 12 events (cycles, instructions, branches,
  branch-misses, cache-references, cache-misses, context-switches, cpu-migrations, page-faults, ref-cycles,
  cpu-clock, task-clock).
- **APX1186 has no planning time** (no `EXPLAIN ANALYZE`; `planning_time_ms` is empty).
- **Output capture** strips `EXPLAIN ANALYZE` and runs the query; APX1186-queryA is replaced by a cursor loop that
  prints each row as a `NOTICE`.
- Single-core, temp-controlled and detailed logs from before the query changes in section 5.1 are not comparable
  for APX1130 and APX1145.

---

## 5. Background

### 5.1 Query replacements: APX1130 and APX1145

In the original pairs A and B returned different row counts, so an energy difference could not be attributed to
the guideline. Both pairs were replaced with ones that return exactly the same rows (the old files are in
`queries_replaced_backup/`).

| Query | Old A / B | New A / B |
|---|---|---|
| APX1130 (not-equal operator) | `l_shipmode <> 'SHIP' OR l_shipmode <> 'RAIL'` (all rows) / `= 'SHIP' OR = 'RAIL'` | `l_shipmode <> 'SHIP' AND l_shipmode <> 'RAIL'` / `l_shipmode IN ('AIR','FOB','MAIL','REG AIR','TRUCK')` |
| APX1145 (leading `%` in LIKE) | `lineitem.l_comment LIKE '%special%'` / `LIKE 'special%'` | `orders.o_clerk LIKE '%Clerk#00000095%'` / `LIKE 'Clerk#00000095%'` |

Equivalence: TPC-H columns are `NOT NULL`, `l_shipmode` has exactly 7 values, and `Clerk#` only occurs at the
start of `o_clerk`. Verified with identical row counts (APX1130: 4,286,695; APX1145: 14,915) and `EXCEPT ALL` in
both directions returning 0 rows.

APX1092-queryA/B: the `HAVING` threshold was changed from `SUM(l_quantity) > 30000` to `> 15000` (with 30000
both returned 0 rows; with 15000 both return 6,311 rows).

Why the B forms differ in cost: APX1130-B (`= ANY('{...}')` over 5 values) is searched linearly, about 3.6
comparisons per row against 1.9 for the short-circuiting `AND` of two `<>`; APX1145-B uses a bitmap index scan on
one process, while A can only do a parallel sequential scan on three.

### 5.2 Runner and Makefile changes

- **Pinning:** `pin_postgres_to_cpu` used `pgrep ... | head -1`, the lowest PID, which on a machine with several
  clusters can be a cluster other than the one the runner queries. It now looks up the version serving port 5432
  with `pg_lsclusters` and pins that postmaster (falling back to the old behaviour).
- **Planning-time mode** (`PLANNING_TIME_ENABLE`, `make run-planning-time*`).
- **`LOOPS` / `RUNS_PER_LOOP`** are passed through by the single-core, perf-detailed and planning targets.
- **`make setup`** now makes the generated `.tbl` files readable by the `postgres` user (`dbgen` writes
  `nation.tbl` unreadable, so the `nation` table loaded empty without an error) and stops on the first SQL error.
- **`run-perf` is not used.** It runs `perf stat` **without `-a`**, so it only counts the `psql` client, not the
  PostgreSQL backend that does the work: for APX1090-A over 100 runs it recorded 13.4 G cycles against 328 G
  system-wide in the detailed run. `run-perf-detailed` measures the whole system with the same events plus
  temperature, frequency and power from `turbostat`, so it replaces it.
- `SIGLESS_ADDR` / `SIGLESS_CHANNEL` can be set by environment (defaults unchanged).
- `run_supplementary.sh` added (section 4).

### 5.3 Files in this folder

| File | Purpose |
|---|---|
| `query_runner.c`, `rapl.c`, `rapl.h`, `Makefile` | runner source and build/run targets |
| `queries/` | the 22 query files; `queries_replaced_backup/` has replaced/original versions |
| `tpch_schema.sql`, `tpch_prep.sql`, `tpch-dbgen/` | schema, post-load prep (indexes, helper table/function), data generator |
| `run_supplementary.sh` | sequential supplementary campaign (section 4) |
| `temp_controlled_run.sh`, `run_single_core.sh`, `post_to_sigless.sh` | wrappers / Sigless poster |
| `query_timing.csv` | main log (appended by every normal run) |
| `logs/` | logs of the supplementary runs |

The runner source differs from the original GitHub repo head
(https://github.com/mkmason/sql-energy-optimization) by the changes in 5.2.
