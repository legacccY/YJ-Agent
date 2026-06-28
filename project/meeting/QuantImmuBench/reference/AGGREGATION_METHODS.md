# per-patient Spearman 聚合方法学

> 服务 quantimmu-bench。建档 2026-06-26。来源:researcher 联网查统计文献(meta-analysis of correlations)。
> 场景:9 个患者,每患者内单独算 Spearman ρ_i(工具预测分 vs ELISpot SFC),每人肽数 n_i=6-16,把 9 个 ρ_i 聚合成头条值。
> 用户要求:多种方法都报 + 「乘方再开根」类(幂平均/几何)。实现见 `analysis/per_patient_spearman_multimethod.py`。

---

## 核心场景约束(决定哪些方法可信)

- **K=9 患者**(小):I²/τ² 估计极不稳(K<10 误差可达 ±28pp,BMC Med Res Methodol 2015)→ **不用随机效应**,用固定效应。
- **n_i=6-16**(极小):每个 ρ_i 自身 95% CI 宽达 ±0.6-0.7 → 任何聚合值的 CI 都很宽,须如实报。
- 患者 108/109 全阳(0 阴性)对 Spearman 无碍(连续 SFC 仍有变异),全 9 人参与。

---

## 主报方法(2 种,统计正解,互证)

### 1. Fisher-z 固定效应加权平均 ⭐ 统计正解
$$z_i=\operatorname{arctanh}(\rho_i)=\tfrac12\ln\tfrac{1+\rho_i}{1-\rho_i}$$
Spearman 专用方差(Fieller-Hartley-Pearson 1957):$\operatorname{Var}(z_i)\approx\dfrac{1+\rho_i^2/2}{n_i-3}$,权重 $w_i=1/\operatorname{Var}(z_i)$
$$\bar z=\frac{\sum w_i z_i}{\sum w_i},\qquad \bar\rho=\tanh(\bar z)$$
95% CI:$\tanh(\bar z\pm 1.96/\sqrt{\sum w_i})$。方差稳定化、大样本近正态、meta 标准做法。

### 2. 中位数 $\tilde\rho=\operatorname{median}(\rho_i)$ ⭐ 稳健替代
对 outlier 患者完全免疫;K=9 奇数 → 取第 5 大值,无插值歧义。Devlin 1975 minimax 最优。

---

## 次报方法(描述性探索,明确标「探索性」)

### 3. 简单未加权均值 $\bar\rho=\frac1K\sum\rho_i$
可解释性最强;但 ρ≠0 时抽样分布偏斜 → 系统低估(n_i 小时偏差不可忽略)。本场景 n_i 跨度小,与 HS 接近。

### 4. Hunter-Schmidt 样本量加权 $\bar\rho_{HS}=\dfrac{\sum n_i\rho_i}{\sum n_i}$
psychometrics 传统;本场景 n_i 仅 6-16(两倍内)→ 与简单均值差异小。

### 5. 几何均值(用户要求,via 变换) —— 「木桶效应」
ρ∈[-1,1] 不能直接几何均值,先变换 $v_i=\tfrac{1+\rho_i}2\in[0,1]$:
$$\bar\rho_{GM}=2\Big(\prod v_i\Big)^{1/K}-1=2\exp\!\Big(\tfrac1K\sum\ln\tfrac{1+\rho_i}2\Big)-1$$
任一患者 ρ→-1 拖底。**TODO:无文献专门背书此变换用于 Spearman 聚合 → 仅描述性。**

### 6. 幂平均 $M_p$(用户的「乘方再开根」,via 变换) —— $p=2$ 即 RMS
$$\bar\rho_{M_p}=2\Big(\tfrac1K\sum v_i^{\,p}\Big)^{1/p}-1,\quad v_i=\tfrac{1+\rho_i}2$$
$p\to0$=几何;$p=1$=算术;$p=-1$=调和(惩罚低相关);$p=2$=均方根(奖励高相关,最符合用户「乘方开根」);$p\to\infty$=max。
$$\bar\rho_{RMS}=2\sqrt{\tfrac1K\sum\big(\tfrac{1+\rho_i}2\big)^2}-1$$
纯数学聚合算子,无统计模型假设。$p>1$ 锦上添花视角、$p<1$ 木桶视角。**TODO:无文献背书用于 ρ 聚合 → 仅描述性,不可构造 CI。**

### 7. UWLS+3(可选,2025 最新偏差校正)
Stanley-Doucouliagos 2025:自由度调成 $n_i+1$ 再逆方差加权 LS,K<10 偏差降至 <0.01。可作 Fisher-z 的现代替代补充。

---

## 实现要求(per_patient_spearman_multimethod.py)

对**每个工具**输出一行,含:
- 9 个 per-patient ρ_i(原始,score 方向已统一为「越高越免疫原」)+ 各 n_i
- 全局 ρ(对照,看个体差异掩盖多少)
- 上述 7 种聚合值(Fisher-z 加权+CI、median、simple mean、HS、GM、M₂-RMS、UWLS+3)
- 跨患者分布:min/max/std(ρ_i)
- 列名清晰,落 `analysis/per_patient_spearman_<NN>tools.csv`

## 报告/审稿警告(必写进产物)
1. n_i=6-16 → 单 ρ_i CI ±0.6-0.7,聚合 CI 很宽,不可过度解读。
2. K=9 → 不用随机效应(τ² 不稳)。
3. 几何/幂平均作用于 ρ 须先 (1+ρ)/2 变换,且是描述性非推断,不构造 CI。
4. 主结论以 Fisher-z 加权 + median 为准,其余作敏感性/探索对照。

## 关键引用
Fieller-Hartley-Pearson 1957 Biometrika 44:470(Spearman z 方差);Fisher transformation(Wikipedia);Hedges-Olkin 1985 / Hunter-Schmidt 1990;Devlin 1975(median robust);Generalized mean(Wikipedia);Stanley-Doucouliagos 2025 UWLS+3(PMC12631149);BMC Med Res Methodol 2015(I² small-K bias)。
