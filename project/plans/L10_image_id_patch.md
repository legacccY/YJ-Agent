# L10 — Patch to emit `image_name` into `itb_predictions.csv`

**Goal**: add an `image_name` (= ITB `isic_id`) column to every per-sample row written into
`results/itb_predictions.csv`, so ISIC2020 demographics (sex / age) can be joined for L10
fairness. DO NOT apply yet — review first, then re-run eval on GPU.

## Why this is needed
`run_experiments.py` reads `results/itb_subsets.csv`, which **already has an `isic_id` column**
(`ISIC_xxxxxxx` for isic2020 rows; FitzPatrick17k md5hash for ITB-Diverse). But each
`run_*_baseline()` collects only `all_probs / all_targets / all_qbar` while iterating
`sub.iterrows()`, then writes prediction rows in that same order — the identifier is dropped.
We re-capture it.

## Identifier field
- File: `run_experiments.py`
- Source column: `row["isic_id"]` (from `itb_subsets.csv`), available inside every
  `for _, row in tqdm(sub.iterrows(), ...)` loop.
- For ISIC subsets (ITB-Edge / ITB-HQ / ITB-LQ) this equals the ISIC2020 `image_name`.
  For ITB-Diverse it is a FitzPatrick17k hash (harmless — sex/age script excludes it).

## Minimal patch (6 runner functions — same shape in each)
Each runner has: (a) an accumulator-init line `all_probs, all_targets, all_qbar = [], [], []`,
(b) inside the loop an append of `all_qbar.append(float(row["qbar"]))`, and (c) a final
`for i in range(len(targets_arr)): pred_rows.append({...})`. In each we add a parallel
`all_ids` list and write `"image_name": all_ids[i]`.

Apply the SAME 3 edits to all 6 runners:
`run_b3_baseline`, `run_ts_baseline`, `run_focal_baseline`, `run_qvib_baseline`,
`run_mcdropout_baseline`, `run_ensemble_baseline`.

### Edit pattern (illustrated on `run_b3_baseline`, lines 163, 175, 189–194)

(1) Init accumulator — add `all_ids`:
```diff
-        all_probs, all_targets, all_qbar = [], [], []
+        all_probs, all_targets, all_qbar = [], [], []
+        all_ids = []
```

(2) Inside loop, right after the `all_qbar.append(float(row["qbar"]))` line — capture id.
NOTE: the `continue` on `img is None` happens BEFORE this append, so ordering stays aligned:
```diff
             all_qbar.append(float(row["qbar"]))
+            all_ids.append(str(row["isic_id"]))
```

(3) In the prediction-write loop, add the column:
```diff
             pred_rows.append({
                 "baseline": "A", "baseline_name": "EfficientNet-B3 (Direct)", "subset": subset,
+                "image_name": all_ids[i],
                 "prob_pos": float(probs_arr[i, 1]), "target": int(targets_arr[i]),
                 "qbar": float(qbar_arr[i]), "kl_term": 0.0, "prior_var": 0.0,
             })
```

### Exact line anchors per runner (current file)
| Runner | (1) init `all_*` line | (2) `all_qbar.append` line | (3) `pred_rows.append` block |
|---|---|---|---|
| `run_b3_baseline`        | 163 | 176 | 190–194 |
| `run_ts_baseline`        | 212 | 227 | 240–244 |
| `run_focal_baseline`     | 260 | 279 | 295–299 |
| `run_qvib_baseline`      | 312 | 332 | 351–356 |
| `run_mcdropout_baseline` | 376 | 404 | 420–424 |
| `run_ensemble_baseline`  | 444 | 466 | 482–486 |

(`run_qvib_baseline` line 312 also inits `all_kl, all_prior_var` on the next line — leave that,
just add `all_ids = []` alongside. Its loop appends id after the `all_prior_var.append(pvar)`
block, i.e. after current line 334.)

## After patch
Re-run `python run_experiments.py` (all baselines) on GPU → overwrites
`results/itb_predictions.csv` now WITH `image_name`. Then copy/point that file to
`results/itb_predictions_withid.csv` and run `scripts/fairness_sex_age_breakdown.py`.

## Zero-risk note
Purely additive: one new column, no metric / ordering / RNG change. Existing downstream
readers (`fairness_fitzpatrick_breakdown.py` etc.) select columns by name, so an extra column
does not break them.
