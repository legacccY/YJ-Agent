---
model: Claude 4.7 Opus
date: 2026-05-20T16:13:17.491Z
---


> **思考过程**
> 
> The user wants me to act as a CV reviewer (BMVC) with no prior exposure to medical imaging, calibration, or information bottleneck. They want me to read this paper with a "beginner's mind" and flag everything I don't understand on first read. Let me go through this carefully, sentence by sentence, and identify:
> 
> 1. Jargon/terms (classified as J1 unknown, J2 guessable, J3 clear)
> 2. Logical jumps where I lose the thread
> 3. Sentences where I can't decide what the authors claim
> 4. Sections that should be re-ordered
> 5. 3 figures/tables with captions that don't make sense without body
> 6. A paragraph paraphrasing the contribution
> 
> Let me read the paper thoroughly.
> 
> Starting from the beginning:
> 
> **Title:** "Quality-Aware Calibration: Exposing and Mitigating Calibration Collapse under Image Quality Shift in Dermatology AI"
> 
> **Abstract:**
> - "On ITB, standard temperature scaling can reverse the entropy–quality correlation on some backbones." — ITB? Temperature scaling? Entropy-quality correlation? What entropy? What backbones?
> - "For a Std VIB backbone the entropy–quality Spearman correlation flips from ρ=−0.153 (p<10−15) to ρ=+0.241 (p<10−37)" — Std VIB? I know VIB = Variational Information Bottleneck from the intro mention but Std VIB is a specific thing.
> - "turning a quality-fragile model into a quality-oblivious one on the inputs that most demand caution" — quality-fragile, quality-oblivious are terms they define later.
> - "Quality-Conditioned Temperature Scaling (QCTS), a two-parameter post-hoc calibrator conditioned on per-image quality" — post-hoc calibrator?
> - "Quality-Aware Calibration (QAC), the Quality-Calibration Degradation Index (QCDI), and a three-class diagnostic taxonomy (quality-oblivious / fragile / aware)" — these are their proposed terms.
> - "MC Dropout and Deep Ensembles remain quality-oblivious on low-quality inputs despite competitive AUC (low-quality ECE 0.44–0.62, roughly triple simpler alternatives)" — MC Dropout? Deep Ensembles? AUC? ECE?
> - "QCTS cuts QCDI from +0.015 to +0.004 (73% reduction over TS) and low-quality ECE by 46%" — TS = Temperature Scaling?
> - "The reversal generalises from EfficientNet to ResNet-50 and ViT-Tiny on ITB" — EfficientNet, ResNet-50, ViT-Tiny are known architectures. Clear.
> - "extends to ImageNet-C corruption severity as an alternative per-input quality scalar" — ImageNet-C? Known benchmark for corruptions. Clear enough.
> 
> Now let me systematically go through each section...
> 
> **Section 1 Introduction:**
> - "Monte Carlo Dropout [7] and deep ensembles [13]" — MC Dropout, deep ensembles. I know these from general ML but the reviewer persona might not fully. Let me assess as someone with CV background but no calibration expertise.
> - "temperature scaling [8]" — From context: a calibration method that uses a single scalar T.
> - Actually wait, I'm told I have ResNet/Transformer/SSL background but have NEVER worked on medical imaging, calibration, or information bottleneck. So I know CV architectures (EfficientNet, ResNet, ViT, ConvNeXt, Swin) but NOT calibration (ECE, temperature scaling, etc.) and NOT medical imaging.
> 
> Let me re-read with this lens.
> 
> Key terms I need to flag as J1 (unknown to me as a CV person who hasn't worked on calibration):
> - **Temperature Scaling (TS)** — first mentioned in abstract, defined in Section 2 as "learns a single scalar T to soften logits." As a CV person I've heard of it but wouldn't know the mechanics. I'd say J2 (guessable from context since they explain it).
> - **ECE (Expected Calibration Error)** — first used in abstract as "low-quality ECE 0.44-0.62." Defined in §3.1. J2 — guessable from the formula they provide.
> - **MC Dropout** — mentioned in abstract. J2 — I know dropout, "MC Dropout" with 30 passes is guessable.
> - **Deep Ensembles** — J2, guessable (ensemble of models).
> - **VIB (Variational Information Bottleneck)** — mentioned as Std VIB. J2 maybe? They cite [1] and mention it in related work. But as someone who hasn't worked on IB, I'd need more explanation.
> - **QCDI (Quality-Calibration Degradation Index)** — their own term, defined in §3.2. J3 — clear after definition.
> - **QAC (Quality-Aware Calibration)** — their term, defined. J3.
> - **Spearman's ρ** — J3, standard statistical measure.
> - **EDL (Evidential Deep Learning)** — J2, mentioned with brief explanation.
> - **softplus** — J3, standard function.
> - **L-BFGS** — J2/J3, standard optimizer.
> - **PAC-Bayes** — J1 if they don't explain well. Let me check §4.2. They mention "McAllester-style" bound. As someone without calibration/learning theory background, this would be J1 — unknown.
> - **Isotonic regression** — J2, they mention it briefly. I know it from stats.
> - **Platt scaling** — J2, standard calibration method.
> - **DeiT initialisation** — J3, I know this from ViT literature.
> 
> Now let me identify logical jumps and unclear claims.
> 
> **Potential J1 terms (truly unknown to the target reviewer):**
> 1. **PAC-Bayes / McAllester-style bound** — §4.2, "For a binary classifier, the expected ECE on a quality stratum... satisfies (McAllester-style [16])" — A CV reviewer who hasn't worked on learning theory won't know this.
> 2. **Variational Information Bottleneck (VIB)** / **Std VIB** — Used throughout. Even though they cite [1] and give a brief explanation in §2, the core concept is assumed. As someone without IB background, I'd need more.
> 3. **Evidential Deep Learning (EDL) / Dirichlet outputs** — §2. They mention "Dirichlet outputs" without explaining what that means in this context.
> 4. **Information Bottleneck compression strength β** — §4.2, "In the Variational IB [1] the compression strength β controls how much input information the latent Z discards." If I don't know IB, this is opaque.
> 5. **softplus** — Actually this is J3, it's defined: softplus(u) = log(1+e^u).
> 
> Let me reconsider. As a CV reviewer (ResNet/Transformer/SSL), I know:
> - Standard architectures (EfficientNet, ResNet, ViT, ConvNeXt, Swin)
> - Standard ML concepts (cross-entropy, NLL, AdamW, cosine annealing)
> - Standard evaluation (AUC, confusion matrices, Spearman correlation)
> - I know what calibration MEANS broadly but not the specific metrics/methods
> 
> What I DON'T know:
> - ECE, temperature scaling, reliability diagrams (calibration-specific)
> - VIB, information bottleneck theory
> - EDL, Dirichlet uncertainty
> - PAC-Bayes bounds
> - MC Dropout as calibration method (I know dropout for regularization)
> - Platt scaling, isotonic regression for calibration
> - BRISQUE, CLIP-IQA (image quality assessment methods)
> 
> Let me now systematically go through and find:
> 
> **Logical jumps** (≥2):
> 
> Jump 1: In §1 (intro), they go from "Standard TS reverses entropy-quality correlation" to proposing QCTS without clearly explaining WHY this reversal happens. The mechanism isn't explained until §5.2.
> 
> Jump 2: In §4.2, they jump from "softplus function definition" to "PAC-Bayes generalisation sketch" without clear motivation. Why bring PAC-Bayes? The connection to the practical method is tenuous.
> 
> Jump 3: The transition from §3 (taxonomy) to §4 (ITB + QCTS) — they define taxonomy in §3.3 but then §4 describes ITB construction and QCTS without explicitly connecting the taxonomy to the benchmark design.
> 
> **Undecidable claims:**
> 
> 1. "QCTS is a post-hoc calibrator that conditions temperature on per-image quality, unlike Guo et al.'s [8] quality-agnostic TS and unlike the training-time uncertainty modelling of EDL [23] and VIB [1]." — Wait, is this claiming that VIB is training-time uncertainty modelling? VIB was trained as a backbone. The sentence groups EDL and VIB but they seem different.
> 
> 2. "Sharpness is the dominant calibration risk among the five degradation types we test; colour temperature is comparatively benign." — Is this a claim from their experiments or a general statement? The evidence for "dominant calibration risk" needs to be clarified — dominant in what sense? Magnitude of ECE increase?
> 
> 3. "QCTS cuts QCDI from +0.015 to +0.004 (73% reduction over TS) and low-quality ECE by 46%." — 73% reduction over TS: is this (0.015-0.004)/0.015 = 73%? But they say "over TS" — does this mean the reduction is from the TS baseline? The QCDI for TS is +0.015 and for QCTS is +0.004, so the reduction relative to TS is (0.015-0.004)/0.015 = 73%. But QCDI for raw Std VIB is +0.016 (Table 1). So "over TS" is correct. But the abstract says QCDI drops "from +0.015 to +0.004" — this is the TS baseline going to QCTS, not raw Std VIB to QCTS. This is slightly confusing.
> 
> **Sections to reorder:**
> 
> 1. §4.2 (QCTS) could come before §4.1 (ITB) since QCTS is the method and ITB is the benchmark — or alternatively §3.3 (taxonomy) could be folded into §5 (experiments) since it reads like a result.
> 
> 2. The PAC-Bayes sketch in §4.2 feels out of place and could be moved to an appendix or a discussion section.
> 
> 3. §5.4 (universality across backbones) should arguably come right after §5.2 (main results) since it's part of the core empirical claim.
> 
> **Figures/tables with unclear captions:**
> 
> 1. **Figure 1** — The caption mentions "Std VIB" and "QCTS" without defining them. A reader seeing this figure first (as is typical) won't know what these are. The "red" and "orange" annotations assume the reader knows which is which.
> 
> 2. **Table 1** — "Subscripts are half-widths of 1,000-iter bootstrap 95% CIs." Wait, I see subscripts like "0.751±0.072" — these are ± values, not subscripts. The caption says "subscripts" but the table shows ± notation. This is confusing.
> 
> 3. **Table 3** — "Ablation on the form of T(q̄)" — The caption mentions "single-seed point estimates" which conflicts with earlier statements about "averaged over three training seeds." The inconsistency needs explanation.
> 
> 4. **Figure 2** — The caption is quite long and technical. The "Takeaway" line helps but the figure has a lot of components (dataset logos, network diagrams, mathematical notation) that require body text to fully parse.
> 
> Actually, let me re-read more carefully to identify all the specific sentences where I lose the thread.
> 
> Let me now structure my response properly.
> 
> One more thing — the "Paraphrase the paper's contribution" paragraph.
> 
> The paper's contribution:
> - They identify that standard calibration methods (temperature scaling, MC dropout, deep ensembles) fail when image quality varies — a problem they call "calibration collapse under quality shift."
> - They propose a framework (QAC, QCDI, taxonomy) to evaluate calibration quality-awarely.
> - They build a benchmark (ITB) for this evaluation using dermatology images.
> - They propose QCTS, a simple 2-parameter post-hoc fix that conditions temperature on per-image quality score, which fixes the problem without retraining.
> 
> OK, now let me think about the J1/J2/J3 counts.
> 
> J1 (truly unknown, needs explanation):
> 1. "McAllester-style" PAC-Bayes bound — §4.2. A CV reviewer without learning theory won't know this.
> 2. "Dirichlet outputs" in context of EDL — §2. What does Dirichlet mean here?
> 3. "Variational Information Bottleneck" — the paper cites [1] but never explains the mechanism. Even the brief explanation in §2 is insufficient for someone who's never worked with IB.
> 4. "BRISQUE" and "CLIP-IQA" — §5.3/Table S1. These are image quality assessment methods. A non-medical-imaging CV person might know BRISQUE, but CLIP-IQA is newer.
> 5. "DeiT initialisation" — §5.4. Actually, as a Transformer person, I know this. J3.
> 
> Actually, let me be more careful about what a "CV reviewer with ResNet/Transformer/SSL background but NO calibration/medical imaging/IB" would know.
> 
> Known:
> - ResNet, ViT, EfficientNet, ConvNeXt, Swin architectures
> - Standard training (AdamW, cosine annealing, batches, epochs)
> - AUC, Spearman correlation, bootstrap CIs
> - Cross-entropy, NLL
> - Softmax, softplus
> - L-BFGS
> - Dropout (as regularization)
> - Ensembles (general concept)
> - ImageNet-C (corruption benchmark)
> - Basic statistics (p-values, confidence intervals)
> 
> NOT known:
> - ECE (Expected Calibration Error) — though the formula is given
> - Temperature Scaling specifically
> - MC Dropout as uncertainty method (as opposed to regularization)
> - Deep Ensembles as calibration method
> - Reliability diagrams
> - VIB / Information Bottleneck theory
> - EDL / Dirichlet uncertainty
> - Platt scaling, isotonic regression (these are calibration-specific)
> - BRISQUE, CLIP-IQA (IQA-specific)
> - PAC-Bayes bounds
> - Fitzpatrick skin types (medical)
> 
> Let me finalize the J1 count. I'll be strict — J1 means "I as a CV person who hasn't worked on calibration genuinely don't know this term and the paper doesn't explain it."
> 
> J1 candidates:
> 1. **PAC-Bayes / McAllester-style bound** (line ~320-330) — Not explained. A learning theory concept. J1.
> 2. **Dirichlet outputs** in EDL context — Mentioned without explanation. J1 for a non-calibration person.
> 3. **Variational Information Bottleneck** — They cite and briefly define, but the core IB concepts (compression strength β, latent Z, etc.) are assumed. This is borderline J1/J2. I'll say J2 since they do give a sentence of explanation in §2.
> 4. **BRISQUE / CLIP-IQA** — These are IQA methods. A general CV person might not know them. Borderline J1/J2.
> 5. **DeiT initialisation** — J3 for a Transformer person.
> 
> Let me count more carefully across the whole paper for truly unknown terms:
> - "McAllester-style [16]" / PAC-Bayes — J1 (not explained, learning theory jargon)
> - "Dirichlet outputs" — §2 — J1 (not explained, EDL-specific)
> - "DeiT initialisation" — §5.4 — J3 for Transformer person
> - "BRISQUE" — §5.3 — J2 (context: "off-the-shelf estimators")
> - "CLIP-IQA" — §5.3 — J2
> - "FitzPatrick17k" — J2 (context: dermatology dataset, skin types)
> - "Platt scaling" — §5.3 — J2 (standard ML calibration, but not everyone knows it)
> - "isotonic regression" — §5.3 — J2
> 
> Actually, for a CV reviewer at BMVC, Platt scaling and isotonic regression should be known (they're standard ML). BRISQUE is a well-known IQA method in CV. So maybe only 2-3 true J1s.
> 
> Let me settle on:
> J1: PAC-Bayes/McAllester bound, Dirichlet outputs (in context of EDL)
> J2: VIB, BRISQUE, CLIP-IQA, Platt scaling, isotonic regression, MC Dropout (as calibration), Deep Ensembles (as calibration), ECE (before §3.1), temperature scaling (before §2), FitzPatrick skin types, EDL, reliability diagrams
> J3: Everything else that's standard CV/ML
> 
> Now for logical jumps:
> 
> Jump 1: The transition from the observation "TS reverses ρ" (end of §1) to proposing QCTS (§4.2). The paper states the observation but doesn't explain the mechanism of WHY TS causes this reversal until much later (§5.2). The reader is left hanging.
> 
> Jump 2: The PAC-Bayes section in §4.2. It appears abruptly after the softplus definition and optimization, with no clear motivation for why a theoretical bound is needed or what it adds.
> 
> Jump 3: In §3.3, the taxonomy classes are defined by QCDI magnitude, but then the "disambiguating QCDI sign-flips" paragraph introduces a second criterion (ρ < -0.15 for genuine quality-awareness). This second criterion feels added ad-hoc and the connection to the 3-class taxonomy is fuzzy.
> 
> Undecidable claims:
> 
> 1. §1: "Sharpness is the dominant calibration risk among the five degradation types we test; colour temperature is comparatively benign." — Is "dominant" measured by the magnitude of ECE increase? The paper doesn't specify the metric for "dominant" in this summary claim.
> 
> 2. Abstract: "MC Dropout and Deep Ensembles remain quality-oblivious on low-quality inputs despite competitive AUC (low-quality ECE 0.44-0.62, roughly triple simpler alternatives)" — What are the "simpler alternatives"? Std VIB? EfficientNet-B3? The comparison baseline is unclear.
> 
> 3. §5.3: "piecewise minimises validation NLL but produces the worst QCDI and a near-zero entropy–q̄ correlation, so smooth interpolation across q̄—not NLL alone—turns post-hoc calibration into quality-aware calibration." — Is the claim that NLL optimization is insufficient for quality-aware calibration, or that smooth interpolation specifically enables it? The causal claim is ambiguous.
> 
> Now for sections to reorder:
> 
> 1. §3.3 (Taxonomy) reads like an experimental finding but is presented before the method. It could go after §5.2 or be integrated there.
> 
> 2. §4.1 (ITB) and §4.2 (QCTS) — If ITB is the benchmark used to evaluate QCTS, describing ITB first makes sense. But the PAC-Bayes sketch in §4.2 disrupts the flow and should be an appendix.
> 
> 3. The "Generalisation sketch via PAC-Bayes" paragraph in §4.2 should be an appendix — it's a theoretical sketch that interrupts the method description.
> 
> OK now for the 3 figures/tables with captions that don't make sense without body:
> 
> 1. **Figure 1**: Row 3 mentions "Std VIB assigns 81–96% melanoma probability" and "QCTS (orange) brings predictions down by 13–14 pp without retraining." Without reading the body, I don't know what Std VIB is, what QCTS is, or why 81-96% melanoma probability for benign lesions is problematic (though I can guess). The caption uses undefined acronyms.
> 
> 2. **Table 1**: "Subscripts are half-widths of 1,000-iter bootstrap 95% CIs." — But the values use ± notation (e.g., "0.751±0.072"), not subscripts. The caption's terminology ("subscripts") doesn't match the table formatting, causing confusion on first read. Also, the distinction between "bold" and "underline" for best/second-best is noted but the visual difference may not be clear without seeing the formatted table.
> 
> 3. **Figure 2**: The caption is dense and references "VisiScore-Net" (undefined in the caption), "softplus(T₀ + α(1-q̄))" (the formula is in the figure but its meaning is opaque without body text), and "L-BFGS" (optimizer, but the caption assumes knowledge of the optimization procedure). The takeaway line helps but the caption is overloaded.
> 
> Let me now compile everything into the final output format.
> 
> Actually, I want to double-check one thing — the paper says "We will release ITB and QCTS." This is a BMVC 2026 submission. The anonymization says "Submission # ??" which suggests this is a review draft.
> 
> Let me now write the final response.

# Brutally Honest BMVC Review — "Quality-Aware Calibration" (First-Read, No Calibration/Medical/IB Background)

---

## 🔤 JARGON / TERMS I HAD TO GUESS

| # | Term | Quote | Class |
|---|------|-------|-------|
| 1 | **Temperature Scaling (TS)** | *"standard temperature scaling can reverse the entropy–quality correlation"* (Abstract) | **J2** — guessable: §2 says "learns a single scalar T to soften logits." But the *mechanism* (how T enters softmax) is never stated explicitly; I had to infer `softmax(z/T)`. |
| 2 | **ECE (Expected Calibration Error)** | *"low-quality ECE 0.44–0.62, roughly triple simpler alternatives"* (Abstract) | **J2** — formula given in §3.1 Eq. (1). Definition comes late (page 4), but acronym appears from Abstract onward. |
| 3 | **Variational Information Bottleneck (VIB) / Std VIB** | *"For a Std VIB backbone the entropy–quality Spearman correlation flips"* (Abstract) | **J2** — §2 mentions "regularises representations by balancing compression and prediction." I sort-of get it, but **what β controls, what the latent Z is, and why it's called a "bottleneck"** is never explained to a non-IB reader. The paper *uses* Std VIB as its main backbone and never defines it properly. |
| 4 | **Evidential Deep Learning (EDL) / Dirichlet outputs** | *"EDL [23] models input-dependent uncertainty at training time via Dirichlet outputs"* (§2) | **J1** — **unknown.** What is a "Dirichlet output" in a classification network? How does a Dirichlet distribution replace a softmax? This is never explained, yet EDL is a baseline in Table 1 and discussed throughout. |
| 5 | **PAC-Bayes / McAllester-style bound** | *"satisfies (McAllester-style [16]): E[ECE_q] ≤ ÊCE_q + sqrt((KL(Posterior_q ‖ Prior) + ln(2√n_q/δ)) / 2n_q)"* (§4.2) | **J1** — **unknown.** As a CV reviewer (ResNet/Transformer background), I have never encountered PAC-Bayes bounds. The paragraph gives zero intuition for *why* this bound is here or what the reader should take from it. |
| 6 | **BRISQUE / CLIP-IQA** | *"Among four off-the-shelf estimators, BRISQUE [18] and CLIP-IQA [28] collapse to α̂≈0"* (§5.3) | **J2** — context says they're image quality estimators. I can guess. |
| 7 | **Platt scaling / isotonic regression** | *"quality-stratified Platt scaling [22] and quality-binned isotonic regression"* (§5.3) | **J2** — I know these from general ML (logistic calibration, non-parametric calibration). But a junior CV reviewer might not. |
| 8 | **Reliability diagrams** | *"Reliability diagrams (supp Fig. S3) make the failure visible"* (§5.2) | **J2** — guessable (ECE visualization), but the paper name-drops them without a single example in the main text. |
| 9 | **DeiT initialisation** | *"ViT-Tiny (Transformer, DeiT initialisation)"* (§5.4) | **J3** — clear to a Transformer person. |
| 10 | **FitzPatrick skin types I–VI** | *"FitzPatrick17k images across all six skin types (I–VI)"* (§4.1) | **J2** — dermatology classification of skin tone; I can infer from context. |
| 11 | **softplus** | *"softplus(u) = log(1+e^u) guarantees T > 0"* (§4.2) | **J3** — defined inline. |
| 12 | **L-BFGS** | *"running L-BFGS for up to 200 iterations"* (§4.2) | **J3** — standard optimizer. |

**J1 count: 2** (PAC-Bayes, Dirichlet outputs). Under threshold of 5. ✅  
**J2 count: 8.** Under threshold of 12. ✅

---

## 🔀 LOGICAL JUMPS (Where I Lost the Thread)

### Jump 1: The TS ρ-reversal is stated but never causally explained.

> *"applying standard temperature scaling to a quality-fragile backbone […] reverses the sign of ρ to +0.241 (Table 1). TS can therefore shift confidence in the wrong direction under quality degradation"* (§1, lines ~085–090)

The paper treats this as the central motivating observation. But **why** does a single scalar T cause entropy to become *positively* correlated with quality? The mechanism is not addressed until §5.2 (and even then only descriptively: "NLL-driven miscalibration repair and quality-awareness are distinct objectives"). A reader who doesn't already believe calibration is quality-sensitive will lose the thread here. I needed a sentence like: *"TS inflates T uniformly, which flattens the softmax for all inputs equally; on low-quality inputs where the model was already uncertain, this uniform flattening can push confidence below the already-low accuracy, inverting the entropy–quality relationship."*

### Jump 2: The PAC-Bayes sketch appears from nowhere.

> *"Generalisation sketch via PAC-Bayes. For a binary classifier, the expected ECE on a quality stratum S_q of size n_q satisfies (McAllester-style [16]): …"* (§4.2, lines ~315–330)

The paper goes from "here is our two-parameter softplus function" → "here is the optimization objective (NLL)" → **suddenly PAC-Bayes bounds**. There is no transition explaining *why* a theoretical bound is being presented in the middle of a method section. Is this meant to justify the method theoretically? Is it a sketch of future work? The paragraph ends with *"We treat Eq. 6 as a motivating sketch; a formal analysis… is left to future work"* — which confirms this is not a contribution. It should be moved to an appendix or removed. I completely lost the narrative here.

### Jump 3: The taxonomy (§3.3) introduces a second "genuine quality-awareness" criterion mid-definition.

> *"Negative QCDI does not always mean genuine quality-awareness. A method is genuinely quality-aware if (i) QCDI≤0 and (ii) ρ(H, q̄)<−0.15"* (§3.3, lines ~215–220)

The three-class taxonomy (Quality-Oblivious / Fragile / Aware) is defined purely by QCDI magnitude. Then, in a "Disambiguating" sub-paragraph, a *second* criterion (ρ < −0.15) is introduced to distinguish "genuinely quality-aware" from "quality-confused." This creates a **4-class taxonomy in practice** (Oblivious / Fragile / Confused / Genuinely Aware) but is presented as a 3-class one. The ρ threshold (−0.15) appears arbitrary. I had to stop and re-map the categories.

---

## ❓ SENTENCES WHERE I CANNOT DECIDE WHAT THE AUTHORS CLAIM

### Claim 1 (Abstract):

> *"MC Dropout and Deep Ensembles remain quality-oblivious on low-quality inputs despite competitive AUC (low-quality ECE 0.44–0.62, roughly triple simpler alternatives)"*

**Question:** What are the "simpler alternatives" being compared against? Std VIB (ECE 0.146)? EfficientNet-B3 (ECE 0.345)? The phrase "triple" implies a specific baseline, but none is named. Table 1 shows Deep Ensemble ECE = 0.440 vs. Std VIB ECE = 0.146, which is indeed ~3× — but the abstract should say "triple Std VIB" explicitly.

### Claim 2 (§5.2):

> *"Sharpness is the dominant calibration risk among the five degradation types we test; colour temperature is comparatively benign."*

**Question:** "Dominant" by what metric? Table 2a shows Blur ECE = 0.173 and Colour temp ECE = 0.264 — colour temperature has *higher* raw ECE. Is "dominant" measured by QCTS reduction magnitude (−51% vs. −41%)? By baseline severity? The sentence can be read both ways. If blur is the risk QCTS fixes best, that's different from blur being the worst risk in absolute terms.

### Claim 3 (§5.3, about piecewise-constant T(q̄)):

> *"piecewise minimises validation NLL but produces the worst QCDI and a near-zero entropy–q̄ correlation, so smooth interpolation across q̄—not NLL alone—turns post-hoc calibration into quality-aware calibration."*

**Question:** Is the claim that (a) NLL is an insufficient objective for quality-aware calibration, or (b) smoothness of T(q̄) is the necessary ingredient, or (c) both? The "so" implies causation (smoothness → quality-awareness) but the evidence is one row in Table 3. This is an overclaim from a single ablation.

---

## 📐 SECTIONS THAT SHOULD BE RE-ORDERED

| # | Move | Justification |
|---|------|---------------|
| 1 | **§3.3 (Taxonomy) → after §5.2** | The taxonomy reads like an empirical finding (regimes derived from QCDI numbers), yet it's presented *before* the method and experiments. A reader encounters "Quality-Oblivious (QCDI > 0.10)" without having seen a single QCDI value. Move it to Results so the taxonomy emerges from the data. |
| 2 | **PAC-Bayes paragraph in §4.2 → Appendix** | It is explicitly labeled a "motivating sketch" for "future work." It interrupts the method description with an equation (Eq. 6) that is never referenced again. It belongs in supplementary material. |
| 3 | **§5.4 (Universality) → merge into §5.2** | The backbone-universality results (Table 4) are a core empirical claim — they show QCTS works across architectures. Splitting them into a separate subsection after the QCTS analysis (§5.3) fragments the main evidence. Put the architecture probe right after the main results table. |
| 4 | **§4.1 (ITB) and §4.2 (QCTS) → swap** | QCTS is the conceptual contribution; ITB is the evaluation scaffold. Describing the benchmark before the method forces the reader to absorb dataset splits, degradation dimensions, and strata definitions before knowing *what* will be evaluated. Method-first is standard. |

**Suggested order:** §1 Intro → §2 Related Work → §3 QAC/QCDI definitions → §4.2 QCTS method → §4.1 ITB benchmark → §5.2 Main results (incl. taxonomy + universality) → §5.3 Analysis → §5.5–5.6 remaining experiments.

---

## 🖼️ 3 FIGURES/TABLES WHOSE CAPTION DID NOT MAKE SENSE WITHOUT RE-READING THE BODY

### 1. **Figure 1** (Calibration collapse example)
> *"Row 3: Std VIB assigns 81–96% melanoma probability under any heavy degradation (red); QCTS (orange) brings predictions down by 13–14 pp without retraining."*

**Problem:** "Std VIB" and "QCTS" are undefined at this point in a linear read. The caption says "red" and "orange" but the figure (as described in text) presumably uses colors to distinguish methods — a black-and-white print reader is lost. Also, "pp" (percentage points) is ambiguous to a non-native reader. The caption uses the figure to *argue* ("Takeaway: a quality-aware post-hoc correction softens exactly the cases…") rather than to *describe*, making it a mini-abstract rather than a caption.

### 2. **Table 1** (Main results)
> *"Subscripts are half-widths of 1,000-iter bootstrap 95% CIs. Bold/underline: best/second per column."*

**Problem:** The table uses **± notation** (e.g., "0.751±0.072"), not subscripts. The word "subscripts" is factually wrong for the formatting shown. On first read, I searched for actual subscripts and found none. This mismatch wastes the reader's attention. Also, the distinction between bold (best) and underline (second) for ECE columns is ambiguous because *lower is better* for ECE but *higher is better* for AUC; the caption doesn't clarify whether "best" means the directionally-optimal value.

### 3. **Figure 2** (Method overview)
> *"(a) ITB construction: … 149,100 quality annotations total. (b) QCTS architecture: … Learnable: (T₀, α) 2 params, no retraining. α=0 recovers standard TS."*

**Problem:** The caption is 214 words long and tries to explain the entire method pipeline. "VisiScore-Net" appears in the figure but is never defined in the caption or the main text before Appendix A. The caption says "q̄ ∈ [0,1]" but the figure shows q ∈ [0,1]⁵ (5-dimensional) → q̄ (scalar) — the dimensionality reduction is implicit. The "Takeaway" sentence ("ITB and QCTS share a single per-image q̄") assumes the reader already understands what q̄ is and why sharing it matters.

---

## 📝 ONE-PARAGRAPH PARAPHRASE OF THE PAPER'S CONTRIBUTION

The paper identifies a previously undocumented failure mode: standard post-hoc calibration methods (temperature scaling, MC dropout, deep ensembles) produce models that are confidently wrong on low-quality images — a dangerous property for dermatology AI deployed on consumer smartphones. The authors build a benchmark (ITB) that stratifies test images by a 5-dimensional quality score and defines a new metric (QCDI) to quantify how much calibration degrades as image quality drops. Their key empirical finding is that temperature scaling — the most common calibration fix — can actually *reverse* a model's entropy–quality correlation, making it *less* cautious on degraded inputs. Their proposed fix, QCTS, replaces temperature scaling's single scalar T with a 2-parameter function T(q̄) = softplus(T₀ + α(1−q̄)) that *increases* temperature (softens predictions) specifically for low-quality images. This requires no retraining, fits in under 200 L-BFGS iterations on a validation set, and reduces low-quality calibration error by ~46% while leaving high-quality performance unchanged. They show the approach transfers across ResNet, ViT, ConvNeXt, and Swin backbones without modification, and they demonstrate that the quality signal must be domain-specific (a generic IQA like BRISQUE doesn't work). The contribution is a lightweight, deployable safety patch for any frozen classifier that receives per-image quality scores.

---

## ⚠️ BRUTALLY HONEST FLAGS

1. **The paper assumes the reader knows VIB deeply.** Std VIB is the primary backbone for every experiment, yet its mechanics — what β does, what the latent Z is, how it differs from a standard classifier — are never explained. A CV reviewer without IB background (which is most of us) will feel this gap acutely by page 3.

2. **The PAC-Bayes paragraph is dead weight.** It is explicitly non-contributory ("motivating sketch… left to future work") and uses notation (KL divergence between posterior and prior over… what? Model weights? Predictions?) that is undefined. A reviewer will either skip it or penalize it. Remove it or make it a real contribution.

3. **The ρ-reversal finding is fascinating but the explanation is thin.** The paper's strongest result — "TS flips ρ from −0.153 to +0.241" — gets one paragraph of interpretation in §5.2. For a paper whose entire motivation rests on this observation, I expected a dedicated analysis (e.g., per-bin breakdown of *which* predictions TS moves in the wrong direction). The mechanism remains somewhat hand-wavy.

4. **"Quality-aware" vs. "quality-confused" is under-explained.** The ρ < −0.15 threshold for "genuine quality-awareness" appears once, with no ablation on the threshold value. Why −0.15 and not −0.10 or −0.20? A reviewer will ask.
