#!/usr/bin/env bash
# Supplementary analysis runs, one phase after another (never in parallel on the same laptop).
#
# Usage (as the normal user; keeps the laptop awake while it runs):
#   sudo systemd-inhibit --what=sleep:idle:handle-lid-switch --why="query_runner supplementary" \
#       nohup ./run_supplementary.sh > logs/supplementary_master.out 2>&1 &
#
# Env overrides:
#   MACHINE=dell|thinkpad                           REQUIRED, goes into every output name
#   PHASES="planning output temp single detailed"   which phases, in this order
#   LOOPS=10                                        loops for temp/single/detailed
#   PLANNING_RUNS=10                                EXPLAIN ANALYZE executions per query (planning)
#   PHASE_GAP_SEC=300                               cool-down between phases
#
# perf (make run-perf) is intentionally NOT a phase: `perf stat` there has no -a, so it only counts the
# psql client (~5% of the cycles of the query); run-perf-detailed measures the whole system instead.
set -u
cd "$(dirname "${BASH_SOURCE[0]}")"

PHASES="${PHASES:-planning output temp single detailed}"
LOOPS="${LOOPS:-10}"
PLANNING_RUNS="${PLANNING_RUNS:-10}"
PHASE_GAP_SEC="${PHASE_GAP_SEC:-300}"
M="${MACHINE:-}"   # "dell" or "thinkpad": put in every output file/dir name so each run writes to fresh files
case "$M" in dell|thinkpad) ;; *) echo "ERROR: set MACHINE=dell or MACHINE=thinkpad"; exit 1 ;; esac
L=logs

stamp() { date -u +%Y-%m-%dT%H:%M:%SZ; }

# preflight: every target file/dir must not exist yet (clean start)
for f in $L/planning_time_$M.csv $L/query_outputs_$M $L/rewritten_queries_$M $L/query_output_sizes_$M.csv \
         $L/temp_controlled_runs_$M.csv $L/temp_controlled_samples_$M $L/query_timing_single_core_$M.csv \
         $L/single_core_rapl_samples_$M $L/single_core_perf_runs_$M $L/single_core_perf_runs_$M.csv \
         $L/detailed_perf_runs_$M $L/detailed_perf_runs_$M.csv; do
    [ -e "$f" ] && { echo "ERROR: $f already exists, refusing to append"; exit 1; }
done
# preflight: AC power, nothing else heavy running, DB reachable
ac=$(cat /sys/class/power_supply/AC*/online 2>/dev/null | head -1)
[ "${ac:-1}" = "1" ] || { echo "ERROR: not on AC power"; exit 1; }
load=$(cut -d' ' -f1 /proc/loadavg)
awk -v l="$load" 'BEGIN{exit !(l>0.5)}' && { echo "ERROR: load average $load > 0.5, something else is running"; exit 1; }
sudo -n -u postgres psql -d tpch -Atc "select count(*) from lineitem2_unindexed" >/dev/null 2>&1 \
    || { echo "ERROR: cannot query tpch (or lineitem2_unindexed missing)"; exit 1; }

run_phase() {
    local name="$1"; shift
    echo "[$(stamp)] ===== phase $name: $*"
    "$@" > "logs/supplementary_${M}_${name}.out" 2>&1
    local rc=$?
    echo "[$(stamp)] ===== phase $name finished, exit code $rc"
    return $rc
}

for p in $PHASES; do
    case "$p" in
        planning) run_phase planning make run-planning-time PLANNING_TIME_LOG_FILE=$L/planning_time_$M.csv LOOPS=1 RUNS_PER_LOOP="$PLANNING_RUNS" ;;
        output)   run_phase output   make run-output-capture OUTPUT_CAPTURE_DIR=$L/query_outputs_$M OUTPUT_CAPTURE_SQL_DIR=$L/rewritten_queries_$M OUTPUT_CAPTURE_LOG_FILE=$L/query_output_sizes_$M.csv ;;
        temp)     run_phase temp     make run-temp-controlled TEMP_CONTROL_LOG_FILE=$L/temp_controlled_runs_$M.csv TEMP_CONTROL_SAMPLE_DIR=$L/temp_controlled_samples_$M LOOPS="$LOOPS" ;;
        single)   run_phase single   make run-single-core CPU_AFFINITY=0 SINGLE_CORE_LOG_FILE=$L/query_timing_single_core_$M.csv SINGLE_CORE_SAMPLE_DIR=$L/single_core_rapl_samples_$M SINGLE_CORE_DETAILED_PERF_OUTPUT_DIR=$L/single_core_perf_runs_$M SINGLE_CORE_DETAILED_PERF_LOG_FILE=$L/single_core_perf_runs_$M.csv LOOPS="$LOOPS" ;;
        detailed) run_phase detailed make run-perf-detailed DETAILED_PERF_OUTPUT_DIR=$L/detailed_perf_runs_$M DETAILED_PERF_LOG_FILE=$L/detailed_perf_runs_$M.csv LOOPS="$LOOPS" ;;
        *) echo "unknown phase $p"; continue ;;
    esac
    echo "[$(stamp)] cooling down ${PHASE_GAP_SEC}s"; sleep "$PHASE_GAP_SEC"
done
echo "[$(stamp)] all phases done"
