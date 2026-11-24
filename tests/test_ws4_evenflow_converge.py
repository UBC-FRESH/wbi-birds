import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_stage2_is_the_convergence_gate():
    m = load("ws4_evenflow_converge")
    # stage 1 not converged is a warm-start fact, not a campaign failure
    assert m.final_status(False, False, True) is True
    # stage 2 not converged is a real failure even if stage 1 converged
    assert m.final_status(False, True, False) is False
    assert m.final_status(False, False, False) is False
    # level-only mode has no stage 2
    assert m.final_status(True, True, False) is True
    assert m.final_status(True, False, True) is False


def test_generated_workflow_has_top_level_nodes():
    import yaml
    m = load("launch_tsa41_bird_sweep")
    wf = yaml.safe_load(m.workflow("case", "rebnut", "aspatial", 100.0, 10, 20))
    assert "nodes" in wf and "nodes" not in wf["workflow"]
    assert wf["nodes"][0]["provider"] == "wbi.ws4_evenflow_convergence"
