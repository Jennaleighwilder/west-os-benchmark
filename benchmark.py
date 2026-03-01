#!/usr/bin/env python3
"""
West-OS Benchmark: Disturbance Cost Governance vs. Alternatives

A reproducible simulation environment that tests three governance strategies
on identical multi-agent failure scenarios:

  1. NO GOVERNANCE     — agents act freely, no oversight
  2. THRESHOLD ONLY    — binary allow/deny based on instability > 0.7
  3. DISTURBANCE COST  — cost-weighted governance (the West-OS approach)

Metrics measured:
  - Cascade failures (how many agents fail due to another agent's action)
  - Recovery time (ticks until system returns to stable state)
  - False positives (legitimate actions incorrectly blocked)
  - System downtime (ticks spent in unstable state)
  - Total harm (cumulative instability exceeding safe threshold)

Each scenario is run 100 times with different random seeds for statistical validity.
"""

import random
import math
import json
import statistics
from dataclasses import dataclass, field
from typing import List, Dict, Tuple
from collections import defaultdict


# ═══════════════════════════════════════════════════════════════════
# FORMAL DEFINITIONS
# ═══════════════════════════════════════════════════════════════════

"""
DEFINITION 1: System State
  A system S at time t is a tuple S(t) = (A, I(t), P(t), H(t)) where:
    A = {a_1, ..., a_n} is a set of agents
    I(t) ∈ [0, 1] is the system instability at time t
    P(t) ≥ 0 is the recovery pressure at time t
    H(t) is the event history up to time t

DEFINITION 2: Action
  An action α by agent a_i at time t is a tuple α = (source, type, impact, reliability)
    where impact ∈ [-1, 1] (negative = restorative)
    and reliability ∈ [0, 1]

DEFINITION 3: Disturbance Cost
  The disturbance cost D(α, S(t)) of action α in state S(t) is:
    D(α, S(t)) = |impact(α)| × (1 + P(t)) × w(type(α)) / reliability(α) × (1 + I(t))

  Where w(type) maps action types to weights:
    w(safe) = 0.5, w(standard) = 1.0, w(hazardous) = 2.0, w(restorative) = 0.3

DEFINITION 4: Governance Strategy
  A governance strategy G is a function G: (α, S(t)) → {ALLOW, DEFER}

  G_none(α, S(t)) = ALLOW                           (no governance)
  G_threshold(α, S(t)) = DEFER if I(t) > θ          (threshold only)
  G_disturbance(α, S(t)) = DEFER if D(α, S(t)) > δ  (disturbance cost)

THEOREM (informal):
  For a system S with n agents generating actions with heterogeneous impacts,
  disturbance cost governance G_disturbance achieves:
    (a) Fewer cascade failures than G_none
    (b) Fewer false positives than G_threshold
    (c) Lower total harm than both
  Under the condition that action impacts are heterogeneous (not all identical).
"""


# ═══════════════════════════════════════════════════════════════════
# SIMULATION ENGINE
# ═══════════════════════════════════════════════════════════════════

@dataclass
class Agent:
    name: str
    reliability: float  # 0-1, how trustworthy this agent is
    action_rate: float  # actions per tick
    impact_mean: float  # mean impact of actions
    impact_std: float   # std of impact
    is_rogue: bool = False
    failed: bool = False
    failed_at: int = -1

@dataclass
class Action:
    source: str
    tick: int
    impact: float       # how much instability this causes
    action_type: str    # safe, standard, hazardous, restorative
    reliability: float
    is_legitimate: bool = True  # for measuring false positives

@dataclass
class SystemState:
    instability: float = 0.0
    recovery_pressure: float = 0.0
    tick: int = 0
    agents_failed: int = 0
    cascade_failures: int = 0
    false_positives: int = 0
    actions_deferred: int = 0
    actions_allowed: int = 0
    ticks_unstable: int = 0
    total_harm: float = 0.0
    peak_instability: float = 0.0
    recovery_ticks: int = 0
    _was_unstable: bool = False

ACTION_WEIGHTS = {
    "safe": 0.5,
    "standard": 1.0,
    "hazardous": 2.0,
    "restorative": 0.3,
}

INSTABILITY_THRESHOLD = 0.7  # above this = "unstable"
CASCADE_THRESHOLD = 0.85     # above this = agents start failing


def compute_disturbance_cost(action: Action, state: SystemState) -> float:
    """
    D(α, S(t)) = |impact| × (1 + P(t)) × w(type) / reliability × (1 + I(t))
    """
    w = ACTION_WEIGHTS.get(action.action_type, 1.0)
    cost = (
        abs(action.impact)
        * (1.0 + state.recovery_pressure)
        * w
        / max(0.1, action.reliability)
        * (1.0 + state.instability)
    )
    return cost


def governance_none(action: Action, state: SystemState) -> str:
    return "ALLOW"


def governance_threshold(action: Action, state: SystemState) -> str:
    if state.instability > INSTABILITY_THRESHOLD:
        return "DEFER"
    return "ALLOW"


def governance_disturbance(action: Action, state: SystemState) -> str:
    cost = compute_disturbance_cost(action, state)
    # Adaptive threshold: lower when system is stressed
    budget = max(0.0, 1.0 - state.instability)
    if cost > budget:
        return "DEFER"
    return "ALLOW"


def create_agents() -> List[Agent]:
    """Standard set of 8 agents for all scenarios."""
    return [
        Agent("analyzer_1", reliability=0.95, action_rate=0.8, impact_mean=0.1, impact_std=0.05),
        Agent("analyzer_2", reliability=0.90, action_rate=0.7, impact_mean=0.15, impact_std=0.08),
        Agent("classifier", reliability=0.85, action_rate=0.6, impact_mean=0.2, impact_std=0.1),
        Agent("router", reliability=0.92, action_rate=1.0, impact_mean=0.05, impact_std=0.02),
        Agent("validator", reliability=0.98, action_rate=0.5, impact_mean=-0.1, impact_std=0.05),  # restorative
        Agent("reporter", reliability=0.88, action_rate=0.4, impact_mean=0.1, impact_std=0.03),
        Agent("monitor", reliability=0.95, action_rate=0.3, impact_mean=-0.05, impact_std=0.02),  # restorative
        Agent("executor", reliability=0.80, action_rate=0.6, impact_mean=0.25, impact_std=0.15),
    ]


# ═══════════════════════════════════════════════════════════════════
# SCENARIOS
# ═══════════════════════════════════════════════════════════════════

def scenario_rogue_agent(agents: List[Agent], tick: int) -> None:
    """At tick 20, one agent goes rogue — high-impact, low-reliability actions."""
    if tick == 20:
        agents[2].is_rogue = True  # classifier goes rogue
        agents[2].reliability = 0.2
        agents[2].impact_mean = 0.6
        agents[2].impact_std = 0.2
        agents[2].action_rate = 2.0

def scenario_cascade_failure(agents: List[Agent], tick: int) -> None:
    """At tick 15, executor starts producing bad data. At tick 25, it cascades."""
    if tick == 15:
        agents[7].impact_mean = 0.4  # executor starts producing bad data
        agents[7].impact_std = 0.2
    if tick == 25:
        agents[7].is_rogue = True
        agents[7].reliability = 0.3
        agents[7].impact_mean = 0.7
        agents[7].action_rate = 3.0

def scenario_gradual_degradation(agents: List[Agent], tick: int) -> None:
    """All agents slowly degrade over time — models drift."""
    for a in agents:
        if not a.is_rogue:
            a.reliability = max(0.3, a.reliability - 0.003)
            a.impact_mean = min(0.5, a.impact_mean + 0.002)

def scenario_burst_load(agents: List[Agent], tick: int) -> None:
    """Ticks 30-40: sudden spike in action rate from all agents."""
    if 30 <= tick <= 40:
        for a in agents:
            a.action_rate *= 1.5
    elif tick == 41:
        # Reset rates
        originals = create_agents()
        for a, o in zip(agents, originals):
            a.action_rate = o.action_rate

def scenario_mixed(agents: List[Agent], tick: int) -> None:
    """Combines rogue agent + gradual degradation + burst."""
    scenario_gradual_degradation(agents, tick)
    if tick == 20:
        agents[2].is_rogue = True
        agents[2].reliability = 0.25
        agents[2].impact_mean = 0.5
        agents[2].action_rate = 2.5
    if 35 <= tick <= 45:
        for a in agents:
            a.action_rate *= 1.3


# ═══════════════════════════════════════════════════════════════════
# SIMULATION RUNNER
# ═══════════════════════════════════════════════════════════════════

def run_simulation(
    governance_fn,
    scenario_fn,
    num_ticks: int = 100,
    seed: int = 42,
) -> Dict:
    """Run one simulation with the given governance strategy and scenario."""
    rng = random.Random(seed)
    agents = create_agents()
    state = SystemState()

    tick_data = []

    for tick in range(num_ticks):
        state.tick = tick

        # Apply scenario mutations
        scenario_fn(agents, tick)

        # Natural recovery (system heals slowly)
        state.instability = max(0.0, state.instability * 0.95 - 0.01)
        state.recovery_pressure = max(0.0, state.recovery_pressure * 0.9)

        # Track unstable ticks
        if state.instability > INSTABILITY_THRESHOLD:
            state.ticks_unstable += 1
            if not state._was_unstable:
                state._was_unstable = True
        else:
            if state._was_unstable:
                state._was_unstable = False
                state.recovery_ticks += 1  # count recovery events

        # Cascade: if instability > threshold, agents start failing
        if state.instability > CASCADE_THRESHOLD:
            for a in agents:
                if not a.failed and not a.is_rogue:
                    fail_prob = (state.instability - CASCADE_THRESHOLD) * 2.0
                    if rng.random() < fail_prob:
                        a.failed = True
                        a.failed_at = tick
                        state.cascade_failures += 1
                        state.agents_failed += 1

        # Each agent generates actions
        tick_actions = 0
        tick_deferred = 0

        for agent in agents:
            if agent.failed:
                continue

            # Determine if agent acts this tick
            if rng.random() > agent.action_rate:
                continue

            # Generate action
            impact = rng.gauss(agent.impact_mean, agent.impact_std)
            if agent.is_rogue:
                impact = abs(impact)  # rogue agents never help

            action_type = "standard"
            if impact < -0.05:
                action_type = "restorative"
            elif impact > 0.4:
                action_type = "hazardous"
            elif impact < 0.1:
                action_type = "safe"

            action = Action(
                source=agent.name,
                tick=tick,
                impact=impact,
                action_type=action_type,
                reliability=agent.reliability,
                is_legitimate=not agent.is_rogue,
            )

            # Apply governance
            verdict = governance_fn(action, state)

            if verdict == "ALLOW":
                state.actions_allowed += 1
                # Apply action's impact to system
                state.instability = max(0.0, min(1.0, state.instability + impact))
                state.recovery_pressure += abs(impact) * 0.5
                tick_actions += 1
            else:
                state.actions_deferred += 1
                tick_deferred += 1
                # Check false positive
                if action.is_legitimate and action.impact < 0.3:
                    state.false_positives += 1

        # Track total harm
        if state.instability > INSTABILITY_THRESHOLD:
            state.total_harm += state.instability - INSTABILITY_THRESHOLD

        state.peak_instability = max(state.peak_instability, state.instability)

        tick_data.append({
            "tick": tick,
            "instability": round(state.instability, 4),
            "pressure": round(state.recovery_pressure, 4),
            "actions": tick_actions,
            "deferred": tick_deferred,
            "agents_alive": sum(1 for a in agents if not a.failed),
            "cascade_failures": state.cascade_failures,
        })

    return {
        "cascade_failures": state.cascade_failures,
        "false_positives": state.false_positives,
        "total_harm": round(state.total_harm, 4),
        "ticks_unstable": state.ticks_unstable,
        "peak_instability": round(state.peak_instability, 4),
        "actions_allowed": state.actions_allowed,
        "actions_deferred": state.actions_deferred,
        "recovery_events": state.recovery_ticks,
        "agents_failed": state.agents_failed,
        "tick_data": tick_data,
    }


# ═══════════════════════════════════════════════════════════════════
# BENCHMARK RUNNER
# ═══════════════════════════════════════════════════════════════════

def run_benchmark(num_runs: int = 100) -> Dict:
    """Run all scenarios with all governance strategies, num_runs times each."""

    strategies = {
        "No Governance": governance_none,
        "Threshold Only": governance_threshold,
        "Disturbance Cost": governance_disturbance,
    }

    scenarios = {
        "Rogue Agent": scenario_rogue_agent,
        "Cascade Failure": scenario_cascade_failure,
        "Gradual Degradation": scenario_gradual_degradation,
        "Burst Load": scenario_burst_load,
        "Mixed (Combined)": scenario_mixed,
    }

    results = {}

    for scenario_name, scenario_fn in scenarios.items():
        results[scenario_name] = {}
        for strategy_name, strategy_fn in strategies.items():
            run_results = []
            for run_id in range(num_runs):
                seed = run_id * 1000 + hash(scenario_name) % 1000
                r = run_simulation(strategy_fn, scenario_fn, num_ticks=100, seed=seed)
                run_results.append(r)

            # Aggregate
            agg = {}
            for metric in ["cascade_failures", "false_positives", "total_harm",
                           "ticks_unstable", "peak_instability", "actions_deferred",
                           "agents_failed"]:
                values = [r[metric] for r in run_results]
                agg[metric] = {
                    "mean": round(statistics.mean(values), 3),
                    "std": round(statistics.stdev(values), 3) if len(values) > 1 else 0,
                    "min": round(min(values), 3),
                    "max": round(max(values), 3),
                    "median": round(statistics.median(values), 3),
                }

            # Store one representative run for plotting
            agg["representative_run"] = run_results[0]["tick_data"]
            results[scenario_name][strategy_name] = agg

    return results


def print_results(results: Dict) -> None:
    """Print formatted benchmark results."""
    print("=" * 90)
    print("  WEST-OS BENCHMARK: DISTURBANCE COST GOVERNANCE vs. ALTERNATIVES")
    print("  100 runs per scenario × 5 scenarios × 3 strategies = 1,500 simulations")
    print("=" * 90)

    for scenario_name, strategies in results.items():
        print(f"\n{'─' * 90}")
        print(f"  SCENARIO: {scenario_name}")
        print(f"{'─' * 90}")

        # Header
        print(f"\n  {'Metric':<25} {'No Governance':>18} {'Threshold Only':>18} {'Disturbance Cost':>18}")
        print(f"  {'─' * 25} {'─' * 18} {'─' * 18} {'─' * 18}")

        metrics_display = [
            ("Cascade Failures", "cascade_failures"),
            ("False Positives", "false_positives"),
            ("Total Harm", "total_harm"),
            ("Ticks Unstable", "ticks_unstable"),
            ("Peak Instability", "peak_instability"),
            ("Agents Failed", "agents_failed"),
            ("Actions Deferred", "actions_deferred"),
        ]

        for display_name, metric_key in metrics_display:
            vals = []
            for strat_name in ["No Governance", "Threshold Only", "Disturbance Cost"]:
                m = strategies[strat_name][metric_key]
                vals.append(f"{m['mean']:>8.2f} ±{m['std']:>5.2f}")

            # Highlight best
            means = [strategies[s][metric_key]["mean"]
                     for s in ["No Governance", "Threshold Only", "Disturbance Cost"]]

            # For most metrics, lower is better (except false_positives comparison)
            print(f"  {display_name:<25} {vals[0]:>18} {vals[1]:>18} {vals[2]:>18}")

    # Summary comparison
    print(f"\n{'=' * 90}")
    print(f"  SUMMARY: Disturbance Cost vs. No Governance (% improvement)")
    print(f"{'=' * 90}")

    for scenario_name, strategies in results.items():
        ng = strategies["No Governance"]
        dc = strategies["Disturbance Cost"]
        th = strategies["Threshold Only"]

        cascade_pct = (1 - dc["cascade_failures"]["mean"] / max(0.001, ng["cascade_failures"]["mean"])) * 100
        harm_pct = (1 - dc["total_harm"]["mean"] / max(0.001, ng["total_harm"]["mean"])) * 100
        unstable_pct = (1 - dc["ticks_unstable"]["mean"] / max(0.001, ng["ticks_unstable"]["mean"])) * 100

        # False positive comparison: DC vs Threshold
        fp_improvement = th["false_positives"]["mean"] - dc["false_positives"]["mean"]

        print(f"\n  {scenario_name}:")
        print(f"    Cascade failures:  {cascade_pct:>+6.1f}% vs no governance")
        print(f"    Total harm:        {harm_pct:>+6.1f}% vs no governance")
        print(f"    Ticks unstable:    {unstable_pct:>+6.1f}% vs no governance")
        print(f"    False positives:   {fp_improvement:>+6.1f} fewer than threshold-only")


def generate_data_for_plots(results: Dict) -> Dict:
    """Extract data needed for paper figures."""
    plot_data = {}

    for scenario_name, strategies in results.items():
        plot_data[scenario_name] = {}
        for strat_name, strat_data in strategies.items():
            # Extract instability over time from representative run
            ticks = [t["tick"] for t in strat_data["representative_run"]]
            instabilities = [t["instability"] for t in strat_data["representative_run"]]
            agents_alive = [t["agents_alive"] for t in strat_data["representative_run"]]

            plot_data[scenario_name][strat_name] = {
                "ticks": ticks,
                "instability": instabilities,
                "agents_alive": agents_alive,
            }

    return plot_data


# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("Running benchmark (1,500 simulations)...\n")
    results = run_benchmark(num_runs=100)

    print_results(results)

    # Save raw data
    # Strip tick_data for JSON (too large)
    save_results = {}
    for scenario, strats in results.items():
        save_results[scenario] = {}
        for strat, data in strats.items():
            save_data = {k: v for k, v in data.items() if k != "representative_run"}
            save_results[scenario][strat] = save_data

    with open("/home/claude/benchmark_results.json", "w") as f:
        json.dump(save_results, f, indent=2)

    # Save plot data
    plot_data = generate_data_for_plots(results)
    with open("/home/claude/plot_data.json", "w") as f:
        json.dump(plot_data, f, indent=2)

    print(f"\n\nResults saved to benchmark_results.json and plot_data.json")
