"""Paper-figure style and plotting functions (IEEEtran sizes: column 3.5 in, full width 7.16 in).

Every figure of the paper is drawn by a function in this module; the notebooks only pass in their data frames and call it.
All figures are written as SVG to analysis/plots/ (cwd of the notebooks is analysis/).

One visual language, each colour / marker / line style has exactly ONE meaning:

  Variant A (guideline NOT followed)   blue    #1f77b4        Variant B (guideline followed)  orange  #ff7f0e
  Outcome of A -> B (significance)     green = significant, B lower;  red = significant, A lower;
                                       hollow grey marker / grey label = not significant
  Measurement source (only where External and RAPL share a panel)   External = dark grey,  RAPL = purple
  Machine                              PC1 ThinkPad = circle / solid,   PC2 Dell = square / hatched
  Runtime marker                       white diamond
  Rank agreement (rank-order figure)   teal = same rank in both orderings,  grey = different rank
  Guideline groups (band behind rows)  energy decrease (>20 % lower) = light green, negligible = light grey, energy increase = light red
  Reference lines                      dark grey (zero lines black); dashed = threshold / second condition

Notebook -> figure map: see analysis/README.md
"""
import json
from contextlib import contextmanager
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Rectangle
from scipy.stats import mannwhitneyu

COL_W, FULL_W = 3.5, 7.16
PLOTS = Path("plots")

VAR = {"A": "#1f77b4", "B": "#ff7f0e"}
GREEN, RED, GREY = "#2ca02c", "#d62728", "#7f7f7f"
GREEN_TXT, RED_TXT, GREY_TXT = "#1c7a1c", "#b01c1c", "#5f5f5f"
SRC = {"External": "#4d4d4d", "RAPL": "#9467bd"}
RANK_SAME, RANK_DIFF = "#2A9D8F", "#9E9E9E"
BAND = {0: "#e8f5e8", 1: "#f3f3f3", 2: "#fbeaea"}
GROUP_NAMES = {0: "Energy decrease", 1: "Negligible (|Δ| < 2 %)", 2: "Energy increase"}
REF = "#444444"
PC_NAME = {"PC_1": "PC1 (ThinkPad)", "PC_2": "PC2 (Dell)"}
PC_MARK = {"PC_1": "o", "PC_2": "s"}
PC_HATCH = {"PC_1": None, "PC_2": "//////"}
PCS = ["PC_1", "PC_2"]

RC = {"font.size": 6, "axes.labelsize": 6.5, "xtick.labelsize": 6, "ytick.labelsize": 6.5, "legend.fontsize": 5.6,
      "axes.linewidth": 0.6, "axes.titlesize": 6.5, "font.family": "DejaVu Sans"}


# ------------------------------------------------------------------ helpers
@contextmanager
def _style():
    """Draw inside matplotlib's DEFAULT style + RC, so a notebook-wide theme (e.g. seaborn 'whitegrid', which switches on
    horizontal grid lines) cannot leak into the paper figures."""
    with plt.style.context("default"), plt.rc_context(RC):
        yield


def save_svg(fig, name, out_dir=None):
    out = Path(out_dir) if out_dir else PLOTS
    out.mkdir(parents=True, exist_ok=True)
    path = out / (name if name.endswith(".svg") else f"{name}.svg")
    fig.savefig(path, format="svg", bbox_inches="tight", facecolor="white")
    print(f"Saved: {path}")
    return path


def guideline_groups(stats_df, metric="energy_external_j", large=-20.0, negligible=2.0):
    """Order guidelines by group (large reduction / negligible / increase), then by mean A->B change across PCs."""
    d = stats_df[stats_df["metric"] == metric].copy()
    d["chg"] = np.where(d["A_mean"] != 0, 100.0 * (d["B_mean"] - d["A_mean"]) / d["A_mean"], np.nan)
    mean_chg = d.groupby("query_family")["chg"].mean().dropna()
    grp = {f: (0 if v < large else (2 if v > negligible else 1)) for f, v in mean_chg.items()}
    order = sorted(mean_chg.index, key=lambda f: (grp[f], mean_chg[f]))
    return order, grp


def write_group_file(order, grp, path=None):
    """Share the row order with notebooks that do not compute the A/B statistics (planning time, ...)."""
    path = Path(path) if path else PLOTS / "guideline_groups.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"order": list(order), "group": {k: int(v) for k, v in grp.items()}}, indent=1))
    return path


def read_group_file(path=None):
    path = Path(path) if path else PLOTS / "guideline_groups.json"
    if not path.exists():
        return None, None
    d = json.loads(path.read_text())
    return d["order"], {k: int(v) for k, v in d["group"].items()}


def ypositions(order, grp, gap=0.9):
    y, last, pos = 0.0, None, {}
    for f in order:
        if last is not None and grp[f] != last:
            y += gap
        pos[f] = y
        y += 1.0
        last = grp[f]
    return pos


def draw_bands(ax, order, ypos, grp, x_left, fontsize=5.5, label=True):
    for g in (0, 1, 2):
        ys = [ypos[f] for f in order if grp[f] == g]
        if ys:
            ax.axhspan(min(ys) - .5, max(ys) + .5, color=BAND[g], zorder=0)
            if label:
                ax.text(x_left + .01 * abs(x_left), min(ys) - .56, GROUP_NAMES[g], fontsize=fontsize, fontweight="bold", color="#6b6b6b", va="bottom")


def despine(ax, sides=("top", "right")):
    for s in sides:
        ax.spines[s].set_visible(False)


def outcome_style(change, p):
    """(face, edge) of a marker: filled green / red when significant, hollow grey when not."""
    if p >= .05:
        return "white", GREY
    return (GREEN if change < 0 else RED), "black"


def _stat_lookup(stats_df):
    idx = stats_df.set_index(["pc", "query_family", "metric"])

    def row(pc, fam, metric):
        return idx.loc[(pc, fam, metric)]

    def pct(pc, fam, metric):
        r = row(pc, fam, metric)
        return 100.0 * (r["B_mean"] - r["A_mean"]) / r["A_mean"]
    return row, pct


def _paper_df(analysis_df):
    return analysis_df[analysis_df["variant"].isin(["QUERYA", "QUERYB"])].copy()


# ------------------------------------------------------------------ 1. forest (single column)
def forest(stats_df, metric="energy_external_j", source="External", name="ab_forest_energy_external_pct", zh=3.0):
    S, pct = _stat_lookup(stats_df)
    order, grp = guideline_groups(stats_df)
    order = [f for f in order if all((pc, f, metric) in stats_df.set_index(["pc", "query_family", "metric"]).index for pc in PCS)]
    ypos = ypositions(order, grp)
    small = [f for f in order if grp[f] == 1]
    vals = np.array([pct(pc, f, m) for pc in PCS for f in order for m in (metric, "runtime_sec")])
    x_lo, x_hi = min(vals.min(), -zh) - 8, max(vals.max(), zh) + 7
    off = {"PC_1": -.2, "PC_2": .2}

    def pair(ax, f, pc, y0, es=24, ds=9):
        e, t = pct(pc, f, metric), pct(pc, f, "runtime_sec")
        y = y0 + off[pc]
        ax.plot([t, e], [y, y], color="#9a9a9a", lw=1.0, solid_capstyle="round", zorder=2)
        fc, ec = outcome_style(e, S(pc, f, metric)["p_value"])
        ax.scatter(e, y, s=es, marker=PC_MARK[pc], fc=fc, ec=ec, lw=.7, zorder=4)
        ax.scatter(t, y, s=ds, marker="D", fc="white", ec="#222222", lw=.6, zorder=6)

    with _style():
        fig, ax = plt.subplots(figsize=(COL_W, .30 * len(order) + 1.4))        # about 4.7 in tall
        draw_bands(ax, order, ypos, grp, x_lo)
        for f in order:
            for pc in PCS:
                pair(ax, f, pc, ypos[f])
        ax.axvline(0, color="black", lw=.8, zorder=1)
        ax.set_xlim(x_lo, x_hi)
        ax.set_yticks([ypos[f] for f in order]); ax.set_yticklabels(order)
        ax.set_ylim(max(ypos.values()) + .75, -1.35)
        ax.grid(axis="x", ls=":", alpha=.5); ax.tick_params(axis="y", length=0)
        ax.set_xlabel("Change A → B (%)"); despine(ax)
        leg = [Line2D([], [], marker="o", ls="", mfc=GREEN, mec="black", ms=4.5, label="sig., B lower"),
               Line2D([], [], marker="o", ls="", mfc=RED, mec="black", ms=4.5, label="sig., A lower"),
               Line2D([], [], marker="o", ls="", mfc="white", mec=GREY, ms=4.5, label="not significant"),
               Line2D([], [], marker="o", ls="", mfc="#cccccc", mec="black", ms=4.5, label=f"{PC_NAME['PC_1']} {source} energy"),
               Line2D([], [], marker="s", ls="", mfc="#cccccc", mec="black", ms=4.5, label=f"{PC_NAME['PC_2']} {source} energy"),
               Line2D([], [], marker="D", ls="", mfc="white", mec="#222222", ms=3.4, label="runtime (same line, on top)")]
        fig.legend(handles=leg, loc="upper center", ncol=2, frameon=False, fontsize=5.6, bbox_to_anchor=(.5, 1.0),
                   columnspacing=1.0, handletextpad=.3, labelspacing=.35)
        fig.subplots_adjust(left=.15, right=.98, top=.905, bottom=.075)
        if small:                                                    # zoom inset on the negligible group
            fig.canvas.draw()
            ys = [ypos[f] for f in small]
            ymin, ymax = min(ys) - .5, max(ys) + .5
            mag = (x_hi - x_lo) / (2 * zh)
            xi_l, xi_r = x_lo + .05 * (x_hi - x_lo), -zh - .09 * (x_hi - x_lo)
            to_ax = lambda xy: ax.transAxes.inverted().transform(ax.transData.transform(xy))
            (a0, b0), (a1, b1) = to_ax((xi_l, ymax)), to_ax((xi_r, ymin))
            ins = ax.inset_axes([a0, b0, a1 - a0, b1 - b0]); ins.set_facecolor("white")
            for f in small:
                for pc in PCS:
                    pair(ins, f, pc, ypos[f], es=22, ds=8)
            ins.axvline(0, color="black", lw=.6, zorder=1); ins.set_xlim(-zh, zh); ins.set_ylim(ymax, ymin)
            ticks = list(range(-int(zh) + 1, int(zh)))
            ins.set_xticks(ticks); ins.set_xticklabels([f"{t:d}".replace("-", "−") for t in ticks], fontsize=5)
            ins.set_yticks([]); ins.grid(axis="x", ls=":", alpha=.5); ins.tick_params(axis="x", length=1.5, pad=1)
            for s_ in ins.spines.values():
                s_.set_visible(True); s_.set_edgecolor(REF); s_.set_linewidth(.7)
            ins.text(.02, .012, f"zoom ±{zh:g} % (×{mag:.0f})", transform=ins.transAxes, fontsize=5, va="bottom", ha="left", color=REF, fontweight="bold")
            ax.add_patch(Rectangle((-zh, ymin), 2 * zh, ymax - ymin, fill=False, ec=REF, lw=.8, zorder=7))
            for yy in (ymin, ymax):
                ax.plot([xi_r, -zh], [yy, yy], color=REF, lw=.6, ls=(0, (4, 3)), zorder=7)
        save_svg(fig, name)
        plt.show()


# ------------------------------------------------------------------ 2. mean % change, External vs RAPL (single column)
def mean_pct_bars(stats_df, name="ab_mean_pct_diff_energy"):
    S, pct = _stat_lookup(stats_df)
    order, grp = guideline_groups(stats_df)
    ypos = ypositions(order, grp)
    mm = {"External": "energy_external_j", "RAPL": "energy_rapl_j"}
    vals = np.array([pct(pc, f, m) for pc in PCS for f in order for m in mm.values()])
    lo, hi = min(vals.min(), 0), max(vals.max(), 0)
    span = hi - lo
    xlim = (lo - .17 * span, hi + .17 * span)
    slots, offs, k = {}, [-.33, -.11, .11, .33], 0
    for pc in PCS:
        for src in ("External", "RAPL"):
            slots[(pc, src)] = offs[k]; k += 1
    with _style():
        fig, ax = plt.subplots(figsize=(COL_W, .33 * len(order) + 1.6))        # about 5.2 in tall
        draw_bands(ax, order, ypos, grp, xlim[0])
        for f in order:
            for (pc, src), o in slots.items():
                r = S(pc, f, mm[src]); c = pct(pc, f, mm[src]); y = ypos[f] + o
                ax.barh(y, c, height=.19, color=SRC[src], edgecolor="#333", lw=.4, hatch=PC_HATCH[pc], zorder=3)
                col = GREY_TXT if r["p_value"] >= .05 else (GREEN_TXT if c < 0 else RED_TXT)
                ax.annotate(f"{c:+.1f}", (c, y), xytext=(2 if c >= 0 else -2, 0), textcoords="offset points",
                            ha="left" if c >= 0 else "right", va="center", fontsize=4.5, color=col, fontweight="bold")
        ax.axvline(0, color="black", lw=.8, zorder=4); ax.set_xlim(xlim)
        ax.set_yticks([ypos[f] for f in order]); ax.set_yticklabels(order); ax.set_ylim(max(ypos.values()) + .75, -1.35)
        ax.grid(axis="x", ls=":", alpha=.5); ax.tick_params(axis="y", length=0); ax.set_xlabel("Change in energy, A → B (%)"); despine(ax)
        h = [Patch(fc=SRC["External"], ec="#333", lw=.4, label="External"), Patch(fc=SRC["RAPL"], ec="#333", lw=.4, label="RAPL"),
             Patch(fc="white", ec="#333", lw=.4, label=f"{PC_NAME['PC_1']} (solid)"),
             Patch(fc="white", ec="#333", lw=.4, hatch="//////", label=f"{PC_NAME['PC_2']} (hatched)"),
             Patch(fc=GREEN_TXT, label="value label: sig., B lower"), Patch(fc=RED_TXT, label="value label: sig., A lower"),
             Patch(fc=GREY_TXT, label="value label: not significant")]
        fig.legend(handles=h, loc="upper center", ncol=2, frameon=False, fontsize=5.6, bbox_to_anchor=(.5, 1.0),
                   columnspacing=1.2, handlelength=1.4, labelspacing=.35)
        fig.subplots_adjust(left=.15, right=.98, top=.905, bottom=.07)
        save_svg(fig, name)
        plt.show()


# ------------------------------------------------------------------ 3. RAPL offset bars (single column)
def offset_bars(analysis_df, stats_df, name="rapl_energy_offset_bars"):
    d = _paper_df(analysis_df)
    d["off"] = 100 * (d["rapl_package_j"] - d["external_energy_j"]) / d["external_energy_j"]
    st = d.groupby(["pc", "query_family", "variant"])["off"].agg(["mean", "std"])
    pcm = d.groupby("pc")["off"].mean()
    order, grp = guideline_groups(stats_df)
    ypos = ypositions(order, grp)
    slots = {("PC_1", "QUERYA"): -.33, ("PC_1", "QUERYB"): -.11, ("PC_2", "QUERYA"): .11, ("PC_2", "QUERYB"): .33}
    xl = (min(-62, float((st["mean"] - st["std"]).min()) - 12), 0)
    with _style():
        fig, ax = plt.subplots(figsize=(COL_W, 5.0))
        draw_bands(ax, order, ypos, grp, xl[0])
        for f in order:
            for (pc, v), o in slots.items():
                m, s = st.loc[(pc, f, v)]
                ax.barh(ypos[f] + o, m, height=.19, color=VAR[v[-1]], edgecolor="#333", lw=.4, hatch=PC_HATCH[pc], zorder=3)
                ax.errorbar(m, ypos[f] + o, xerr=s, color="#222", lw=.4, capsize=.8, zorder=4)
                ax.annotate(f"{m:.1f}", (m - s, ypos[f] + o), xytext=(-2, 0), textcoords="offset points", ha="right", va="center", fontsize=4.6)
        for pc, ls in (("PC_1", ":"), ("PC_2", "-.")):
            ax.axvline(pcm[pc], color="k", lw=.7, ls=ls, zorder=5)
        ax.axvline(0, color="k", lw=.8, zorder=4)
        ax.set_xlim(xl); ax.set_yticks([ypos[f] for f in order]); ax.set_yticklabels(order); ax.set_ylim(max(ypos.values()) + .75, -1.35)
        ax.grid(axis="x", ls=":", alpha=.5); ax.tick_params(axis="y", length=0)
        ax.set_xlabel("RAPL energy offset from external (%)"); despine(ax)
        h = [Patch(fc=VAR["A"], ec="#333", lw=.4, label="Variant A"), Patch(fc=VAR["B"], ec="#333", lw=.4, label="Variant B"),
             Patch(fc="w", ec="#333", lw=.4, label=f"{PC_NAME['PC_1']} (solid)"),
             Patch(fc="w", ec="#333", lw=.4, hatch="//////", label=f"{PC_NAME['PC_2']} (hatched)"),
             Line2D([], [], color="k", ls=":", lw=.8, label=f"PC1 mean ({pcm['PC_1']:.1f} %)"),
             Line2D([], [], color="k", ls="-.", lw=.8, label=f"PC2 mean ({pcm['PC_2']:.1f} %)")]
        fig.legend(handles=h, loc="upper center", ncol=3, frameon=False, bbox_to_anchor=(.5, 1.0), columnspacing=1.0, handlelength=1.4)
        fig.subplots_adjust(left=.15, right=.98, top=.93, bottom=.06)
        save_svg(fig, name)
        plt.show()


# ------------------------------------------------------------------ 4. rank order (bars show RAPL energy, rows ordered by external)
def rank_tables(analysis_df):
    df = _paper_df(analysis_df)
    out = {}
    for pc in PCS:
        d = df[df["pc"] == pc].groupby(["query_family", "variant"])[["external_energy_j", "rapl_package_j"]].median().reset_index()
        d["label"] = d["query_family"] + "-" + d["variant"].str[-1]
        d["r_ext"] = d["external_energy_j"].rank(ascending=False, method="first").astype(int)
        d["r_rapl"] = d["rapl_package_j"].rank(ascending=False, method="first").astype(int)
        d["shift"] = d["r_rapl"] - d["r_ext"]
        out[pc] = d.sort_values("r_ext").reset_index(drop=True)
    return out


def rank_bars(analysis_df, layout="column", name=None):
    """layout: 'column' = horizontal bars, PCs stacked, one column (used in the paper);
               'side'   = horizontal bars, PCs next to each other, full width;
               'vertical' = vertical bars, PCs next to each other, full width."""
    R = rank_tables(analysis_df)
    leg = [Patch(fc=RANK_SAME, label="same rank in both orderings"), Patch(fc=RANK_DIFF, label="different rank (label: RAPL rank shift)")]
    ymax = max(R[p]["rapl_package_j"].max() for p in PCS)
    with _style():
        if layout == "vertical":
            fig, axes = plt.subplots(1, 2, figsize=(FULL_W, 2.6), sharey=True)
            for ax, pc in zip(axes, PCS):
                d = R[pc]
                ax.bar(range(len(d)), d["rapl_package_j"], color=[RANK_SAME if s == 0 else RANK_DIFF for s in d["shift"]], width=.75, edgecolor="none")
                for i, s in enumerate(d["shift"]):
                    if s:
                        ax.text(i, d["rapl_package_j"][i] + ymax * .01, f"{s:+d}", ha="center", va="bottom", fontsize=4.6)
                ax.set_xticks(range(len(d))); ax.set_xticklabels(d["label"], rotation=90, fontsize=4.8)
                ax.set_title(PC_NAME[pc], pad=2); ax.set_ylim(0, ymax * 1.08); ax.margins(x=.01); despine(ax)
            axes[0].set_ylabel("RAPL energy (J)")
            fig.legend(handles=leg, loc="upper center", ncol=2, frameon=False, bbox_to_anchor=(.5, 1.02))
            fig.tight_layout(rect=[0, 0, 1, .93])
            default = "energy_rapl_ordered_by_external_vertical"
        else:
            xmax = ymax * 1.22
            if layout == "side":
                fig, axes = plt.subplots(1, 2, figsize=(FULL_W, 3.9), sharex=True)
            else:
                fig, axes = plt.subplots(2, 1, figsize=(COL_W, 5.3), sharex=True)
            for ax, pc in zip(axes, PCS):
                d = R[pc]
                y = np.arange(len(d))
                ax.barh(y, d["rapl_package_j"], color=[RANK_SAME if s == 0 else RANK_DIFF for s in d["shift"]], height=.72, edgecolor="none")
                for i, (e, s) in enumerate(zip(d["rapl_package_j"], d["shift"])):
                    ax.text(e + xmax * .008, i, f"{e:,.0f}" + (f"  ({s:+d})" if s else ""), va="center", ha="left", fontsize=4.6, color="#222")
                ax.set_yticks(y); ax.set_yticklabels(d["label"], fontsize=5); ax.set_ylim(len(d) - .4, -.6); ax.set_xlim(0, xmax)
                ax.set_title(PC_NAME[pc], pad=2); ax.tick_params(axis="y", length=0); ax.grid(axis="x", ls=":", alpha=.4); despine(ax)
                if ax is axes[-1] or layout == "side":                 # shared x-axis: one label is enough in the stacked layout
                    ax.set_xlabel("RAPL energy (J), rows ordered by external energy")
            fig.legend(handles=leg, loc="upper center", ncol=2, frameon=False, bbox_to_anchor=(.5, 1.0))
            fig.tight_layout(rect=[0, 0, 1, .955 if layout == "side" else .975])
            default = "energy_rapl_ordered_by_external" + ("_side" if layout == "side" else "_column")
        save_svg(fig, name or default)
        plt.show()
    return R


# ------------------------------------------------------------------ 5. within-run power profiles (full width, one PC)
def power_profiles(trace_df, pc, name=None, families=None, ylim=None):
    """trace_df: per-sample external power with columns pc, query_family, variant (QUERYA/QUERYB), loop_index, time_s, power_w."""
    t = trace_df[(trace_df["pc"] == pc) & trace_df["variant"].isin(["QUERYA", "QUERYB"])].copy()
    t["tbin"] = np.floor(t["time_s"]).astype(int)
    b = t.groupby(["query_family", "variant", "loop_index", "tbin"], as_index=False)["power_w"].mean()
    fams = families or sorted(b["query_family"].unique(), key=lambda f: (f.startswith("PE"), f))
    if ylim is None:
        ylim = (8, 21) if pc == "PC_1" else (10, 42)
    ncols = 3                                          # single column (3.5 in): 3 x 4 grid, the 12th cell holds the legend
    nrows = int(np.ceil((len(fams) + 1) / ncols))
    small = {"font.size": 5, "xtick.labelsize": 5, "ytick.labelsize": 5, "axes.labelsize": 5.5, "axes.titlesize": 5.5}
    with _style(), plt.rc_context(small):
        # x and y are shared by ALL panels of one PC: a panel's curve length is then directly comparable between guidelines
        fig, axes = plt.subplots(nrows, ncols, figsize=(COL_W, 1.0 * nrows + .35), sharex=True, sharey=True)
        flat = axes.ravel()
        tmax = 0
        for ax, fam in zip(flat, fams):
            for v in ("A", "B"):
                dd = b[(b["query_family"] == fam) & (b["variant"] == f"QUERY{v}")]
                piv = dd.pivot_table(index="tbin", columns="loop_index", values="power_w")
                piv = piv[piv.notna().sum(axis=1) >= max(3, .5 * piv.shape[1])]
                ax.plot(piv.index, piv.values, color=VAR[v], lw=.25, alpha=.18, rasterized=True)
                ax.plot(piv.index, piv.median(axis=1), color=VAR[v], lw=.9)
                tmax = max(tmax, piv.index.max())
            ax.set_ylim(*ylim); ax.set_title(fam, pad=1.5, fontweight="bold"); ax.grid(ls=":", alpha=.35); despine(ax)
            ax.tick_params(length=2, pad=1.5)
        flat[0].set_xlim(0, tmax * 1.02)
        flat[0].xaxis.set_major_locator(plt.MaxNLocator(3, integer=True, prune="upper"))
        flat[0].yaxis.set_major_locator(plt.MaxNLocator(3, integer=True))
        for ax in flat[len(fams) + 1:]:
            ax.axis("off")
        last = flat[len(fams)]; last.axis("off")
        n_loops = int(b["loop_index"].nunique())
        last.legend(handles=[Line2D([], [], color=VAR["A"], lw=1.2, label="Variant A"), Line2D([], [], color=VAR["B"], lw=1.2, label="Variant B"),
                             Line2D([], [], color="#777", lw=.5, alpha=.7, label=f"loops ({n_loops})"),
                             Line2D([], [], color="#333", lw=1.1, label="median")],
                    loc="center", frameon=False, fontsize=5, title=f"{PC_NAME[pc]}\nexternal power", title_fontsize=5.2,
                    handlelength=1.4, labelspacing=.3, borderaxespad=0)
        for ax in axes[:, 0]:
            ax.set_ylabel("Power (W)", labelpad=1)
        for i, ax in enumerate(flat[:len(fams)]):
            if i + ncols >= len(fams):               # last visible panel in each column carries the x label and tick labels
                ax.set_xlabel("Time in run (s)", labelpad=1)
                ax.tick_params(labelbottom=True)
        fig.subplots_adjust(left=.11, right=.99, top=.965, bottom=.075, wspace=.16, hspace=.45)
        save_svg(fig, name or f"within_run_power_profile_{pc}")
        plt.show()


# ------------------------------------------------------------------ 6. thermal: all loops overlaid by time-in-loop (single column)
def thermal_overlaid(pkg_by_variant, n_loops, fam, machine_label, name):
    """pkg_by_variant: {'A': DataFrame, 'B': DataFrame} one row per second with PkgWatt, PkgTmp, in recording order
    (n_loops loops appended back to back)."""
    with _style():
        fig, (a1, a2) = plt.subplots(2, 1, figsize=(COL_W, 2.5), sharex=True, gridspec_kw={"height_ratios": [1.15, 1], "hspace": .12})
        tmax = 0
        for v in "AB":
            p = pkg_by_variant[v].reset_index(drop=True)
            L = len(p) // n_loops
            for col, ax in (("PkgWatt", a1), ("PkgTmp", a2)):
                M = np.vstack([p[col].to_numpy()[k * L: k * L + L - 1] for k in range(n_loops)])   # last second = loop seam
                ax.plot(np.arange(M.shape[1]), M.T, color=VAR[v], lw=.35, alpha=.25, rasterized=True)
                ax.plot(np.arange(M.shape[1]), np.median(M, axis=0), color=VAR[v], lw=1.0)
            tmax = max(tmax, L - 1)
        a2.axhline(95, color=REF, lw=.7, ls="--"); a2.text(tmax, 95.8, "95 °C", color=REF, fontsize=5, ha="right")
        a1.set_ylabel("Package power (W)"); a2.set_ylabel("Package temp. (°C)")
        a2.set_xlabel(f"Time in loop (s), {n_loops} loops overlaid")
        a1.set_title(f"{fam}, {machine_label}", pad=2)
        a1.legend(handles=[Line2D([], [], color=VAR["A"], label="Variant A"), Line2D([], [], color=VAR["B"], label="Variant B")],
                  loc="center right", frameon=False)
        for a in (a1, a2):
            a.grid(ls=":", alpha=.4); despine(a)
        fig.subplots_adjust(left=.14, right=.98, top=.94, bottom=.15)
        save_svg(fig, name)
        plt.show()


# ------------------------------------------------------------------ 7. planning time change B - A (single column)
def planning_difference(planning_df, order=None, grp=None, name="planning_time_difference", n_boot=2000, seed=1):
    """planning_df: columns pc ('PC_1'/'PC_2'), test_name ('<family>-queryA.sql'), planning_time_ms (first run of each loop already dropped)."""
    d = planning_df.copy()
    d["pt"] = pd.to_numeric(d["planning_time_ms"], errors="coerce")
    d["fam"] = d["test_name"].str.extract(r"^(APX\d+|PE\d+)-query")[0]
    d["v"] = d["test_name"].str.extract(r"-query([AB])")[0]
    d = d.dropna(subset=["pt", "fam", "v"])
    if order is None or grp is None:
        order, grp = read_group_file()
    if order is None:
        order = sorted(d["fam"].unique()); grp = {f: 1 for f in order}
        print("guideline_groups.json not found (run run_analysis first): rows in alphabetical order")
    order = [f for f in order if f in set(d["fam"])]
    grp = {f: grp.get(f, 1) for f in order}
    ypos = ypositions(order, grp, gap=.6)
    rng = np.random.default_rng(seed)
    off = {"PC_1": -.17, "PC_2": .17}
    with _style():
        fig, ax = plt.subplots(figsize=(COL_W, 2.7))
        draw_bands(ax, order, ypos, grp, 0, label=False)
        for f in order:
            for pc in PCS:
                a = d[(d["fam"] == f) & (d["pc"] == pc) & (d["v"] == "A")]["pt"].to_numpy()
                b = d[(d["fam"] == f) & (d["pc"] == pc) & (d["v"] == "B")]["pt"].to_numpy()
                if len(a) < 2 or len(b) < 2:
                    continue
                diff = np.median(b) - np.median(a)
                bs = [np.median(rng.choice(b, len(b))) - np.median(rng.choice(a, len(a))) for _ in range(n_boot)]
                lo, hi = np.percentile(bs, [2.5, 97.5])
                fc, ec = outcome_style(diff, mannwhitneyu(a, b).pvalue)
                y = ypos[f] + off[pc]
                ax.plot([lo, hi], [y, y], color="#9a9a9a", lw=1.0, solid_capstyle="round", zorder=2)
                ax.scatter(diff, y, s=24, marker=PC_MARK[pc], fc=fc, ec=ec, lw=.7, zorder=4)
        ax.axvline(0, color="black", lw=.8, zorder=1)
        ax.set_yticks([ypos[f] for f in order]); ax.set_yticklabels(order); ax.set_ylim(max(ypos.values()) + .7, -.7)
        ax.set_xlabel("Planning time change, A → B (ms), median and 95 % CI")
        ax.tick_params(axis="y", length=0); ax.grid(axis="x", ls=":", alpha=.5); despine(ax)
        leg = [Line2D([], [], marker="o", ls="", mfc=GREEN, mec="black", ms=4.5, label="sig., B lower"),
               Line2D([], [], marker="o", ls="", mfc=RED, mec="black", ms=4.5, label="sig., A lower"),
               Line2D([], [], marker="o", ls="", mfc="white", mec=GREY, ms=4.5, label="not significant"),
               Line2D([], [], marker="o", ls="", mfc="#cccccc", mec="black", ms=4.5, label=PC_NAME["PC_1"]),
               Line2D([], [], marker="s", ls="", mfc="#cccccc", mec="black", ms=4.5, label=PC_NAME["PC_2"])]
        fig.legend(handles=leg, loc="upper center", ncol=2, frameon=False, fontsize=5.6, bbox_to_anchor=(.5, 1.0),
                   columnspacing=1.0, handletextpad=.3, labelspacing=.35)
        fig.subplots_adjust(left=.16, right=.98, top=.84, bottom=.13)
        save_svg(fig, name)
        plt.show()


# ------------------------------------------------------------------ 8. all cores vs one core, one loop each (single column)
def single_loop_stacked(all_cores, one_core, fam, pc_label, name):
    """all_cores / one_core: {'A': (time_s, watts), 'B': (time_s, watts)} for ONE loop each."""
    with _style():
        fig, axes = plt.subplots(2, 1, figsize=(COL_W, 2.5), sharex=True, sharey=True, gridspec_kw={"hspace": .38})
        for v in "AB":
            axes[0].plot(*all_cores[v], color=VAR[v], lw=.9, label=f"Variant {v}")
            axes[1].plot(*one_core[v], color=VAR[v], lw=.9)
        axes[0].set_title(f"{fam}, {pc_label}: all cores", pad=2); axes[1].set_title("PostgreSQL pinned to one core", pad=2)
        axes[0].legend(loc="center right", frameon=False); axes[1].set_xlabel("Time in loop (s)")
        for a in axes:
            a.set_ylabel("Package power (W)"); a.grid(ls=":", alpha=.4); despine(a)
        fig.subplots_adjust(left=.14, right=.98, top=.93, bottom=.14)
        save_svg(fig, name)
        plt.show()


# ------------------------------------------------------------------ 9. CPU utilisation, one loop each, all cores vs one core (single column)
def single_loop_busy_stacked(all_cores, one_core, fam, pc_label, name):
    """all_cores / one_core: {'A': DataFrame, 'B': DataFrame}; index = seconds in ONE loop, one column per CPU, values = Busy %.
    Thin lines = individual CPUs, thick line = mean over CPUs (verifies how many CPUs the query keeps busy)."""
    with _style():
        fig, axes = plt.subplots(2, 1, figsize=(COL_W, 2.5), sharex=True, sharey=True, gridspec_kw={"hspace": .38})
        for ax, data in zip(axes, (all_cores, one_core)):
            for v in "AB":
                d = data[v]
                for c in d.columns:
                    ax.plot(d.index, d[c], color=VAR[v], lw=.4, alpha=.45, rasterized=True)
                ax.plot(d.index, d.mean(axis=1), color=VAR[v], lw=1.1)
        axes[0].set_title(f"{fam}, {pc_label}: all cores", pad=2)
        axes[1].set_title("PostgreSQL pinned to one core", pad=2)
        fig.legend(handles=[Line2D([], [], color=VAR["A"], lw=1.2, label="Variant A"), Line2D([], [], color=VAR["B"], lw=1.2, label="Variant B"),
                            Line2D([], [], color="#777", lw=.5, alpha=.7, label="individual CPUs"),
                            Line2D([], [], color="#333", lw=1.2, label="mean over CPUs")],
                   loc="upper center", frameon=False, ncol=4, fontsize=5, bbox_to_anchor=(.5, 1.0), columnspacing=1.0, handlelength=1.4)
        axes[1].set_xlabel("Time in loop (s)")
        for a in axes:
            a.set_ylabel("CPU busy (%)"); a.set_ylim(0, 105); a.grid(ls=":", alpha=.4); despine(a)
        fig.subplots_adjust(left=.14, right=.98, top=.86, bottom=.14)
        save_svg(fig, name)
        plt.show()
