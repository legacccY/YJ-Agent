import pandas as pd, numpy as np, os, warnings
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt, matplotlib.patches as mpatches, matplotlib.colors as mcolors
from sklearn.metrics import roc_auc_score, average_precision_score, roc_curve
from scipy import stats
warnings.filterwarnings("ignore")

DATA_PATH = "D:/YJ-Agent/project/meeting/QuantImmuBench/scripts/out/merged_all_tools_5tools.xlsx"
FIG_DIR   = "D:/YJ-Agent/project/meeting/QuantImmuBench/analysis/figures"
ANLYS_DIR = "D:/YJ-Agent/project/meeting/QuantImmuBench/analysis"
os.makedirs(FIG_DIR, exist_ok=True)

TOOLS  = {"DeepImmuno":"MT_DeepImmuno","PredIG":"MT_PredIG","IMPROVE":"MT_IMPROVE_mean_prediction_rf","NeoTImmuML":"MT_NeoTImmuML","pTuneos":"MT_pTuneos"}
COLORS = {"DeepImmuno":"#E6693E","PredIG":"#4C9BE8","IMPROVE":"#3DA851","NeoTImmuML":"#9B59B6","pTuneos":"#D55E00"}

df = pd.read_excel(DATA_PATH)
ds2 = df[df["Dataset"]=="DS2"].copy()
ds1 = df[df["Dataset"]=="DS1"].copy()
ds2_pep = ds2.drop_duplicates("Peptide_ID")[["Peptide_ID","Elispot"]].set_index("Peptide_ID")
ds1_pep = ds1.drop_duplicates("Peptide_ID")[["Peptide_ID","Elispot"]].set_index("Peptide_ID")

def agg_pep(sub, col):
    valid = sub[sub[col].notna()].copy()
    if valid.empty: return {}
    out = {}
    for pid, grp in valid.groupby("Peptide_ID")[col]:
        arr = grp.values; k = min(3, len(arr))
        out[pid] = {"max":float(arr.max()),"mean":float(arr.mean()),"top3mean":float(np.sort(arr)[-k:].mean())}
    return out

pep_scores = {t: agg_pep(ds2, c) for t, c in TOOLS.items()}
elispot_vals = ds2_pep["Elispot"]
THRESHOLDS = {">0":0, ">10":10, ">median":float(elispot_vals.median())}

rows = []
for tname in TOOLS:
    pd_ = pep_scores[tname]
    if not pd_: continue
    pids = list(pd_.keys())
    for method in ("max","mean","top3mean"):
        sc = np.array([pd_[p][method] for p in pids])
        el = elispot_vals.loc[pids].values
        rho, pval = stats.spearmanr(sc, el)
        for thr_name, thr_val in THRESHOLDS.items():
            labs = (el > thr_val).astype(int)
            npos = int(labs.sum()); nneg = int((1-labs).sum())
            if npos==0 or nneg==0: auc_roc=np.nan; auprc=np.nan
            else: auc_roc=round(roc_auc_score(labs,sc),4); auprc=round(average_precision_score(labs,sc),4)
            rows.append({"Tool":tname,"Aggregation":method,"Threshold":thr_name,
                         "n_pep":len(pids),"n_pos":npos,"n_neg":nneg,
                         "AUC_ROC":auc_roc,"AUPRC":auprc,"Spearman_rho":round(rho,4),"Spearman_pval":round(pval,4)})
metrics_df = pd.DataFrame(rows)
metrics_df.to_csv(os.path.join(ANLYS_DIR, "metrics_ds2.csv"), index=False)
print(metrics_df[(metrics_df["Aggregation"]=="max")&(metrics_df["Threshold"]==">0")][["Tool","AUC_ROC","AUPRC","Spearman_rho"]].to_string(index=False))

fig,ax=plt.subplots(figsize=(7,6))
ax.plot([0,1],[0,1],"--",color="gray",lw=1,label="Random (AUC=0.50)")
for tname,tcol in TOOLS.items():
    pd_=pep_scores[tname]
    if not pd_: continue
    pids=list(pd_.keys()); sc=np.array([pd_[p]["max"] for p in pids])
    el=ds2_pep.loc[pids]["Elispot"].values; labs=(el>0).astype(int)
    if labs.sum()==0 or (1-labs).sum()==0: continue
    auc=roc_auc_score(labs,sc); fpr,tpr,_=roc_curve(labs,sc)
    ax.plot(fpr,tpr,color=COLORS[tname],lw=2.2,label=tname+" (AUC="+f"{auc:.3f}"+ ")")
ax.set_xlabel("False Positive Rate",fontsize=12); ax.set_ylabel("True Positive Rate",fontsize=12)
ax.set_title("ROC Curves DS2 ELISpot>0 agg=max",fontsize=11); ax.legend(fontsize=10)
ax.set_xlim([0,1]); ax.set_ylim([0,1.01])
plt.tight_layout(); fig.savefig(os.path.join(FIG_DIR,"fig1_roc_curves_ds2.png"),dpi=200); plt.close()
print("Done - figures saved to", FIG_DIR)
