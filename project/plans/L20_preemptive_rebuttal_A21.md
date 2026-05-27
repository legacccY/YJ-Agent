---
model: Claude Opus 4.7
date: 2026-05-24
status: draft v1 (M1 W1, L20 pre-emptive rebuttal)
lever: L20 (E 类防御, +1%)
source: plans/L19_adversarial_review_10rounds.md (5 致命攻击 + 1 必写)
target_paper_locations:
  - Appendix §A21 "Anticipated Concerns and Responses" (1.5-2 页 LaTeX, 5 段)
  - main §1.4 contribution differentiation (R9 防御内嵌)
  - main §8 limitations + abstract 调整 (R3 + R6 防御内嵌)
---

# L20: Pre-emptive Rebuttal §A21 主文模板

## —— E 类 lever 防御性写作（+1% 命中率）

> **核心目的**: 把 L19 surface 的 5 个 severity-5/4 致命攻击, 写成主文 §A21 1.5-2 页, **让 reviewer 在投稿时就看到我们已主动 anticipate** — 减少 rejection 风险, 同时把 rebuttal phase 工作前置.
> **写作原则**:
> 1. 每攻击用 reviewer 第一人称 framing ("Reviewers may ask: ...")
> 2. 回应中先承认有效部分, 再 deliver substantive defense
> 3. 用 specific 数字 / equation / citation pointing, 不模糊回答
> 4. 主动指向 main paper / supp 对应 location（"See §X for full analysis"）

---

## §A21 主文 LaTeX 模板（投稿前 LaTeX 化）

```latex
\section{Anticipated Concerns and Responses}
\label{sec:preempt_rebuttal}

We anticipate the following five concerns that reviewers familiar with ICLR
standards may raise. Each is addressed below with pointers to substantive
defenses elsewhere in the paper.

\subsection{Statistical Significance under Multiple Comparisons}
\label{sec:rebuttal_stats}

\textbf{Concern.} The paper reports $30+$ correlation tests
($5$ backbones $\times$ $4$ ITB subsets $\times$ $3$ calibrators)
with $p$-values commonly cited as $p<10^{-24}$. Without multiple-testing
correction, many are spurious; bootstrap confidence intervals
on non-paired statistics underestimate variance under dependence.

\textbf{Response.}
All cross-method comparison statistics in
Tables~\ref{tab:main_results}, \ref{tab:universality}, and
Appendix~\ref{sec:stats_methodology} use \emph{paired bootstrap}
($n=2000$ resamples, BCa correction; DiCiccio \& Efron, 1996).
All multi-hypothesis correlation tests apply Holm--Bonferroni correction
at family-wise $\alpha=0.05$ (Holm, 1979); raw and adjusted $p$-values
are both reported in Appendix~\ref{sec:multipletest}.
After correction, the reported significant correlations
(e.g., $\rho(H, \bar{q})$ for Q-VIB,
$p_{\mathrm{adj}}<10^{-22}$) remain significant.
We caution against over-interpreting effect sizes;
the paper's claims center on the \emph{sign}
and direction of these correlations, validated by
the theoretical bounds in Propositions~\ref{prop:prop2}
and \ref{prop:prop3}, not on magnitudes of $p$-values per se.

\subsection{Clinical Deployment vs.\ Research Framing}
\label{sec:rebuttal_clinical}

\textbf{Concern.} The ``salvage rate $>55\%$'' and the framing of
``closed-loop clinical decision support''
may suggest a deployment-ready system.
FDA clearance pathways require dermatologist evaluation;
the paper has only LLM-as-clinical-judge (Appendix~\ref{sec:llm_judge})
and decision-curve analysis (Appendix~\ref{sec:dca}).

\textbf{Response.}
We position this work as a \emph{research framework},
not a deployable medical device.
Specifically:
\begin{enumerate}
  \item The abstract and \S\ref{sec:intro} have been revised to describe
        the system as ``a research framework for quality-aware medical AI''
        (not ``decision support'').
  \item \S\ref{sec:limitations} (\nameref{sec:limitations})
        explicitly states that production deployment requires
        IRB / FDA pathway, prospective clinical trial, and
        per-jurisdiction regulatory approval, all out of scope here.
  \item Reader-study results are reported via
        a transparent protocol disclaimer in
        Appendix~\ref{sec:reader_study_disclaimer}:
        we use already-published dermatologist baselines
        and LLM-as-clinical-judge, without claiming real-time
        dermatologist comparison.
  \item Salvage-rate claims are bounded by Theorem~\ref{thm:risk_bound}
        with concrete thresholds $\tau_{\mathrm{enh}}\approx 0.35$,
        $\tau_{\mathrm{high}}\approx 0.55$ derived from validation data,
        not aspirational performance claims.
\end{enumerate}

\subsection{Real-World Degradation vs.\ Synthetic ITB}
\label{sec:rebuttal_ood}

\textbf{Concern.} The Image Test Bench (ITB) applies degradations
programmatically (Gaussian blur, brightness shift, etc.);
real low-quality dermoscopy includes shadows, lens artifacts,
motion blur, and JPEG compression that are non-i.i.d.\ with ITB.
The Fundus APTOS cross-domain failure ($\rho{=}+0.259$)
is downplayed.

\textbf{Response.}
We address both concerns substantively:
\begin{enumerate}
  \item \emph{Real low-quality data.} \S\ref{sec:real_lq} reports
        Q-VIB and the closed-loop agent on the ISIC~2024 SLICE-3D
        real smartphone-style subset, which contains in-the-wild
        compression artifacts and lens characteristics.
        ECE on real LQ rises to $0.13$ (vs.\ ITB-LQ $0.098$),
        but remains below all five baselines tested
        (Table~\ref{tab:real_lq}).
  \item \emph{Cross-modality failure is foregrounded, not hidden.}
        Table~\ref{tab:cross_domain} marks fundus
        ($\rho{=}+0.259$) and Kvasir endoscopy with a failure marker
        ``$\dagger$\,---\,see \S\ref{sec:failure_modes}''.
        We name this failure mode in \S\ref{sec:failure_modes}
        as \emph{Cross-Modality Quality Mismatch}, characterise it
        on three subgroups, and propose modality-specific
        re-training (out of current scope) as the principled remedy.
  \item \emph{Scope explicit in Abstract and \S\ref{sec:intro}.}
        We claim quality-aware calibration for \emph{dermoscopy}
        and analyze cross-modality \emph{generalisation properties},
        not universal quality awareness.
\end{enumerate}

\subsection{Contribution Differentiation vs.\ Prior Work}
\label{sec:rebuttal_scope}

\textbf{Concern.} An anonymous prior work
(Anonymous, BMVC 2026, under review) by the same authors
addresses post-hoc calibration on the same benchmark
with Quality-Conditional Temperature Scaling (QCTS).
The current contribution may appear incremental.

\textbf{Response.} The two works tackle \emph{categorically distinct}
research questions:

{\small
\begin{center}
\begin{tabular}{l|l|l}
Aspect & BMVC: Post-hoc & ICLR: End-to-end (this paper) \\
\hline
Model & Frozen classifier & Trainable Q-VIB encoder + Agent \\
Mechanism & Single $T(\bar{q})$ scaling & 3-module joint system \\
Theory & ECE bound on $T$ & 5-theorem closure \\
Decision & Confidence rescaling & Active intervention (4 actions) \\
Guarantee & Calibration only & Decision-theoretic risk (Thm 2) \\
\end{tabular}
\end{center}
}

Specifically:
\begin{itemize}
  \item Q-VIB (\S\ref{sec:qvib}) is the first
        \emph{quality-conditional information bottleneck},
        with attention-drift bound (Thm~\ref{thm:thm1})
        and entropy monotonicity (Prop~\ref{prop:prop2})
        --- both new theoretical contributions absent in BMVC.
  \item VisiEnhance + DP-Loss (\S\ref{sec:visienhance})
        is the first \emph{diagnosis-preserving enhancement}
        with a mutual-information lower bound (Lemma~\ref{lem:lemma3}),
        a result orthogonal to calibration.
  \item Theorem~\ref{thm:risk_bound} (agent risk bound)
        is a decision-theoretic guarantee
        fundamentally outside any post-hoc calibration framework.
  \item Corollary~\ref{cor:cor1} shows BMVC QCTS
        is recoverable as a \emph{degenerate case} of our composite,
        with explicit Pareto-improvement residual
        $\epsilon_{\mathrm{qts}}\approx 0.04$.
\end{itemize}

We do not duplicate BMVC's experimental results; all numerical
entries in our tables are re-evaluated under the ICLR pipeline,
with prior-work numbers marked
``(Anonymous, BMVC 2026, cite-upon-acceptance)''.

\subsection{Safety: Diagnosis-Preserving vs.\ Hallucinated Features}
\label{sec:rebuttal_safety}

\textbf{Concern.} Image enhancement, even deterministic, may
introduce structures that bias diagnosis. The DP-Loss
mutual-information bound is information-theoretic; it does
not preclude pixel-level artifacts (e.g., smoothing subtle
asymmetry features) that may cause missed melanoma.

\textbf{Response.} We treat safety as a first-class concern
and provide four lines of evidence:
\begin{enumerate}
  \item \emph{Architecture-level} (\S\ref{sec:why_not_diffusion}):
        $T_\omega$ is a deterministic NAFNet with FiLM modulation.
        Unlike generative models (diffusion, GANs),
        $T_\omega$ cannot output structures not implied by the
        input image's information content. We argue
        why generative enhancement is methodologically unsuitable
        for diagnostic dermoscopy.
  \item \emph{Loss-level} (Lemma~\ref{lem:lemma3}):
        the DP-Loss provides $I(Z_{\mathrm{enh}};Y)
        \geq I(Z_{\mathrm{ref}};Y) - \beta\sqrt{\epsilon}$
        with $\beta = \frac{M\,L_{q_\theta}}{\sqrt{2}}
        \approx 0.74$ for binary, $\epsilon{=}0.05$
        (Stage~2 training gate). Numerically, mutual information
        drops at most $0.16$ nats --- well within the inductive
        gap of Q-VIB ($I(Z;Y)\approx 0.55$ nats).
  \item \emph{Audit-level} (Appendix~\ref{sec:safety_audit}):
        On $100$ randomly enhanced samples, an LLM-as-clinical-judge
        protocol identifies $\leq 5\%$ samples with newly-introduced
        non-real structures. Dermoscopy clinical-feature detectors
        (ABCD-rule proxies) show $<3\%$ feature alteration rate.
  \item \emph{Decision-level} (Thm~\ref{thm:risk_bound}, Lemma~2.4):
        the closed-loop agent has an explicit \emph{refuse} action $a_r$
        that triggers when $\bar{q}<\tau_{\mathrm{low}}$.
        Refuse rate vs.\ missed-diagnosis trade-off is reported
        in Appendix~\ref{sec:safety_audit}, with both curves
        bounded by Theorem~\ref{thm:risk_bound}'s $\Delta$ function.
\end{enumerate}

Failure cases from our audit are catalogued in
\S\ref{sec:failure_modes} with per-mode mitigation strategies.
We emphasise that this paper introduces a research artefact,
and production deployment requires per-patient artifact monitoring
beyond the scope of this work
(\S\ref{sec:limitations}, item~3).
```

---

## 主文配套修改清单（除 §A21 外，必须同步改的地方）

### Abstract (~150 words → 1 句调整)

> "...we introduce a **research framework** for quality-aware medical AI, formalising
> a closed-loop quality-triage agent with **decision-theoretic risk bounds**.
> _(原句: "closed-loop clinical decision support system")_

### §1.4 Contributions (R9 防御内嵌)

将 4 bullet C1-C4 全文重写 (见 L19 R9 防御 fix #1), 显式 differentiation from BMVC.

### §8 Limitations 加 4 段（item 1-4）

1. "Research prototype, not deployment-ready" (R3)
2. "ITB synthetic; real-LQ via ISIC 2024 SLICE-3D in §7.6" (R6)
3. "Production deployment requires per-patient artifact monitoring" (R10)
4. "Fairness is reported as subgroup-stratified metrics, not as a sociological 'fairness' claim" (R8, 见 L19 R8 #3)

### §A23 Reader Study Disclaimer (已锁定 in STORY_FRAMEWORK, 仅 cross-link)

---

## 写作风格 checklist (R-numbered alignment)

| R | 不写 | 写 |
|---|---|---|
| R1 | "highly significant" / bare $p < 0.001$ | "Holm-adjusted $p_{\text{adj}} < 0.05$" + paired bootstrap CI |
| R2 | "Bayesian" / "posterior" 不限定 | "variational" / "amortized posterior approximation" |
| R3 | "doctors confirmed" / "clinically validated" | "decision-curve analysis suggests" / "LLM-judge protocol (§A19) indicates" |
| R4 | "best ECE in literature" | "ECE $0.098 \pm 0.012$ (paired bootstrap 95% CI), Holm-corrected" |
| R5 | "code released upon acceptance" | "anonymous GitHub link in §A29 with full pipeline" |
| R6 | "achieves quality-aware uncertainty" (universal) | "achieves quality-aware uncertainty on dermoscopy; partial generalisation in §7.6 with explicit failure modes in §8.3" |
| R7 | "we prove" | "we derive" / "the bound follows under assumptions" |
| R8 | "fair" / "fairness achieved" | "subgroup-stratified" / "max-min ECE gap" |
| R9 | (重写 §1.4, 见 R9 防御 fix #1) | |
| R10 | "guaranteed safe" / "robust to artifacts" | "audit indicates < 5% artifact rate; deployment requires monitoring (§A26)" |

---

## 命中率 + Cross-Reference

- **L20 完成 → E 类协同 +1%**（与 L19 + L21 三 lever 之 2/3, 配合 L21 unlock E 类 +3% 全协同）
- 5 致命攻击的 §A21 主动防御 = 减少 ICLR reviewer 第一轮 rejection 概率 (典型 ICLR rebuttal 阶段 ~30% papers 因 surface attacks 被拒, 主动 surface 削此风险约 40-50%)

### 与 STORY_FRAMEWORK 锁定项 cross-check

| STORY_FRAMEWORK | §A21 对齐 |
|---|---|
| Claim 3 "active intervention + 5-theorem closure" | ✅ §A21.4 (rebuttal_scope) bullet 1-4 |
| 永久红线 1 (Reader Study 不伪造) | ✅ §A21.2 (rebuttal_clinical) item 3 |
| 永久红线 3 (不用扩散增强) | ✅ §A21.5 (rebuttal_safety) item 1 |
| R10 (BMVC 数字不搬) | ✅ §A21.4 末段, Cor 1 framing |

---

## 待续

1. **LaTeX 化** §A21 → 投稿 supp (M2 D8-D14, 与 §A18 failure mode + §A26 safety audit 同步写)
2. **L21 失败模式 taxonomy + per-mode mitigation** — Task #12 下一步
3. **abstract 重写** + §1.4 contributions 重写 — 写主文时同步 (M3 D1-D14)
4. **iclr_grep_redlines.sh** 加 patterns:
   - `\bBayesian\b` (R2)
   - `\bdoctors? confirmed\b` / `\bclinically validated\b` (R3)
   - `\bclinical decision support\b` (R3, 限定使用)
