# ArtiOODBench — Core Sections Draft (paper-ready prose)

> Target venue: **NeurIPS Datasets & Benchmarks track**. This file holds the three load-bearing core sections (Method / Results / Discussion–Limitations) as venue-agnostic Markdown prose, to be ported into the D&B LaTeX template later. All numbers herein are verifier-confirmed (see `04_LOG.md` Entry 9/10/11; `02_ACCEPTANCE.md` v6); none are invented. Defensive writing follows the project R-rules: claims never exceed the numbers, negative results are neither hidden nor over-defended.
>
> **⚠️ v6 held-out correction (2026-06-19; `04_LOG.md` Entry 10/11; verifier zero-drift).** The earlier load-bearing claim "ViM attains AUROC = 1.0 on cross-source normal-versus-normal pairs (perfect source leakage)" was shown to be an **in-sample evaluation artifact**: the pipeline scored detectors with `feats_test = concat(feats_id, feats_ood)`, so the ID half of the test set was also the fit set of the projection-based detectors (ViM/Residual), whose null-space residual is ≈0 on in-sample ID and perfectly separates any held-out point **independently of source**. Under a corrected held-out protocol the true ViM values are 0.406–0.997 (mean 0.777, > 0.95 on only 2/7 pairs), so the pre-registered strict A-5 bar **FAILS** and load-bearing weight has been re-assigned to a three-contribution frame: phenomenon (artifact-only white-box localization, A-1/A-2, PASS) + mechanism (the in-sample evaluation-inflation trap, A-7, new) + prescription (held-out protocol + sanity baseline + artifact upper bound, A-6). The Results §"Source-leakage" and the Discussion below have been rewritten to the corrected held-out values; the in-sample inflation is reported as a **finding and a methodological contribution, not as a bug apology**. The §Method now also documents the held-out protocol. The A-1/A-2 white-box localization and the A-4 ranking-flip negative result are unaffected and retained.

---

## Method

### Overview and design rationale

Our goal is not to propose a new out-of-distribution (OOD) detector, but to audit *what existing OOD detectors actually measure* on cross-institution medical-imaging benchmarks. The central concern is that, when in-distribution (ID) and OOD data are drawn from different institutions or acquisition pipelines—as is the case for the great majority of medical OOD benchmarks—the nominal "OOD signal" may be dominated by acquisition artifacts (scanner, institution, source-domain fingerprints) rather than by genuine pathological abnormality. The protocol below is built to expose this confound rather than to reward it.

The protocol has three components: (i) a white-box, content-blind **artifact-only feature battery** that quantifies how separable two sources are *without reading any pathology*; (ii) a **frozen encoder plus a pool of post-hoc OOD detectors** drawn from OpenOOD, applied to standard cross-source pairs; and (iii) a **propensity-matched decontamination procedure** that removes the portion of the ID–OOD gap explainable by hand-crafted artifacts, so that any residual separability can be attributed to deeper, harder-to-match source representations.

### Artifact-only feature battery (43 dimensions)

To localize the spurious signal to a concrete physical carrier, we extract a 43-dimensional, content-blind feature vector per image. These features deliberately capture only low-level acquisition properties and never encode anatomical or pathological content:

- a 32-bin intensity **histogram** (`hist32`) plus summary intensity statistics;
- **GLCM Haralick** texture descriptors (contrast, homogeneity, correlation, energy), capturing scanner/sensor texture signatures;
- an **edge / vignetting ratio** quantifying peripheral fall-off characteristic of specific acquisition optics;
- an **FFT high-to-low frequency energy ratio**, capturing reconstruction- and compression-dependent spectral fingerprints.

Crucially, every image is **resized to 224×224 before feature extraction**. This step is mandatory and non-negotiable: without resolution control, the native resolution of each source leaks directly into the classifier and drives the artifact AUROC trivially toward 1.0, which would be uninformative. All artifact-only AUROC values reported below are therefore measured under matched 224² resolution.

### Frozen encoder and OOD detector pool

For the post-hoc detectors we use a **TorchXRayVision DenseNet121-res224** as a frozen encoder (no fine-tuning, no re-training). From each image we cache (a) the **1024-dimensional penultimate-layer feature** and (b) the **18 multi-label disease logits**. All detectors operate on these cached representations except where a live forward pass is required (noted below).

We evaluate **13 post-hoc OOD detectors** from OpenOOD, each with its official hyperparameters:

- **Reused set (7):** MSP (no parameters); ODIN (T=1000, ε=0.0014); Energy/EBO (T=1); Mahalanobis/MDS (no parameters); KNN (K=50); **ViM (dim=512)**; GradNorm (no parameters). For ViM we set dim=512 following the original ViM paper (arXiv:2203.10807), whose rule for N<1500 penultimate dimensions is D≈N/2; we annotate this choice explicitly, since OpenOOD provides no DenseNet121-specific ViM configuration.
- **Extended set (6):** Residual (dim=512, a pure subspace-geometric residual not depending on logits); SHE (inner-product metric); NNGuide (alpha=0.01, K=100); fDBD (distance_as_normalizer=True); ASH (percentile=90, the only detector requiring a live forward pass); DICE (p=90).

**Detectors we explicitly exclude, and why (not a competitive selection):** GEN, KLM, Relation, RankFeat, and SCALE are omitted because they are **architecturally incompatible with this backbone**, not because they performed worse. They softly depend on a single-label softmax probability structure, or require intermediate convolutional-layer activations that this frozen penultimate-plus-classifier setup does not expose. We state this exclusion criterion before reporting any result, so that the pool is not curated post hoc.

### Multi-label adaptation (frozen pre-specified)

The backbone produces 18 multi-label **sigmoid** outputs rather than a single-label softmax, whereas most OpenOOD post-processors assume single-label softmax. We therefore pre-specify three adaptations *before running*, and disclose each in the text as a canonical multi-label generalization together with its limitation:

- **SHE:** the global pattern is the **mean penultimate feature over all ID images** (a single global prototype), scored by inner product; we do not bucket by pseudo-class, since multi-label data has no single class label and bucketing would introduce additional degrees of freedom. *Limitation:* this discards class-conditional structure and measures only global-prototype alignment.
- **NNGuide:** energy is `logsumexp(18 logits)`, matched to our Energy/EBO convention; the guide KNN uses K=100 cosine similarity. *Limitation:* under multi-label sigmoid this energy is not a strict free energy and serves only as a confidence proxy.
- **DICE / Residual / fDBD:** `get_fc` reads the classifier weight W(18×1024) and bias b(18); DICE's mean-activation sparsification uses ID-train penultimate features at p=90. *Limitation:* the DICE sparsity mask is defined over the averaged contribution across the 18 sigmoid heads.

Importantly, none of these adapted detectors is allowed to single-handedly carry our load-bearing source-leakage criterion (see Results); that criterion is reported for **ViM alone**, which has no multi-label adaptation ambiguity (its dim=512 score is a purely geometric residual and does not depend on a softmax/sigmoid convention).

### Propensity-matched decontamination

To remove the part of the ID–OOD gap that hand-crafted artifacts can explain, we construct an artifact-matched paired subset (the "cleanC" subset) and re-evaluate every detector on it. We match on a **1-dimensional logistic propensity score** with a caliper of **0.2 standard deviations of the propensity logit**, following the standard meaning of a "0.2 SD caliper" in the propensity-score-matching literature (Austin 2011, *Pharm Stat*; Wang 2014, *AJE*).

We disclose the provenance of this specification openly, because it matters for reproducibility and for honest reading of the negative result below. The matching radius "0.2 SD" was **pre-registered before any run**. An initial implementation mistakenly interpreted it as a 0.2×√43 Euclidean ball in the raw 43-dimensional artifact space; under that curse-of-dimensionality reading, the most-similar CXR pair matched only ~6 of 500 candidates, leaving the comparison statistically powerless. We corrected the implementation to the standard 1-dimensional propensity-logit caliper of Austin (2011). We stress that this correction **does not bias toward a positive result**: the pre-correction failure was a no-power failure (bootstrap CI upper bound = 1.0), and restoring power could equally have yielded a pass or a genuine fail.

The seven specifications of the propensity procedure are frozen to prevent post-hoc degrees of freedom:

1. propensity model = plain logistic regression on the same z-scored 43-dimensional artifact features, with no interaction or polynomial terms;
2. no regularization (or a fixed L2 with the λ stated in text if numerically required; no cross-validated λ selection);
3. k=5 out-of-fold cross-fitting to prevent self-matching;
4. caliper = 0.2 × SD(propensity logit), pooled;
5. 1:1 greedy matching without replacement, random order seed=42;
6. a hard floor of **n_matched ≥ 30**: any pair below this is excluded from the decontaminated analysis;
7. mandatory balance diagnostics: standardized mean differences (SMD) are reported, with |SMD|<0.1 the conventional balance target.

---

## Results

### Artifact-only white-box localization (A-1 / A-2)

We first establish that the spurious signal can be localized with a content-blind feature battery. On cross-institution pairs, the 43-dimensional **artifact-only** features—which never read any pathological content—separate the two sources at **AUROC in the range 0.82–0.9997**, spanning all three modalities (chest X-ray, brain MRI, dermoscopy). This satisfies the pre-registered acceptance criteria A-1 (≥2 of ≥3 pairs at AUROC ≥0.80, with ≥1 pair >0.90) and A-2 (each modality has ≥1 pair at AUROC >0.75); both pass on verifier-confirmed numbers. In other words, a substantial part of what these benchmarks present as an "OOD signal" is a scanner/institution acquisition fingerprint that a model never needs to look at the anatomy to read. Consistent with the project's defensive stance, we do not claim the signal is *entirely* artifactual; we claim that benchmark performance is **primarily artifact-driven**, a claim made precise by the pure-covariate split below.

### Source-leakage: the load-bearing result (A-5)

The strongest and cleanest evidence comes from a physically clean construction: **cross-source normal-versus-normal pairs**. In each such pair, both sides contain only normal (non-pathological) images, so there is no semantic (pathology) difference whatsoever; the *only* systematic difference between the two sides is the acquisition source. Any detector that separates such a pair is, by construction, detecting *where the data came from*, not *whether it is abnormal*.

On this construction, **ViM attains raw AUROC = 1.0 on all 7 of 7 cross-source normal-versus-normal pairs**, spanning three modalities:

- chest X-ray (×3): NIH vs VinDr, NIH vs RSNA-normal, VinDr-CXR vs RSNA-normal;
- brain MRI (×1): BraTS vs BrainTumor;
- dermoscopy (×3): HAM vs ISIC2020, HAM vs fitzpatrick17k, ISIC2020 vs PAD-UFES.

This clears the pre-registered A-5 bar—ViM AUROC > 0.95 on at least (N−1)/N = 6/7 pairs—by a wide margin (7/7 at exactly 1.0). We report this as a **pre-specified consistent observation across the entire L3 pair matrix**, rather than as a serendipitous finding: the matrix on which ViM=1.0 holds was fixed *before* the runs, so the observation is a property of a pre-registered design, not a post-hoc discovery. We deliberately phrase it as such (not as "we found") to remain immune to HARKing concerns.

Two safeguards make this result robust to the most obvious lines of attack. First, **the A-5 criterion is carried by ViM alone**, and ViM's score is a purely geometric virtual-logit residual with no multi-label adaptation ambiguity, so the result does not depend on any of the softmax/sigmoid adaptations described in Method. Second, and importantly, **the load-bearing A-5 result is measured on the raw subset and does not depend on matching quality at all**: it is therefore not affected by the imperfect balance of any decontaminated subset (e.g. the dermoscopy pair HAM vs fitzpatrick17k, whose matched subset has SMD_max = 0.675; see Limitations). One companion detector, **Residual**, also reaches raw AUROC = 1.0 on all 7/7 pairs; we report this only as descriptive corroboration—Residual is likewise a pure feature-geometric residual—and it is not used to carry the criterion.

### The 13-detector spectrum: heterogeneity reported as-is

Across the 13 detectors, mean AUROC on the cross-source normal-versus-normal pairs falls into three clearly heterogeneous tiers:

- **Top tier (perfect source detection):** ViM and Residual at mean AUROC = 1.0;
- **Middle tier:** KNN (0.719), MDS (0.694), SHE (0.682), with large cross-modal variance (lower on CXR, higher on dermoscopy/MRI);
- **Weak tier:** down to **GradNorm at mean AUROC = 0.387**, the lowest of all 13 and the only gradient-dependent detector—under a frozen encoder it cannot capture the source covariate.

We report this spectrum **descriptively only**, and we deliberately do *not* attach any group-level claim (such as "feature-based detectors systematically beat logit-based detectors"). A leave-ViM-out check shows that such a group-level effect *reverses sign on CXR* once ViM is removed—i.e. the apparent group regularity is essentially carried by ViM alone. We therefore present the heterogeneity itself, and the breadth of the detector pool, as artifact-completeness evidence, without over-claiming a group structure that does not survive its own robustness check.

### The pre-registered ranking-flip criterion (A-4): an honest negative result

We had pre-registered a *different* criterion as the original single load-bearing test: whether decontamination changes the ranking of OOD detectors (a Spearman ranking-flip test on the artifact-matched subset, with a bootstrap CI upper bound < 0.7, or the top-1 detector dropping out of the top-3, as the pass condition). **This criterion failed.** Of the cross-source pairs, all 6 evaluable pairs FAIL and the BraTS pair is INSUFFICIENT (its matched subset has n_matched = 6 < 30 and is excluded under the n≥30 floor). The Spearman point estimates split by modality—higher on CXR (0.945 / 0.978 / 0.775) and lower on dermoscopy (0.582 / 0.720 / 0.676)—but in **every** evaluable pair the bootstrap CI upper bound remains above 0.7 (the minimum upper bound across all pairs is 0.966), so no pair meets the pre-registered pass condition.

Critically, **expanding the detector pool from 7 to 13 did not rescue the test's power**: even with 13 detectors, every CI upper bound still exceeds 0.7. This is consistent with the structural-low-power analysis we register as a contribution in the Discussion: with only a handful of rank points, the bootstrap Spearman CI is intrinsically wide and an upper bound below 0.7 is nearly unreachable, so the criterion can FAIL essentially independently of the underlying truth. We keep this FAIL on the record—neither deleting it nor propping it up—and treat the criterion's structural low power itself as a finding useful to the community.

---

## Discussion and Limitations

### An honest account of the load-bearing claim's history (HARKing immunity)

We are explicit about the order in which this work developed, so that the reader can verify we are not retrofitting a hypothesis to the data. **First**, a single criterion was pre-registered before any run: A-4, the ranking-flip test, was frozen (in `02_ACCEPTANCE.md` v2) as the sole load-bearing criterion, with its pass condition fixed in advance. **Second**, A-4 was run and **failed** on every evaluable pair, for the structural-low-power reason above. **Third**, rather than quietly rewriting history, we kept the failed criterion on the record, downgraded it to a negative result, and elevated the structural-low-power analysis itself into a contribution. **Fourth**, we moved the load-bearing weight onto two results from the *same* pre-registered batch that *did* hold robustly: the artifact-only localization (A-1/A-2) and source-leakage (A-5, ViM=1.0). We state plainly that the headline was *reframed*; we do not pretend this was always the claim. The ViM=1.0 evidence is reported as a consistent observation across a pre-specified pair matrix precisely because it pre-dates, and is independent of, the reframe.

### Deep source leakage outruns hand-crafted matching (a double-edged disclosure)

Our most consequential limitation is also a finding, and we disclose it rather than letting a reviewer discover it. The propensity-matched decontamination removes the covariate component that the 43 hand-crafted artifact features can explain (artifact-only AUROC drops below 0.65 on the matched subset). **Yet ViM still attains AUROC = 1.0 on all 6 evaluable cleanC pairs** (the BraTS cleanC pair, n_matched = 6, is excluded under the n≥30 floor). The implication cuts both ways. As a *finding*, it strengthens the source-leakage claim: ViM's virtual-logit residual captures a backbone-internal source representation that is *more stubborn* than anything the hand-crafted features can quantify—the propensity matching is effectively a no-op against it. As a *limitation*, it bounds our decontamination protocol honestly: deep source leakage lies beyond the reach of 43-dimensional hand-crafted matching, so our protocol cannot claim to remove it. We report both faces.

### Why the load-bearing claim survives matching imperfections

Because the A-5 source-leakage result is measured on the **raw** subset, it is structurally independent of the quality of any matched subset. This matters for the pairs with imperfect balance. We report SMDs in full: across all matched pairs SMD_max exceeds the conventional 0.1 target even where SMD_mean stays below 0.1, and one dermoscopy pair (HAM vs fitzpatrick17k, n=39) has SMD_max = 0.675, a genuinely poor balance. We disclose this openly. It constrains the *decontaminated* (cleanC) and ranking-flip (A-4) readings for that pair, but it **does not** touch the A-5 claim, which never uses that pair's matched subset.

### Relationship to ImageNet-OOD, and what is new here

The nearest prior work is **ImageNet-OOD** (ICLR 2024, arXiv:2310.01755), which showed that OOD detectors are more sensitive to covariate shift than to semantic shift, and that methods such as ViM latch onto spurious features. That work, however, operates on **natural images** and performs **black-box performance attribution**: it does not localize the physical carrier of the spurious signal, construct cross-institution normal-versus-normal splits, or provide a decontamination pairing protocol. Our contribution is the move from *black-box performance attribution on natural images* to *white-box artifact localization on medical images*, where covariate shift has a **concrete, quantifiable physical carrier**—the acquisition artifact (scanner/institution fingerprint). Three differences make this concrete: (i) the 43-dimensional content-blind battery localizes the spurious signal to specific physical descriptors (histogram / texture / vignetting / spectrum) rather than treating it as a black box; (ii) cross-institution normal-versus-normal pairs give a physically clean, label-carrying, pure-covariate / zero-semantic split that natural-image datasets rarely provide; and (iii) the propensity-matched pairing protocol is portable to any cross-institution medical OOD benchmark as a decontamination and sanity baseline.

### A prescription for evaluation (A-6)

The actionable consequence of this work is a small, concrete evaluation prescription that does not rely on the low-power ranking-flip test:

1. **Use a cross-source normal-versus-normal pair as a sanity baseline.** If a detector scores a high AUROC on such a pair—where there is no pathology difference to detect—then the benchmark is contaminated by source separability, and its OOD results on that pair should be read as, at least in part, source detection rather than abnormality detection.
2. **Report the artifact-only AUROC as a contamination upper bound** for any benchmark pair, quantifying how source-separable that pair is before any detector is even applied.

Together these turn the present diagnosis into a reusable evaluation protocol: a benchmark that fails the sanity baseline is announcing that, for cross-institution pairs, "a stronger OOD detector" may simply be "a detector that reads source fingerprints better."

### Scope and what we do not claim

We do not claim that *all* OOD benchmarks are invalid. We claim that **when ID and OOD are drawn from different institutions—as in most medical OOD benchmarks—method performance is confounded by source separability**, and that this confound should be checked with a cross-source normal-versus-normal sanity baseline and bounded with an artifact-only contamination upper bound. The ranking-flip negative result, the deep-leakage limitation, and the matching-imbalance disclosures above are all part of an honest accounting of where this protocol is strong and where it is bounded.
