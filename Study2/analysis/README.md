# Analysis

These scripts recompute the reported numbers and figures from `../data/`. Run them from `Study2/`:

```bash
python3 -m pip install -r analysis/requirements.txt
python3 analysis/moltbox/verify_claims.py
python3 analysis/babel/verify_claims.py
python3 analysis/moltbox/make_figures.py
python3 analysis/babel/make_figures.py
```

| Script | Output |
|---|---|
| `moltbox/verify_claims.py` | `moltbox/output/claims.md`: each reported number about Moltbox, the value computed from `data/moltbox/run-01/`, and its source. |
| `babel/verify_claims.py` | `babel/output/claims.md`: the same for Babel, from `data/babel/reported-runs/`. |
| `moltbox/make_figures.py` | Figures A1 and A2, in `moltbox/output/figures/`. |
| `babel/make_figures.py` | Figures B1 to B3, in `babel/output/figures/`. |

In the claims tables, `match` means that the computed value, rounded as in the text, equals the reported value.

The claims scripts need only the Python standard library (Python 3.9 or later). The figure scripts need matplotlib; the versions in `requirements.txt` install on Python 3.9 to 3.12.
