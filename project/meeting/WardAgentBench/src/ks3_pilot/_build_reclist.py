# 抓 mimic3wdb-matched 一批 numerics record 名(结尾n) -> records.txt。主线临时工具。
import urllib.request, sys
BASE="https://physionet.org/files/mimic3wdb-matched/1.0/"
def get(url):
    req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0"})
    return urllib.request.urlopen(req,timeout=60).read().decode("utf-8","ignore")
# 顶层 RECORDS = 病人目录清单(形如 p00/p000020/)
top=[l.strip() for l in get(BASE+"RECORDS").splitlines() if l.strip()]
print(f"[info] 顶层 {len(top)} 病人目录, 取前 8 个找 numerics record")
recs=[]
for pdir in top[:60]:
    try:
        sub=[l.strip() for l in get(BASE+pdir+"RECORDS").splitlines() if l.strip()]
    except Exception as e:
        print(f"  [skip] {pdir}: {e}"); continue
    # numerics record 结尾 'n'；sub 项形如 p000020-2183-04-28-17-47n
    nums=[s for s in sub if s.endswith("n")]
    for n in nums[:3]:
        recs.append(pdir+n)  # 全相对路径
    print(f"  {pdir}: {len(sub)} records, {len(nums)} numerics")
    if len(recs)>=45: break
open("records.txt","w",encoding="utf-8").write("\n".join(recs[:45]))
print(f"[written] records.txt ({len(recs[:45])} numerics records)")
print("\n".join(recs[:5]))
