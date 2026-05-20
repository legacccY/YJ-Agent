import numpy as np
for name in ['resnet50', 'vit_tiny']:
    d = f'project/results/backbones/{name}'
    for f in ['degraded_val_logits', 'degraded_val_qbar', 'degraded_val_targets']:
        arr = np.load(f'{d}/{f}.npy')
        print(f'{name}/{f}: shape={arr.shape}, range=[{arr.min():.3f}, {arr.max():.3f}]')
    print()
