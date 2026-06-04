import paramiko, warnings
warnings.filterwarnings('ignore')
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect('dtn.hpc.xjtlu.edu.cn', username='jiayu2403', password='pxXd3VGhbB', timeout=15)
def run(cmd, t=60):
    _, o, e = c.exec_command(cmd, timeout=t)
    return (o.read().decode('utf-8','replace') + e.read().decode('utf-8','replace')).strip()
M = '/gpfs/work/bio/jiayu2403/mednca'
print("=== dbg_1435324.out (GT/pred voxels) ==="); print(run(f'cat {M}/logs/dbg_1435324.out'))
print("=== dbg_1435324.err ==="); print(run(f'cat {M}/logs/dbg_1435324.err'))
print("=== tl_1435325.out (ckpt timeline, grep dice) ==="); print(run(f'grep -i "ckpt\|dice\|done\|Error\|Traceback" {M}/logs/tl_1435325.out | head -40'))
c.close()
