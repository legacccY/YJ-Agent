# HPC Companion — 待办

## 下次优先（用户 2026-06-17 提出）

### 1. GPU 利用率曲线参考 Windows 任务管理器
- 平滑比例（曲线插值/抗锯齿，别折线生硬）
- **从左到右平移、曲线跟随的滚动动画**（固定时间窗，新点从右进、旧点左移出窗）
- 填充面积（曲线下半透明填充，任务管理器那种）
- Y 轴已锁 0-100%、禁缩放（已完成，保持）

### 2. 刷新间隔加「1 秒」选项
- `cmb_interval` 加 "1 秒"
- **必须给曲线缓冲加上限**（防 1s 刷新内存堆积）：
  - `_gpu_t/_gpu_sm`、`_hb_x/_hb_y` 改成定长滑窗（如最多 600 点 ≈ 10 分钟@1s），超出丢最旧
  - 配合任务管理器式固定时间窗滚动，正好

## 已知小尾巴
- `_clear_gpu` 方法去掉 GPU 按钮后已无引用，可删
- 偶尔残留一个 ~39MB python 进程（Start-Process 启动副产物？），不影响，待查
- `_scratch/` 下测试脚本（probe/run_test/run_fail/submit_live/submit_gpu/shot）= 临时验证用，可清
- HPC 上 `/gpfs/work/bio/jiayu2403/test/` 留了测试任务产物（submit_*.sh / gpu_demo.py / result.txt / logs），可清

## 已完成（截至 2026-06-17）
- 核心后端：paramiko SSH/SFTP（保活30s）+ SLURM 解析/sbatch 生成 + keyring 密码 + QThread 异步
- 4 面板：连接(profile/自动连接/预设) · 任务监控 · SFTP双栏(断点续传/速度/ETA) · 提交向导(可编辑脚本)
- 任务监控：squeue+sacct 融合(结束任务不消失) · 历史范围(今/3/7/30天) · 错误红横幅(退出码+err尾) · 日志find兜底+缓存 · GPU/心跳异步(切job秒出) · 选中自动跟刷 · 深/浅主题
- 实跑验证：成功(COMPLETED)/报错(FAILED 127)/CPU实时日志/GPU利用率86%+心跳 全通
- PyInstaller build.spec 就绪（未打包）
