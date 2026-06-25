import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt, numpy as np, pandas as pd
from pathlib import Path
ROOT=Path("D:/YJ-Agent/project/meeting/QuantImmuBench")
xls=ROOT/"scripts/out/merged_all_tools_5tools.xlsx"
df=pd.read_excel(xls)
df=df[df["Dataset"]=="DS2"].copy()  # 与8工具corr一致,仅DS2
TOOLS=["DeepImmuno","PredIG","pTuneos","IMPROVE","NeoTImmuML"]
COL={"DeepImmuno":"MT_DeepImmuno","PredIG":"MT_PredIG","pTuneos":"MT_pTuneos",
     "IMPROVE":"MT_IMPROVE_mean_prediction_rf","NeoTImmuML":"MT_NeoTImmuML"}
pepcol="Peptide_ID"
# 逐肽 max 聚合
agg=df.groupby(pepcol).agg({COL[t]:"max" for t in TOOLS if COL[t] in df.columns}).reset_index()
present=[t for t in TOOLS if COL[t] in agg.columns]
M=np.ones((len(present),len(present)))
for i,a in enumerate(present):
    for j,b in enumerate(present):
        if i==j: M[i,j]=1.0; continue
        s=agg[[COL[a],COL[b]]].dropna()
        M[i,j]=s.iloc[:,0].corr(s.iloc[:,1],method="spearman") if len(s)>2 else np.nan
fig,ax=plt.subplots(figsize=(6.4,5.6))
im=ax.imshow(M,cmap="RdBu_r",vmin=-1,vmax=1)
ax.set_xticks(range(len(present)));ax.set_xticklabels(present,rotation=40,ha="right")
ax.set_yticks(range(len(present)));ax.set_yticklabels(present)
for i in range(len(present)):
    for j in range(len(present)):
        v=M[i,j]; ax.text(j,i,f"{v:.2f}",ha="center",va="center",
            color="white" if abs(v)>0.6 else "black",fontsize=11)
ax.set_title("DS2 5-tool peptide-level score correlation (n="+str(len(agg))+")",fontsize=11)
cb=fig.colorbar(im,ax=ax,shrink=0.85);cb.set_label("Spearman rho")
fig.tight_layout()
out=ROOT/"analysis/figures/fig_corr_heatmap_5tools.png"
fig.savefig(out,dpi=150);print("WROTE",out)
print("present tools:",present,"| n_pep:",len(agg))
