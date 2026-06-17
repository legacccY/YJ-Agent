import sys, numpy as np, torch, torch.nn.functional as F
from pathlib import Path
from omegaconf import OmegaConf
from torch.utils.data import DataLoader
from sklearn.metrics import roc_auc_score
sys.path.insert(0,'.')
from data.qad_dataset import QADDataset, qad_collate_fn
from models.q_vib_encoder import QVIBEncoder
from models.qad_classifier import QADClassifier
from models.quality_adaptive_prior import QualityAdaptivePrior
torch.manual_seed(0); np.random.seed(0)
dev='cuda' if torch.cuda.is_available() else 'cpu'
cfg=OmegaConf.load('configs/qad_efnet.yaml')
ds=QADDataset(quality_csv=cfg.data.labels_csv,metadata_csv=cfg.data.metadata_csv,abcd_cache_csv=cfg.data.abcd_cache_csv,
  efnet_features_npy=cfg.data.get('efnet_features_npy',None),efnet_index_csv=cfg.data.get('efnet_index_csv',None),
  split_csv=cfg.data.get('split_csv',None),split='test')
ld=DataLoader(ds,batch_size=512,shuffle=False,num_workers=0,collate_fn=qad_collate_fn)
enc=QVIBEncoder(abcd_dim=4,q_dim=5,d_model=cfg.model.encoder.d_model,n_heads=cfg.model.encoder.n_heads,
  latent_dim=cfg.model.encoder.latent_dim,efnet_dim=cfg.model.encoder.get('efnet_dim',0),
  use_tokenizer=cfg.model.encoder.get('use_tokenizer',True)).to(dev)
clf=QADClassifier(latent_dim=cfg.model.encoder.latent_dim,hidden_dim=cfg.model.classifier.hidden_dim,
  num_classes=cfg.model.classifier.num_classes).to(dev)
cands=['efnet/best_qad','efnet_tokft/best_qad','efnet_s42/best_qad','efnet_s123/best_qad','efnet_s2024/best_qad','best_qad']
for name in cands:
  p=Path(f'../checkpoints/{name}.pth')
  if not p.exists(): print(name,'MISSING'); continue
  try:
    ck=torch.load(p,map_location=dev); enc.load_state_dict(ck['encoder']); clf.load_state_dict(ck['classifier'])
    enc.eval(); clf.eval()
  except Exception as e: print(name,'LOAD-ERR',str(e)[:60]); continue
  probs,tg=[],[]
  with torch.no_grad():
    for b in ld:
      mu,ls=enc(b['abcd'].to(dev),b['q'].to(dev),efnet_feat=b['efnet_feat'].to(dev) if 'efnet_feat' in b else None)
      pl=[F.softmax(clf(enc.reparameterize(mu,ls)),-1) for _ in range(20)]
      probs.append(torch.stack(pl).mean(0).cpu().numpy()); tg.append(b['target'].numpy())
  probs=np.concatenate(probs); tg=np.concatenate(tg)
  print(f'{name}: AUC={roc_auc_score(tg,probs[:,1]):.4f}  n={len(tg)}')
