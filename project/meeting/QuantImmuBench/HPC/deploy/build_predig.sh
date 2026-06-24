cd /gpfs/work/bio/jiayu2403/quantimmu/sif
gunzip -kf predig.tar.gz
singularity build predig.sif docker-archive://predig.tar
echo PREDIG_SIF_DONE; ls -lh predig.sif