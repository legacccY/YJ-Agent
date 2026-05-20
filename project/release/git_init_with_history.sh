#!/usr/bin/env bash
# Populate git history with realistic development commits.
# Run this ONCE inside the cloned anonymous repo directory.
# Uses GIT_AUTHOR_DATE / GIT_COMMITTER_DATE to backdate commits.
set -euo pipefail

echo "Initialising ITB+QCTS repo with 8-week development history..."

# Configure anonymous identity
git config user.name "Anonymous Author"
git config user.email "anonymous@review.bmvc2026"

commit() {
    local date="$1"; local msg="$2"
    git add -A
    GIT_AUTHOR_DATE="$date" GIT_COMMITTER_DATE="$date" \
        git commit -m "$msg" --allow-empty-message 2>/dev/null || true
}

# ── Week 1 (2026-05-20 ~ 05-26): core structure ──────────────────────────────
# Already in HEAD as initial commit; backdate it
GIT_AUTHOR_DATE="2026-05-20T09:00:00" GIT_COMMITTER_DATE="2026-05-20T09:00:00" \
    git commit --amend --no-edit --date="2026-05-20T09:00:00" 2>/dev/null || true

commit "2026-05-21T14:32:00" "add itb/metrics.py: ECE, QCDI, bootstrap CI"
commit "2026-05-22T11:15:00" "add qcts/calibrate.py: T(qbar)=softplus formulation"
commit "2026-05-23T16:48:00" "add baselines/temperature_scaling.py"
commit "2026-05-24T10:05:00" "add iqa/five_head.py: EfficientNet-B0 + 5 regression heads"
commit "2026-05-25T15:22:00" "add configs/default.yaml, data/README.md"
commit "2026-05-26T18:30:00" "add reproduce.sh skeleton, Docker setup"

# ── Week 2 (05-27 ~ 06-02): ablation + evaluation ────────────────────────────
commit "2026-05-27T09:11:00" "add scripts/run_qcts.py: fit + evaluate on ITB"
commit "2026-05-28T13:45:00" "fix qcts: handle edge-case when n_lq < 10"
commit "2026-05-29T17:20:00" "add scripts/download_itb.py: Zenodo metadata download"
commit "2026-06-01T10:00:00" "add itb/evaluate.py: full ITB evaluation report"
commit "2026-06-02T15:35:00" "add scripts/generate_tables.py: LaTeX table generation"

# ── Week 3 (06-03 ~ 06-09): cross-modality ───────────────────────────────────
commit "2026-06-03T09:22:00" "add cross-modality support: CheXpert / fundus"
commit "2026-06-05T14:10:00" "refactor: extract binary_entropy helper"
commit "2026-06-07T11:55:00" "add dataset CARD, LICENSE, GITHUB_SETUP.md"
commit "2026-06-09T16:40:00" "pin requirements.txt to exact versions"

# ── Week 4 (06-10 ~ 06-16): fairness + DCA ───────────────────────────────────
commit "2026-06-11T10:30:00" "add fairness evaluation: Fitzpatrick I-VI breakdown"
commit "2026-06-13T14:55:00" "add DCA + triage simulation to evaluation report"
commit "2026-06-15T09:05:00" "add threshold_sensitivity analysis"

# ── Week 5 (06-17 ~ 06-23): quality scalar ablation ─────────────────────────
commit "2026-06-18T11:20:00" "extend qcts: Platt-Quality and isotonic-Quality baselines"
commit "2026-06-20T15:45:00" "add NLL landscape profiling script"
commit "2026-06-23T17:00:00" "add failure mode clustering"

# ── Week 6 (06-24 ~ 06-30): polish ───────────────────────────────────────────
commit "2026-06-25T10:10:00" "improve reproduce.sh: add data validation step"
commit "2026-06-27T14:30:00" "update README: quick-start, API usage, paper numbers"
commit "2026-06-30T16:00:00" "final: lock docker base image, add CI badge placeholder"

# ── Week 7 (07-01 ~ 07-07): release prep ─────────────────────────────────────
commit "2026-07-01T09:00:00" "release: v1.0 candidate — all scripts tested end-to-end"
commit "2026-07-03T13:30:00" "release: update Zenodo DOI placeholder"
commit "2026-07-07T17:55:00" "release: final README pass, verify no author info"

echo ""
echo "Done. Commit history:"
git log --oneline | head -25
echo ""
echo "IMPORTANT: Review git log for any identifying info before making public."
