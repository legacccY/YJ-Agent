cd /gpfs/work/bio/jiayu2403/quantimmu/sif
gunzip -kf ptuneos.tar.gz
singularity build ptuneos.sif docker-archive://ptuneos.tar
echo PTUNEOS_SIF_DONE; ls -lh ptuneos.sif