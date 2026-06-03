import torch, os
print('cuda', torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else '')
r = r'D:\YJ-Agent\project\meeting\Med-NCA\data\Task04_Hippocampus'
for s in ['imagesTr', 'labelsTr']:
    p = os.path.join(r, s)
    n = len([f for f in os.listdir(p) if f.endswith('.nii.gz') and not f.startswith('._')]) if os.path.isdir(p) else 'MISSING'
    print(s, n)
