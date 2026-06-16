import csv
f="results/backbones/section54_summary.csv"
rows=list(csv.DictReader(open(f)))
cols=["backbone","raw_rho","ts_rho","qcts_rho","raw_qcdi","ts_qcdi","qcts_qcdi",
      "raw_ITB-LQ_ece","ts_ITB-LQ_ece","qcts_ITB-LQ_ece"]
print("backbone | raw_rho | ts_rho | qcts_rho | raw_qcdi | ts_qcdi | qcts_qcdi | rawLQ_ece | tsLQ_ece | qctsLQ_ece")
for r in rows:
    def g(k):
        v=r.get(k,"")
        return f"{float(v):+.3f}" if v not in ("",None) else "NA"
    print(" | ".join([r["backbone"]]+[g(c) for c in cols[1:]]))
