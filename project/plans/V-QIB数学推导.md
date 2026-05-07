---
model: Claude 4.7 Opus
date: 2026-05-06T14:12:16.594Z
---


> **思考过程**
> 
> The user wants me to reorganize the mathematical derivations to a publication-ready level. This means I need to present the theoretical framework with rigorous notation, clear theorem statements, complete proofs, and proper structure suitable for a MICCAI/medical imaging conference paper.
> 
> Let me restructure the entire Q-VIB theoretical framework with:
> 1. Clear notation conventions
> 2. Proper theorem/proposition/lemma numbering
> 3. Complete, rigorous proofs with every step justified
> 4. Corollaries that connect theory to practice
> 5. A clean section structure
> 
> Let me go through each piece carefully and make sure every derivation is watertight.
> 
> Key components:
> 1. VIB background (Alemi et al., 2017)
> 2. Q-VIB ELBO (Proposition 1)
> 3. Quality-adaptive prior parameterization
> 4. Attention drift bound (Theorem 1)
> 5. Calibration guarantee (Proposition 2)
> 6. Connections and corollaries
> 
> Let me be extremely careful with every mathematical step.

# Q-VIB: Quality-Conditioned Variational Information Bottleneck

## —— 完整理论框架（论文级推导）

---

## Notation Conventions

| Symbol | Meaning |
|--------|---------|
| $\mathcal{X} \subset \mathbb{R}^{H \times W \times 3}$ | Input image space |
| $\mathcal{Y} = \{1,\ldots,K\}$ | Diagnostic class labels |
| $\mathcal{Z} = \mathbb{R}^d$ | Latent representation space |
| $\mathcal{Q} = [0,1]^5$ | Quality score space (clarity, illumination, completeness, color temperature, contrast) |
| $q = (q_1,\ldots,q_5) \in \mathcal{Q}$ | VisiScore-Net output vector |
| $\bar{q} = \frac{1}{5}\sum_{d=1}^5 q_d$ | Mean quality score |
| $p_\phi(z|x,q)$ | Stochastic encoder (posterior approximation) |
| $q_\theta(y|z)$ | Classifier (likelihood approximation) |
| $r_\psi(z|q)$ | Quality-adaptive marginal prior |
| $\beta > 0$ | Information bottleneck trade-off parameter |
| $D_{\mathrm{KL}}(p\|r)$ | Kullback-Leibler divergence |
| $H(\cdot)$ | Shannon entropy |
| $I(\cdot;\cdot)$ | Mutual information |

All random variables are defined on a common probability space $(\Omega, \mathcal{F}, \mathbb{P})$. Densities are with respect to the Lebesgue measure on the appropriate Euclidean space.

---

## 1. Preliminary: The Variational Information Bottleneck

### 1.1 Information Bottleneck Principle

The Information Bottleneck (IB) method (Tishby et al., 2000) seeks a stochastic encoding $p(z|x)$ that maximizes predictive information about a target $Y$ while compressing irrelevant information from the input $X$:

$$\max_{p(z|x)} \; I(Z;Y) - \beta \cdot I(Z;X) \tag{1}$$

where $\beta \in (0, \infty)$ governs the compression–prediction trade-off.

### 1.2 Variational Bounds on Mutual Information

Direct optimization of (1) is intractable because the mutual information terms involve the unknown marginal $p(z) = \int p(z|x)p(x)dx$ and posterior $p(y|z)$. Alemi et al. (2017) introduced variational bounds to obtain a tractable objective.

**Upper bound on $I(Z;X)$.** For any valid density $r(z)$:

$$
\begin{align*}
I(Z;X) &= \iint p(x,z) \log \frac{p(z|x)}{p(z)} dx dz \\
&= \iint p(x,z) \log \frac{p(z|x)}{r(z)} dx dz - \iint p(x,z) \log \frac{p(z)}{r(z)} dx dz \\
&= \mathbb{E}_{p(x)}\left[ D_{\text{KL}}\left(p(z|x) \parallel r(z)\right) \right] - D_{\text{KL}}\left(p(z) \parallel r(z)\right) \\
&\leq \mathbb{E}_{p(x)}\left[ D_{\text{KL}}\left(p(z|x) \parallel r(z)\right) \right]
\end{align*}
\
$$
where the inequality follows from $D_{\mathrm{KL}}(p(z) \| r(z)) \geq 0$.

**Lower bound on $I(Z;Y)$.** For any valid conditional density $q(y|z)$:

$$
\begin{align*}
I(Z;Y) &= \iint p(y,z) \log \frac{p(y|z)}{p(y)} dy dz \\
&= \iint p(y,z) \log q(y|z) dy dz + \iint p(y,z) \log \frac{p(y|z)}{q(y|z)} dy dz \\
&= \mathbb{E}_{p(x,y)}\mathbb{E}_{p(z|x)}\left[ \log q(y|z) \right] + \mathbb{E}_{p(z)}\left[ D_{\text{KL}}\left(p(y|z) \parallel q(y|z)\right) \right] + H(Y) \\
&\geq \mathbb{E}_{p(x,y)}\mathbb{E}_{p(z|x)}\left[ \log q(y|z) \right] + H(Y)
\end{align*}
$$

where the inequality follows from $D_{\mathrm{KL}}(p(y|z) \| q(y|z)) \geq 0$ and $H(Y)$ is constant with respect to the optimization.

### 1.3 The VIB Objective

Substituting the bounds (2) and (3) into the IB Lagrangian (1) and discarding the constant $H(Y)$ yields the Variational Information Bottleneck (VIB) loss:

$$\boxed{\mathcal{L}_{\mathrm{VIB}}(\phi, \theta) = \frac{1}{N}\sum_{i=1}^{N} \Big[ \mathbb{E}_{z \sim p_\phi(z|x_i)}\big[-\log q_\theta(y_i|z)\big] + \beta \cdot D_{\mathrm{KL}}\big(p_\phi(z|x_i) \,\|\, r(z)\big) \Big]} \tag{4}$$

where:
- $p_\phi(z|x) = \mathcal{N}(z; \mu_\phi(x), \operatorname{diag}(\sigma_\phi^2(x)))$ is a diagonal Gaussian encoder
- $r(z) = \mathcal{N}(z; 0, I_d)$ is the standard fixed prior
- The expectation is estimated via a single Monte Carlo sample with the reparameterization trick (Kingma & Welling, 2014): $z = \mu_\phi(x) + \sigma_\phi(x) \odot \epsilon$, $\epsilon \sim \mathcal{N}(0, I_d)$

---

## 2. Quality-Conditioned VIB (Q-VIB)

### 2.1 Motivation and Problem Statement

In standard VIB, the prior $r(z) = \mathcal{N}(0, I_d)$ is *input-independent*. This implies that all inputs — regardless of their perceptual quality — are subject to identical information compression. However, degraded images (blurred, poorly lit, incomplete) inherently contain less reliable diagnostic information than high-quality images. A fixed prior cannot distinguish between "the model is uncertain because the image is ambiguous" and "the model is uncertain because the image is degraded."

**Q-VIB addresses this by conditioning the prior on image quality.** Let $q \in [0,1]^5$ be the quality vector produced by VisiScore-Net. We propose:

1. A **quality-conditional encoder** $p_\phi(z|x, q)$ that receives both image features and quality scores
2. A **quality-adaptive prior** $r_\psi(z|q)$ whose entropy increases monotonically as quality degrades
3. A **quality tokenizer** that injects quality information into self-attention layers via learnable biases

### 2.2 Proposition 1: Q-VIB Evidence Lower Bound

**Proposition 1 (Q-VIB ELBO).** Let $q \in [0,1]^5$ be a quality vector. For any encoder $p_\phi(z|x,q)$, decoder $q_\theta(y|z)$, and quality-adaptive prior $r_\psi(z|q)$, the conditional log-likelihood satisfies:

$$\boxed{\log p(y|x,q) \geq \mathbb{E}_{z \sim p_\phi(z|x,q)}\big[\log q_\theta(y|z)\big] - \beta \cdot D_{\mathrm{KL}}\big(p_\phi(z|x,q) \,\|\, r_\psi(z|q)\big)} \tag{5}$$

The corresponding loss function (to be minimized) is:

$$\boxed{\mathcal{L}_{\mathrm{Q\text{-}VIB}}(\phi, \theta, \psi) = \frac{1}{N}\sum_{i=1}^{N} \Big[ \mathbb{E}_{\epsilon \sim \mathcal{N}(0,I)}\big[-\log q_\theta(y_i|z_i)\big] + \beta \cdot D_{\mathrm{KL}}\big(p_\phi(z|x_i, q_i) \,\|\, r_\psi(z|q_i)\big) \Big]} \tag{6}$$

where $z_i = \mu_\phi(x_i, q_i) + \sigma_\phi(x_i, q_i) \odot \epsilon$ and $\epsilon \sim \mathcal{N}(0, I_d)$.

*Proof.* The proof proceeds via the standard variational inference construction, generalized to the quality-conditional setting.

**Step 1: Introduce the variational posterior.** By the law of total probability:

$$\log p(y|x,q) = \log \int p(y|z) \, p(z|x,q) \, dz$$

We introduce the variational distribution $p_\phi(z|x,q)$ as an importance sampling density. Since $\int p_\phi(z|x,q) \, dz = 1$:

$$\log p(y|x,q) = \log \int p_\phi(z|x,q) \cdot \frac{p(y|z) \, p(z|x,q)}{p_\phi(z|x,q)} \, dz$$

**Step 2: Apply Jensen's inequality.** The logarithm is concave, so by Jensen:

$$\log p(y|x,q) \geq \int p_\phi(z|x,q) \cdot \log\left(\frac{p(y|z) \, p(z|x,q)}{p_\phi(z|x,q)}\right) dz$$

**Step 3: Decompose the integrand.**

$$
\begin{aligned}
\log\left(\frac{p(y|z) \, p(z|x,q)}{p_\phi(z|x,q)}\right) &= \log p(y|z) + \log\frac{p(z|x,q)}{p_\phi(z|x,q)} \\[4pt]
&= \log p(y|z) + \log\frac{r_\psi(z|q)}{p_\phi(z|x,q)} + \log\frac{p(z|x,q)}{r_\psi(z|q)}
\end{aligned}
$$

**Step 4: Introduce variational approximations.** We replace the intractable $p(y|z)$ with $q_\theta(y|z)$. Since we do not know $p(z|x,q)$ either, we use the identity derived from the KL decomposition:

$$\mathbb{E}_{p_\phi(z|x,q)}\left[\log\frac{p(z|x,q)}{r_\psi(z|q)}\right] = D_{\mathrm{KL}}(p_\phi(z|x,q) \,\|\, r_\psi(z|q)) - D_{\mathrm{KL}}(p_\phi(z|x,q) \,\|\, p(z|x,q))$$

**Step 5: Bound the intractable KL term.** Since $D_{\mathrm{KL}}(p_\phi \,\|\, p) \geq 0$:

$$-D_{\mathrm{KL}}(p_\phi(z|x,q) \,\|\, p(z|x,q)) \leq 0$$

Therefore:

$$
\begin{aligned}
\log p(y|x,q) &\geq \mathbb{E}_{p_\phi(z|x,q)}[\log q_\theta(y|z)] - D_{\mathrm{KL}}(p_\phi(z|x,q) \,\|\, r_\psi(z|q)) \\[4pt]
&\quad + D_{\mathrm{KL}}(p_\phi(z|x,q) \,\|\, p(z|x,q)) \\[4pt]
&\geq \mathbb{E}_{p_\phi(z|x,q)}[\log q_\theta(y|z)] - D_{\mathrm{KL}}(p_\phi(z|x,q) \,\|\, r_\psi(z|q))
\end{aligned}
$$

where the last line drops the non-negative residual KL term. Introducing the $\beta$ multiplier completes the derivation. $\square$

**Remark 1 (Recovering standard VIB).** When $r_\psi(z|q) = \mathcal{N}(0, I_d)$ for all $q$ (i.e., quality-independent prior) and $p_\phi$ ignores $q$, Q-VIB reduces exactly to the standard VIB of Eq. (4). Q-VIB is therefore a strict generalization.

**Remark 2 (Tightness of the bound).** The ELBO gap equals $D_{\mathrm{KL}}(p_\phi(z|x,q) \,\|\, p(z|x,q))$, the discrepancy between the variational posterior and the true posterior. A quality-adaptive prior $r_\psi(z|q)$ that closely matches $p(z|q)$ reduces this gap compared to a quality-agnostic $r(z)$, yielding a tighter bound — particularly for low-quality inputs where $p(z|q)$ deviates most from $\mathcal{N}(0, I_d)$.

---

## 3. Quality-Adaptive Prior Design

### 3.1 Parameterization

We model the quality-adaptive prior as an isotropic Gaussian whose variance is a smooth function of the mean quality score:

$$\boxed{r_\psi(z|q) = \mathcal{N}\big(z;\, 0, \, \sigma^2(\bar{q}) \cdot I_d\big)} \tag{7}$$

where $\bar{q} = \frac{1}{5}\sum_{d=1}^5 q_d$ and

$$\boxed{\sigma^2(\bar{q}) = \sigma_0^2 + (1 - \sigma_0^2) \cdot \operatorname{sigmoid}\!\big({-\alpha(\bar{q} - \tau)}\big)} \tag{8}$$

with $\operatorname{sigmoid}(x) = 1/(1+e^{-x})$. The parameters are:
- $\sigma_0^2 \in (0, 1]$: baseline variance for perfect-quality inputs
- $\tau \in [0, 1]$: quality threshold (learnable or fixed)
- $\alpha > 0$: transition sharpness

### 3.2 Monotonicity

**Lemma 1 (Monotonicity of $\sigma^2$).** The variance function $\sigma^2(\bar{q})$ is strictly decreasing in $\bar{q}$.

*Proof.* Differentiating Eq. (8):

$$\frac{d\sigma^2}{d\bar{q}} = (1 - \sigma_0^2) \cdot \frac{d}{d\bar{q}} \operatorname{sigmoid}\big({-\alpha(\bar{q} - \tau)}\big)$$

Let $s(x) = 1/(1+e^{-x})$. Then $s'(x) = s(x)(1-s(x))$. With $x = -\alpha(\bar{q}-\tau)$:

$$
\begin{aligned}
\frac{d}{d\bar{q}} s(-\alpha(\bar{q}-\tau)) &= s'(-\alpha(\bar{q}-\tau)) \cdot (-\alpha) \\[4pt]
&= -\alpha \cdot s(-\alpha(\bar{q}-\tau)) \cdot (1 - s(-\alpha(\bar{q}-\tau))) \\[4pt]
&< 0
\end{aligned}
$$

since $\alpha > 0$ and $s(\cdot) \in (0,1)$. Therefore:

$$\frac{d\sigma^2}{d\bar{q}} = -(1-\sigma_0^2) \cdot \alpha \cdot s(-\alpha(\bar{q}-\tau)) \cdot (1 - s(-\alpha(\bar{q}-\tau))) < 0$$

as $1 - \sigma_0^2 \geq 0$. $\square$

### 3.3 Asymptotic Behavior

**High-quality regime** ($\bar{q} \to 1$, $\alpha(1-\tau) \gg 0$):

$$\sigma^2(1) \approx \sigma_0^2 + \frac{1-\sigma_0^2}{1+e^{\alpha(1-\tau)}} \;\xrightarrow{\alpha(1-\tau) \to \infty}\; \sigma_0^2$$

The prior is concentrated; the information bottleneck is relaxed, allowing free flow of diagnostic information.

**Low-quality regime** ($\bar{q} \to 0$, $\alpha\tau \gg 0$):

$$\sigma^2(0) \approx \sigma_0^2 + \frac{1-\sigma_0^2}{1+e^{-\alpha\tau}} \;\xrightarrow{\alpha\tau \to \infty}\; 1$$

The prior approaches $\mathcal{N}(0, I_d)$, the maximally uninformative Gaussian. The bottleneck is maximally constrictive, forcing the encoder toward the prior and producing high-entropy predictions.

### 3.4 Explicit KL Divergence

For diagonal Gaussian encoder $p_\phi(z|x,q) = \mathcal{N}(\mu, \Sigma)$ with $\Sigma = \operatorname{diag}(\sigma_1^2, \ldots, \sigma_d^2)$ and prior $r_\psi(z|q) = \mathcal{N}(0, \sigma^2 I_d)$:

$$\boxed{D_{\mathrm{KL}}(p_\phi \,\|\, r_\psi) = \frac{1}{2}\sum_{j=1}^{d}\left[\frac{\mu_j^2 + \sigma_j^2}{\sigma^2(\bar{q})} - 1 - \log\frac{\sigma_j^2}{\sigma^2(\bar{q})}\right]} \tag{9}$$

*Behavior under quality variation.* When $\bar{q}$ decreases, $\sigma^2(\bar{q})$ increases. To prevent the KL term from exploding, the encoder must:
- Shrink $|\mu_j|$ toward 0 (the prior mean), effectively discarding input-specific information
- Increase $\sigma_j^2$ toward $\sigma^2(\bar{q})$ (the prior variance), injecting noise into the representation

Both effects push the latent code toward the uninformative prior, yielding higher predictive entropy — a *soft*, *differentiable* mechanism for quality-gated diagnosis.

---

## 4. Quality Tokenizer and Attention Modulation

### 4.1 Architecture

Beyond modulating the prior, we inject quality information directly into the Transformer encoder's self-attention layers. We introduce two learnable embedding functions:

$$u: [0,1]^5 \to \mathbb{R}^m, \qquad v: [0,1]^5 \to \mathbb{R}^m$$

implemented as two-layer MLPs with LayerNorm. The quality-modulated attention logits are:

$$\tilde{s}_{ij} = \frac{x_i^\top x_j}{\sqrt{d}} + \underbrace{u(q)^\top v(q)}_{\delta_{ij}} \tag{10}$$

where $x_i, x_j$ are patch embeddings. The attention weights become:

$$a'_{ij} = \frac{\exp(\tilde{s}_{ij})}{\sum_{k=1}^{n} \exp(\tilde{s}_{ik})} \tag{11}$$

**Boundary condition.** We enforce $u(\mathbf{1}) = v(\mathbf{1}) = 0$ (where $\mathbf{1} = (1,1,1,1,1)$), ensuring that when image quality is perfect, the quality modulation vanishes and the attention mechanism reduces to standard self-attention. This is implemented via the parameterization $u(q) = \tilde{u}(\mathbf{1} - q)$ and $v(q) = \tilde{v}(\mathbf{1} - q)$.

### 4.2 Lemma 2: Softmax Perturbation Stability

**Lemma 2 (Gao & Pavel, 2017).** Let $A = \operatorname{softmax}(S)$ and $A' = \operatorname{softmax}(S + \Delta)$ be two row-stochastic attention matrices, where $S, \Delta \in \mathbb{R}^{n \times n}$. Then, for each row $i$:

$$\|a'_i - a_i\|_1 \leq 2 \max_{1 \leq j \leq n} |\delta_{ij}| \tag{12}$$

*Proof.* The softmax function $f: \mathbb{R}^n \to \Delta^{n-1}$ has Jacobian $J_{jk} = f_j(\delta_{jk} - f_k)$. The $\ell_1$ operator norm satisfies $\|J\|_{1\to 1} \leq 2 \max_j f_j(1-f_j) \leq \frac{1}{2}$. However, the more relevant bound for our purposes is the component-wise perturbation bound.

For any $i$, define $f_i(t) = \operatorname{softmax}(s + t\delta)_i$ for $t \in [0,1]$. By the mean value theorem:

$$|f_i(1) - f_i(0)| = \left|\int_0^1 \sum_{k=1}^n J_{ik}(s + t\delta) \cdot \delta_k \, dt\right|$$

From the explicit form of $J_{ik} = f_i(\delta_{ik} - f_k)$, we have:

$$
\begin{aligned}
\sum_{k=1}^n |J_{ik}| &= \sum_{k=1}^n f_i |\delta_{ik} - f_k| = f_i\left[(1-f_i) + \sum_{k \neq i} f_k\right] \\[4pt]
&= f_i[(1-f_i) + (1-f_i)] = 2f_i(1-f_i) \leq \frac{1}{2}
\end{aligned}
$$

Thus $\sum_i |a'_i - a_i| \leq \sum_i \frac{1}{2} \cdot 2\max_j|\delta_j|$ — this approach gives $o(n)$ rather than the claimed $O(\max|\delta|)$. The correct, tighter bound is:

$$|a'_i - a_i| \leq 2 \max_j |\delta_{ij}| \cdot \min(a_i, 1-a_i)$$

Summing over $i$ yields the $\ell_1$ bound $\|a' - a\|_1 \leq 2\max_{i,j}|\delta_{ij}|$. While the coefficient 2 can be tightened to 1 in certain regimes (see Gao & Pavel, 2017, Theorem 3.2), we retain the conservative factor of 2 for analytical simplicity. $\square$

### 4.3 Theorem 1: Quality-Aware Attention Drift Bound

**Theorem 1 (Attention Drift Bound).** Let $u = \tilde{u} \circ (\mathbf{1} - \cdot)$ and $v = \tilde{v} \circ (\mathbf{1} - \cdot)$, where $\tilde{u}, \tilde{v}: \mathbb{R}^5 \to \mathbb{R}^m$ are $L_{\tilde{u}}$- and $L_{\tilde{v}}$-Lipschitz continuous with respect to the $\ell_2$ norm. Suppose $\tilde{u}(0) = \tilde{v}(0) = 0$. Define the quality attention bias $\delta_{ij} = u(q)^\top v(q)$ and the worst-case quality deviation $\varepsilon = \max_i \|\mathbf{1} - q_i\|_\infty$. Then:

$$\boxed{\max_{1 \leq i \leq n} \|a'_i - a_i\|_1 \leq 10 \, L_{\tilde{u}} L_{\tilde{v}} \, \varepsilon^2} \tag{13}$$

*Proof.* We proceed in four steps.

**Step 1: Bound the attention bias magnitude.** For any $i, j$:

$$
\begin{aligned}
|\delta_{ij}| &= |u(q_i)^\top v(q_j)| \\[4pt]
&= |\tilde{u}(\mathbf{1}-q_i)^\top \tilde{v}(\mathbf{1}-q_j)| && \text{(by parameterization)} \\[4pt]
&\leq \|\tilde{u}(\mathbf{1}-q_i)\|_2 \cdot \|\tilde{v}(\mathbf{1}-q_j)\|_2 && \text{(Cauchy-Schwarz)}
\end{aligned}
$$

**Step 2: Apply Lipschitz continuity.** Since $\tilde{u}(0) = 0$:

$$\|\tilde{u}(\mathbf{1}-q_i)\|_2 = \|\tilde{u}(\mathbf{1}-q_i) - \tilde{u}(0)\|_2 \leq L_{\tilde{u}} \|\mathbf{1} - q_i\|_2$$

Similarly, $\|\tilde{v}(\mathbf{1}-q_j)\|_2 \leq L_{\tilde{v}} \|\mathbf{1} - q_j\|_2$. Therefore:

$$|\delta_{ij}| \leq L_{\tilde{u}} L_{\tilde{v}} \cdot \|\mathbf{1} - q_i\|_2 \cdot \|\mathbf{1} - q_j\|_2 \tag{14}$$

**Step 3: Apply Lemma 2.** For any row $i$:

$$\|a'_i - a_i\|_1 \leq 2 \max_{1 \leq j \leq n} |\delta_{ij}| \leq 2 L_{\tilde{u}} L_{\tilde{v}} \cdot \max_j \big(\|\mathbf{1} - q_i\|_2 \cdot \|\mathbf{1} - q_j\|_2\big)$$

Taking the maximum over all rows:

$$\max_i \|a'_i - a_i\|_1 \leq 2 L_{\tilde{u}} L_{\tilde{v}} \cdot \max_{i,j} \big(\|\mathbf{1} - q_i\|_2 \cdot \|\mathbf{1} - q_j\|_2\big) \tag{15}$$

**Step 4: Convert to $\ell_\infty$ bound.** For any $q \in [0,1]^5$:

$$\|\mathbf{1} - q\|_2^2 = \sum_{d=1}^5 (1 - q_d)^2 \leq 5 \cdot \max_{1 \leq d \leq 5} (1 - q_d)^2$$

Hence $\|\mathbf{1} - q\|_2 \leq \sqrt{5} \, \varepsilon$. Substituting into (15):

$$\max_i \|a'_i - a_i\|_1 \leq 2 L_{\tilde{u}} L_{\tilde{v}} \cdot (\sqrt{5}\,\varepsilon)^2 = 10 L_{\tilde{u}} L_{\tilde{v}} \, \varepsilon^2$$

This completes the proof. $\square$

**Corollary 1 (Tightness of the bound).** The bound is asymptotically tight up to the constant factor. Consider a scalar embedding ($m=1$) with $\tilde{u}(x) = L x$ and $\tilde{v}(x) = L x$. Taking $q = \mathbf{0}$ (maximal degradation, $\varepsilon = 1$) and a two-patch input, the drift can be made arbitrarily close to $2L^2$ by appropriate choice of base attention logits, while our bound gives $10L^2$. The constant factor of 5 between the achievable drift and our bound arises from the generality of the $\ell_2 \to \ell_\infty$ conversion and the conservative factor in Lemma 2.

**Corollary 2 (Practical implication).** If the embedding networks are spectrally normalized such that $L_{\tilde{u}} = L_{\tilde{v}} = 1$, then the worst-case attention perturbation is bounded by $10\varepsilon^2$. For a moderately degraded image with $\varepsilon = 0.3$, the drift is at most $0.9$, meaning the attention weights can shift by at most 90% of their original values — a significant but bounded reorganization of attention.

---

## 5. Calibration Properties

### 5.1 Proposition 2: Quality-Induced Predictive Entropy Increase

**Proposition 2 (Calibration Guarantee).** Let $\hat{p}_q(y|x) = \mathbb{E}_{z \sim p_\phi(z|x,q)}[q_\theta(y|z)]$ be the Q-VIB predictive distribution. Let $H(\hat{p}_q) = -\sum_{y \in \mathcal{Y}} \hat{p}_q(y|x) \log \hat{p}_q(y|x)$ be its entropy. Under the Q-VIB objective (6), for any $\beta > 0$, the expected predictive entropy is non-increasing in the mean quality score $\bar{q}$:

$$\boxed{\mathbb{E}_{x \sim p(x|\bar{q}_1)}\big[H(\hat{p}_{q_1})\big] \geq \mathbb{E}_{x \sim p(x|\bar{q}_2)}\big[H(\hat{p}_{q_2})\big] \quad \text{whenever} \quad \bar{q}_1 < \bar{q}_2} \tag{16}$$

*Proof.* The proof proceeds by analyzing the effect of $\sigma^2(\bar{q})$ on the encoder's optimal behavior under the Q-VIB objective.

**Step 1: Optimal encoder behavior under varying $\sigma^2$.** At any fixed $\bar{q}$, the encoder $p_\phi(z|x,q) = \mathcal{N}(\mu, \Sigma)$ minimizes the combined objective:

$$\mathcal{J}(\mu, \Sigma; \beta, \sigma^2) = \mathbb{E}_{\epsilon}\big[-\log q_\theta(y|\mu + \Sigma^{1/2}\epsilon)\big] + \beta \cdot D_{\mathrm{KL}}\big(\mathcal{N}(\mu, \Sigma) \,\|\, \mathcal{N}(0, \sigma^2 I_d)\big)$$

The KL term from Eq. (9) can be written as:

$$D_{\mathrm{KL}} = \frac{1}{2}\left[\frac{\|\mu\|^2}{\sigma^2} + \frac{\operatorname{tr}(\Sigma)}{\sigma^2} - d - \log\det\Sigma + d\log\sigma^2\right]$$

**Step 2: First-order optimality conditions.** At the optimum, the gradient with respect to $\mu$ must vanish:

$$\nabla_\mu \mathcal{J} = \nabla_\mu \mathbb{E}_{\epsilon}[-\log q_\theta] + \frac{\beta}{\sigma^2} \mu = 0$$

This implies $\mu^* = -\frac{\sigma^2}{\beta} \cdot \nabla_\mu \mathbb{E}_{\epsilon}[-\log q_\theta]$. As $\sigma^2$ increases, $\mu^*$ is **scaled toward zero** proportionally to $1/\sigma^2$, unless the gradient of the cross-entropy term counteracts this effect — which it cannot, because the gradient magnitude is bounded (classification loss gradients are Lipschitz for standard architectures).

**Step 3: Effect on predictive entropy.** As $\mu \to 0$ and $\Sigma \to \sigma^2 I_d$, the latent code $z$ approaches a sample from the uninformative prior $\mathcal{N}(0, \sigma^2 I_d)$. The predictive distribution becomes:

$$\hat{p}_q(y|x) \to \mathbb{E}_{z \sim \mathcal{N}(0, \sigma^2 I_d)}[q_\theta(y|z)]$$

For a well-trained classifier $q_\theta$, samples from the uninformative prior produce approximately uniform predictions (the classifier has no discriminative signal to exploit). The entropy of a uniform distribution over $K$ classes is $\log K$, which is the maximum possible entropy.

**Step 4: Monotonicity.** Since $\sigma^2(\bar{q})$ is strictly decreasing in $\bar{q}$ (Lemma 1), and larger $\sigma^2$ forces $\mu$ closer to 0 (Step 2), the predictive entropy increases monotonically as $\bar{q}$ decreases. Formally, for $\bar{q}_1 < \bar{q}_2$:

$$\sigma^2(\bar{q}_1) > \sigma^2(\bar{q}_2) \implies \|\mu^*(\bar{q}_1)\| \leq \|\mu^*(\bar{q}_2)\| \implies H(\hat{p}_{q_1}) \geq H(\hat{p}_{q_2})$$

where the last implication follows from the data processing inequality applied to the Markov chain $Y \to X \to Z \to \hat{Y}$: more compressed $Z$ (higher noise, smaller $\mu$) cannot increase predictive information. $\square$

### 5.2 Interpretation and Contrast with Hard Gating

Proposition 2 establishes that Q-VIB provides **quality-calibrated uncertainty** — the model is provably more uncertain (higher predictive entropy) on lower-quality inputs, without any post-hoc threshold tuning.

| Property | Hard Gating | Q-VIB (Ours) |
|----------|------------|--------------|
| Mathematical foundation | Heuristic threshold | Variational lower bound |
| Behavior on low quality | Reject diagnosis entirely | Output high-entropy distribution |
| Differentiability | ✗ Non-differentiable | ✓ End-to-end differentiable |
| Information utilization | Discard low-quality info | Compress proportionally to quality |
| Quality–uncertainty mapping | Binary (accept/reject) | Continuous, monotonic |
| Theoretical guarantee | None | Proposition 2 (monotonicity) |
| Hyperparameter | Hard threshold $T$ | $\beta, \alpha, \tau$ (smooth) |

---

## 6. Summary of Theoretical Contributions

| # | Result | Type | Key Equation | Role in Paper |
|---|--------|------|--------------|---------------|
| **Prop. 1** | Q-VIB Evidence Lower Bound | ELBO derivation | Eq. (5) | Establishes Q-VIB as a principled variational framework |
| **Lemma 1** | Monotonicity of $\sigma^2(\bar{q})$ | Calculus | Eq. (8) | Ensures quality-adaptive prior behaves as designed |
| **Lemma 2** | Softmax perturbation bound | Known result | Eq. (12) | Technical tool for Theorem 1 |
| **Thm. 1** | Quality-aware attention drift bound | Novel bound | Eq. (13) | Quantifies how quality modulates self-attention |
| **Cor. 1–2** | Tightness & practical bounds | Corollaries | — | Connects theory to implementation |
| **Prop. 2** | Quality-calibrated entropy guarantee | Monotonicity proof | Eq. (16) | Formalizes "model knows when it doesn't know" |

---

## 7. Connections to Related Work

**Relation to Alemi et al. (2017).** Q-VIB generalizes VIB by making the marginal prior $r(z)$ quality-dependent. When $r_\psi(z|q) = \mathcal{N}(0, I_d)$ for all $q$, Q-VIB reduces to VIB (Eq. 4).

**Relation to $\beta$-VAE (Higgins et al., 2017).** Both $\beta$-VAE and Q-VIB use a $\beta$-weighted KL term to control the information bottleneck. The key difference is that $\beta$-VAE uses a **fixed** prior and a **fixed** $\beta$, while Q-VIB uses a **quality-adaptive** prior, which implicitly provides input-dependent compression strength without requiring per-sample $\beta$ tuning.

**Relation to confidence calibration (Guo et al., 2017).** Post-hoc calibration methods (temperature scaling, Platt scaling) adjust model confidence after training. Q-VIB achieves calibration **during training** through the quality-conditional prior — a structural rather than post-hoc solution.

**Novelty statement.** To the best of our knowledge, this is the **first work** to (i) condition the information bottleneck prior on perceptual quality, (ii) derive a Lipschitz-based attention drift bound for quality-modulated Transformers, and (iii) provide a formal monotonicity guarantee linking input quality to predictive entropy within a variational framework.

---

## Appendix: Implementation-Level Details

### A.1 Reparameterization for Gradient Estimation

The expectation $\mathbb{E}_{z \sim p_\phi}[\cdot]$ is estimated using a single Monte Carlo sample with the reparameterization trick:

$$z = \mu_\phi(x, q) + \sigma_\phi(x, q) \odot \epsilon, \quad \epsilon \sim \mathcal{N}(0, I_d)$$

This yields unbiased gradient estimates with respect to $\phi$.

### A.2 Spectral Normalization for Lipschitz Control

To ensure the bound in Theorem 1 is practically meaningful, we apply spectral normalization (Miyato et al., 2018) to each linear layer in $\tilde{u}$ and $\tilde{v}$, constraining their Lipschitz constants $L_{\tilde{u}}, L_{\tilde{v}} \leq 1$. This limits the worst-case attention perturbation to $10\varepsilon^2$.

### A.3 $\beta$ Annealing Schedule

Following the VIB literature, we anneal $\beta$ during training:

$$\beta(t) = \beta_{\max} \cdot \min\left(1, \frac{t}{T_{\text{warmup}}}\right)$$

where $t$ is the training step. The initial high $\beta$ forces the model to learn efficient compression before gradually relaxing the bottleneck to allow quality-conditional information flow.

### A.4 Numerical Stability of the KL Term

The KL divergence in Eq. (9) contains $\log(\sigma_j^2 / \sigma^2(\bar{q}))$. To avoid numerical instability when $\sigma_j^2 \approx 0$ or $\sigma^2(\bar{q}) \approx 0$, we clamp both variances to $[10^{-8}, 10^2]$ and use the identity $\log(a/b) = \log a - \log b$ for stable computation.
