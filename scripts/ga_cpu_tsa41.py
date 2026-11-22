#!/usr/bin/env python
"""CPU GA for ws4 via fresh-solutions population search (exact ws4 evaluations)."""
from __future__ import annotations
import json, random, sys
from pathlib import Path

from fresh_solutions.backend import CpuBatchBackend
from fresh_solutions.contracts import Evaluation
from fresh_solutions.population import PopulationConfig, run_population_search

from ws4.opt.engine import OptimizeConfig, Optimizer
from ws4.opt.incremental import IncrementalObjective
from ws4.opt.objective import load_targets

D = Path(sys.argv[1] if len(sys.argv) > 1 else "/srv/shared-data/gep/ws4/femic/external/femic-tsa41-instance/output/patchworks_tsa41_p120/compiled-bird")
TARGETS = Path(sys.argv[2] if len(sys.argv) > 2 else D / "targets-evenflow-steady-v7.yaml")
OUT = Path(sys.argv[3] if len(sys.argv) > 3 else D / "ga-cpu")
POP = int(sys.argv[4]) if len(sys.argv) > 4 else 64
GENS = int(sys.argv[5]) if len(sys.argv) > 5 else 200
SEED = int(sys.argv[6]) if len(sys.argv) > 6 else 7

OUT.mkdir(parents=True, exist_ok=True)
opt = Optimizer.from_dataset(D, OptimizeConfig(years=200, targets_path=str(TARGETS), iterations=1, threads=1))
targets = load_targets(TARGETS)
cands = opt.candidates()
blocks = [b for b in sorted(cands) if cands[b]]
chains = {b: cands[b] for b in blocks}


class Adapter:
    name = "ws4-tsa41"
    ACCOUNTS = ("product.HarvestedVolume.managed.Total.CC", "feature.Yield.managed.Total", "feature.Bird.rebnut")

    def __init__(self) -> None:
        self.base = {b: chains[b][0] for b in blocks}
        self.evaluator = IncrementalObjective(opt, targets, extra_accounts=self.ACCOUNTS)
        self.evaluator.reset(self.base)
        self.base_obj = self.evaluator.objective

    @property
    def variable_count(self) -> int:
        return len(blocks)

    def option_count(self, variable: int) -> int:
        return len(chains[blocks[variable]])

    def option_at(self, variable: int, option: int) -> object:
        return chains[blocks[variable]][option]

    def initial_assignment(self) -> dict[int, int]:
        return {i: 0 for i in range(len(blocks))}

    def random_assignment(self, rng: random.Random) -> dict[int, int]:
        return {i: rng.randrange(len(chains[blocks[i]])) for i in range(len(blocks))}

    def mutate(self, assignment, rate, rng):
        child = dict(assignment)
        for i in range(len(blocks)):
            if rng.random() < rate:
                child[i] = rng.randrange(len(chains[blocks[i]]))
        return child

    def crossover(self, left, right, rng):
        return {i: (left[i] if rng.random() < 0.5 else right[i]) for i in range(len(blocks))}

    def _schedule(self, assignment):
        return {blocks[i]: chains[blocks[i]][assignment[i]] for i in range(len(blocks))}

    def evaluate(self, assignment) -> Evaluation:
        schedule = self._schedule(assignment)
        changed = [b for b in blocks if schedule[b] != self.base[b]]
        delta = self.evaluator.delta(changed, schedule) if changed else 0.0
        obj = self.base_obj + delta
        return Evaluation(objective=float(obj), feasible=True, penalty=float(obj))

    def evaluate_batch(self, assignments):
        return [self.evaluate(a) for a in assignments]

    def propose(self, assignment, rng):
        return None

    def apply(self, assignment, change):
        return dict(assignment)

    def undo(self, assignment, change):
        return dict(assignment)


adapter = Adapter()
cfg = PopulationConfig(population=POP, generations=GENS, seed=SEED, mutation_rate=0.05)
result = run_population_search(adapter, cfg, CpuBatchBackend(adapter))
schedule = adapter._schedule(result.assignment)
schedule_csv = OUT / "schedule.csv"
import pandas as pd
pd.DataFrame([{"block_id": b, "treatment": t, "offset": o} for b, ch in schedule.items() for t, o in ch], columns=["block_id", "treatment", "offset"]).to_csv(schedule_csv, index=False)
(OUT / "summary.json").write_text(json.dumps({"objective": result.objective, "feasible": result.feasible, "evaluations": result.evaluations, "generations": result.generations, "schedule": str(schedule_csv)}, indent=2))
print(json.dumps({"objective": result.objective, "evaluations": result.evaluations, "generations": result.generations}))
