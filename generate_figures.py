#!/usr/bin/env python3
"""Generate figures for the paper from benchmark data."""

import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

# Load data
with open("/home/claude/plot_data.json") as f:
    plot_data = json.load(f)

with open("/home/claude/benchmark_results.json") as f:
    results = json.load(f)

COLORS = {
    "No Governance": "#e74c3c",
    "Threshold Only": "#f39c12",
    "Disturbance Cost": "#2ecc71",
}

SCENARIOS = ["Rogue Agent", "Cascade Failure", "Gradual Degradation", "Burst Load", "Mixed (Combined)"]
STRATEGIES = ["No Governance", "Threshold Only", "Disturbance Cost"]

# ─── Figure 1: Instability Over Time (all scenarios) ─────────────
fig, axes = plt.subplots(2, 3, figsize=(16, 10))
axes = axes.flatten()

for idx, scenario in enumerate(SCENARIOS):
    ax = axes[idx]
    for strat in STRATEGIES:
        ticks = plot_data[scenario][strat]["ticks"]
        inst = plot_data[scenario][strat]["instability"]
        ax.plot(ticks, inst, label=strat, color=COLORS[strat], linewidth=1.5, alpha=0.85)

    ax.axhline(y=0.7, color='gray', linestyle='--', alpha=0.5, linewidth=0.8)
    ax.annotate('θ = 0.7', xy=(2, 0.72), fontsize=7, color='gray')
    ax.set_title(scenario, fontsize=11, fontweight='bold')
    ax.set_ylim(-0.05, 1.05)
    ax.set_xlabel('Tick', fontsize=9)
    ax.set_ylabel('Instability I(t)', fontsize=9)
    ax.tick_params(labelsize=8)

# Remove empty subplot
axes[5].set_visible(False)

# Shared legend
handles, labels = axes[0].get_legend_handles_labels()
fig.legend(handles, labels, loc='lower right', fontsize=10, ncol=3,
           bbox_to_anchor=(0.95, 0.08), frameon=True)

fig.suptitle('Figure 1: System Instability Over Time Under Three Governance Strategies',
             fontsize=13, fontweight='bold', y=0.98)
plt.tight_layout(rect=[0, 0.05, 1, 0.95])
plt.savefig('fig1_instability.png', dpi=200, bbox_inches='tight')
plt.close()

# ─── Figure 2: Cascade Failures (bar chart) ──────────────────────
fig, ax = plt.subplots(figsize=(12, 5))

x = np.arange(len(SCENARIOS))
width = 0.25

for i, strat in enumerate(STRATEGIES):
    means = [results[s][strat]["cascade_failures"]["mean"] for s in SCENARIOS]
    stds = [results[s][strat]["cascade_failures"]["std"] for s in SCENARIOS]
    bars = ax.bar(x + i * width, means, width, label=strat, color=COLORS[strat],
                  yerr=stds, capsize=3, alpha=0.85)

ax.set_xlabel('Scenario', fontsize=11)
ax.set_ylabel('Cascade Failures (mean ± std)', fontsize=11)
ax.set_title('Figure 2: Cascade Failures Across Governance Strategies (n=100 runs per condition)',
             fontsize=12, fontweight='bold')
ax.set_xticks(x + width)
ax.set_xticklabels(SCENARIOS, fontsize=9)
ax.legend(fontsize=10)
ax.grid(axis='y', alpha=0.3)

plt.tight_layout()
plt.savefig('/home/claude/fig2_cascades.png', dpi=200, bbox_inches='tight')
plt.close()

# ─── Figure 3: False Positives (bar chart) ───────────────────────
fig, ax = plt.subplots(figsize=(12, 5))

for i, strat in enumerate(STRATEGIES):
    means = [results[s][strat]["false_positives"]["mean"] for s in SCENARIOS]
    stds = [results[s][strat]["false_positives"]["std"] for s in SCENARIOS]
    bars = ax.bar(x + i * width, means, width, label=strat, color=COLORS[strat],
                  yerr=stds, capsize=3, alpha=0.85)

ax.set_xlabel('Scenario', fontsize=11)
ax.set_ylabel('False Positives (mean ± std)', fontsize=11)
ax.set_title('Figure 3: False Positives — Legitimate Actions Incorrectly Blocked (n=100)',
             fontsize=12, fontweight='bold')
ax.set_xticks(x + width)
ax.set_xticklabels(SCENARIOS, fontsize=9)
ax.legend(fontsize=10)
ax.grid(axis='y', alpha=0.3)

plt.tight_layout()
plt.savefig('fig3_false_positives.png', dpi=200, bbox_inches='tight')
plt.close()

# ─── Figure 4: Total Harm comparison ─────────────────────────────
fig, ax = plt.subplots(figsize=(12, 5))

for i, strat in enumerate(STRATEGIES):
    means = [results[s][strat]["total_harm"]["mean"] for s in SCENARIOS]
    stds = [results[s][strat]["total_harm"]["std"] for s in SCENARIOS]
    bars = ax.bar(x + i * width, means, width, label=strat, color=COLORS[strat],
                  yerr=stds, capsize=3, alpha=0.85)

ax.set_xlabel('Scenario', fontsize=11)
ax.set_ylabel('Total Harm (cumulative excess instability)', fontsize=11)
ax.set_title('Figure 4: Total Harm — Cumulative Instability Above Safety Threshold (n=100)',
             fontsize=12, fontweight='bold')
ax.set_xticks(x + width)
ax.set_xticklabels(SCENARIOS, fontsize=9)
ax.legend(fontsize=10)
ax.grid(axis='y', alpha=0.3)

plt.tight_layout()
plt.savefig('fig4_total_harm.png', dpi=200, bbox_inches='tight')
plt.close()

# ─── Figure 5: Agents Alive Over Time (representative) ──────────
fig, axes = plt.subplots(2, 3, figsize=(16, 10))
axes = axes.flatten()

for idx, scenario in enumerate(SCENARIOS):
    ax = axes[idx]
    for strat in STRATEGIES:
        ticks = plot_data[scenario][strat]["ticks"]
        alive = plot_data[scenario][strat]["agents_alive"]
        ax.plot(ticks, alive, label=strat, color=COLORS[strat], linewidth=1.5, alpha=0.85)

    ax.set_title(scenario, fontsize=11, fontweight='bold')
    ax.set_ylim(0, 9)
    ax.set_xlabel('Tick', fontsize=9)
    ax.set_ylabel('Agents Alive', fontsize=9)
    ax.tick_params(labelsize=8)

axes[5].set_visible(False)
handles, labels = axes[0].get_legend_handles_labels()
fig.legend(handles, labels, loc='lower right', fontsize=10, ncol=3,
           bbox_to_anchor=(0.95, 0.08), frameon=True)

fig.suptitle('Figure 5: Agent Survival Under Three Governance Strategies',
             fontsize=13, fontweight='bold', y=0.98)
plt.tight_layout(rect=[0, 0.05, 1, 0.95])
plt.savefig('fig5_survival.png', dpi=200, bbox_inches='tight')
plt.close()

# ─── Summary Table Data ──────────────────────────────────────────
print("TABLE 1: Aggregate Results Across All Scenarios (mean ± std, n=100)")
print()
print(f"{'Metric':<25} {'No Governance':>20} {'Threshold Only':>20} {'Disturbance Cost':>20}")
print("─" * 85)

for metric_key, display in [
    ("cascade_failures", "Cascade Failures"),
    ("false_positives", "False Positives"),
    ("total_harm", "Total Harm"),
    ("ticks_unstable", "Ticks Unstable"),
    ("agents_failed", "Agents Failed"),
]:
    vals = []
    for strat in STRATEGIES:
        # Average across all scenarios
        all_means = [results[s][strat][metric_key]["mean"] for s in SCENARIOS]
        all_stds = [results[s][strat][metric_key]["std"] for s in SCENARIOS]
        grand_mean = np.mean(all_means)
        grand_std = np.mean(all_stds)
        vals.append(f"{grand_mean:>8.2f} ±{grand_std:>5.2f}")
    print(f"  {display:<23} {vals[0]:>20} {vals[1]:>20} {vals[2]:>20}")

print()
print("Figures saved: fig1-fig5")
