"""
R5 ckpt 敏感性诊断：检查本地有无 F/D 多 epoch ckpt
若只有单一 best_qad.pth → 标 TODO，不跑训练
输出: r5_ckpt_sensitivity.json
"""
import os
import json
import glob

OUT_DIR = os.path.dirname(__file__)

# Project root = two levels up from results/qvib_minverify/
PROJECT_DIR = os.path.join(os.path.dirname(__file__), '../..')
_c1 = os.path.normpath(os.path.join(PROJECT_DIR, 'checkpoints'))
_c2 = os.path.normpath(os.path.join(PROJECT_DIR, '..', 'checkpoints'))
# Prefer dir that contains qad ckpts (efnet/, stdvib/ subdirs or best_qad.pth)
import glob as _glob
_has_qad1 = bool(_glob.glob(os.path.join(_c1, '*', 'best_qad.pth')))
_has_qad2 = bool(_glob.glob(os.path.join(_c2, '*', 'best_qad.pth'))) or os.path.exists(os.path.join(_c2, 'best_qad.pth'))
CKPT_DIR = _c1 if _has_qad1 else (_c2 if _has_qad2 else _c1)
CKPT_DIR2 = CKPT_DIR


def find_ckpts(ckpt_dir):
    """Find all .pth files under checkpoints/, grouped by method."""
    if not os.path.exists(ckpt_dir):
        return {}
    results = {}
    for root, dirs, files in os.walk(ckpt_dir):
        for f in files:
            if f.endswith('.pth'):
                rel = os.path.relpath(os.path.join(root, f), ckpt_dir)
                size_mb = os.path.getsize(os.path.join(root, f)) / 1e6
                # Determine method from path
                for code, patterns in [('F', ['efnet', 'qvib', 'q_vib', 'qad']),
                                        ('D', ['stdvib', 'std_vib', 'vib']),
                                        ('G', ['tokft', 'tok_ft'])]:
                    if any(p in rel.lower() for p in patterns):
                        results.setdefault(code, []).append({'path': rel, 'size_mb': round(size_mb, 1)})
                        break
    return results


def main():
    # Try both possible ckpt paths
    ckpt_dir = CKPT_DIR2 if os.path.exists(CKPT_DIR2) else CKPT_DIR
    print(f"Searching checkpoints in: {ckpt_dir}")

    found = find_ckpts(ckpt_dir)
    if not found:
        # Try listing top-level
        if os.path.exists(ckpt_dir):
            contents = os.listdir(ckpt_dir)
            print(f"checkpoints/ contents: {contents}")
        else:
            print(f"checkpoints/ not found at {ckpt_dir}")

    print(f"\nFound ckpts by method: {json.dumps({k: [x['path'] for x in v] for k, v in found.items()}, indent=2)}")

    # Check for F and D specifically
    f_ckpts = found.get('F', [])
    d_ckpts = found.get('D', [])

    # Also scan for any epoch-indexed ckpts (ep\d+ or epoch\d+ in name)
    epoch_ckpts_F = [x for x in f_ckpts if any(pat in x['path'].lower() for pat in ['ep', 'epoch', 'e0', 'e1', 'e2', 'e3'])]
    epoch_ckpts_D = [x for x in d_ckpts if any(pat in x['path'].lower() for pat in ['ep', 'epoch', 'e0', 'e1', 'e2', 'e3'])]

    has_multi_F = len(f_ckpts) > 1
    has_multi_D = len(d_ckpts) > 1

    if not has_multi_F and not has_multi_D:
        verdict = 'TODO: Only single best_qad.pth found for F and D. Multi-epoch sensitivity analysis requires re-training (zero GPU here). Skipping R5.'
        can_run = False
    elif has_multi_F or has_multi_D:
        verdict = 'PARTIAL: Multiple ckpts found, offline AUC comparison possible with eval script.'
        can_run = True
    else:
        verdict = 'TODO: Insufficient ckpts for multi-epoch comparison.'
        can_run = False

    summary = {
        'ckpt_dir': str(ckpt_dir),
        'F_ckpts_found': f_ckpts,
        'D_ckpts_found': d_ckpts,
        'F_has_multi_epoch': has_multi_F,
        'D_has_multi_epoch': has_multi_D,
        'epoch_ckpts_F': epoch_ckpts_F,
        'epoch_ckpts_D': epoch_ckpts_D,
        'can_run_offline': can_run,
        'verdict': verdict,
    }
    print(f"\nVERDICT: {verdict}")

    with open(os.path.join(OUT_DIR, 'r5_ckpt_sensitivity.json'), 'w') as f:
        json.dump(summary, f, indent=2)

    print(f"\nOutput: r5_ckpt_sensitivity.json")
    return summary


if __name__ == '__main__':
    main()
