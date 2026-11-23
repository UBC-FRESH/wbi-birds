"""Write the manuscript AF coefficient and AIC tables from the fitted JSON."""
from __future__ import annotations

import json
from pathlib import Path

FITS = Path("/srv/shared-data/gep/wbi-birds/campaigns/ws4-five-tsa-2026-11/bird-fits/scanfi-240m-nine-species-spatial.json")
OUT = Path("/srv/shared-data/gep/wbi-birds/wbi-birds-manuscript/tables/ws4-2026-11")
LABELS = [("rebnut", "RBNU"), ("borchi2", "BOCH"), ("gockin", "GCKI"), ("brncre", "BRCR"),
          ("yerwar", "YERW"), ("swathr", "SWTH"), ("whtspa", "WTSP"), ("tenwar", "TEWA"),
          ("yebsap", "YBSA")]


def main() -> int:
    data = json.loads(FITS.read_text())
    fits = ["\\begin{table}[h]", "\\centering",
            "\\caption{Spatial-local quasi-Poisson anticipation functions (log link; coefficients on the log scale). "
            "Edge, early-seral and forest fractions are measured in an eight-cell (1.92~km) window at 240~m.}",
            "\\label{tab:fits}", "\\small", "\\begin{tabular}{lrrrrrrr}", "\\toprule",
            "Species & Age & Softwood & Hardwood & Edge & Early seral & Forest & AIC \\\\", "\\midrule"]
    aic = ["\\begin{table}[h]", "\\centering",
           "\\caption{AIC of the aspatial log-link form and the spatial-local form; a positive difference means the spatial-local form is preferred.}",
           "\\label{tab:aic}", "\\small", "\\begin{tabular}{lrrr}", "\\toprule",
           "Species & AIC aspatial & AIC spatial-local & $\\Delta$AIC \\\\", "\\midrule"]
    for code, label in LABELS:
        s = data["species"][code]
        c = s["coefficients"]
        fits.append(f"{label} & {c['age']:.3f} & {c['log1p_softwood']:.2f} & {c['log1p_hardwood']:.2f} "
                    f"& {c['edge_1km']:.2f} & {c['pct_early_500m']:.2f} & {c['pct_forest_1km']:.2f} "
                    f"& {s['aic']:,.0f} \\\\")
        aic.append(f"{label} & {s['aic_base']:,.0f} & {s['aic']:,.0f} & {s['aic_base'] - s['aic']:,.0f} \\\\")
    fits += ["\\bottomrule", "\\end{tabular}", "\\end{table}", ""]
    aic += ["\\bottomrule", "\\end{tabular}", "\\end{table}", ""]
    (OUT / "species-fits.tex").write_text("\n".join(fits))
    (OUT / "species-aic.tex").write_text("\n".join(aic))
    print("wrote tables")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
