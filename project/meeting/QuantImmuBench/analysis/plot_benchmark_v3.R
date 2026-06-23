# plot_benchmark_v3.R
# 服务: quantimmu-bench — 克制专业版 (v3)
# 风格: theme_classic, Okabe-Ito 色盲安全调色板, 去掉炫技元素
# 功能: 5 张图，全用常规画法
#   fig1_roc_v3      — ROC 折线
#   fig2_bar_v3      — 阈值对比分组柱状图
#   fig3_scatter_v3  — score vs Elispot 散点 facet + lm
#   fig4_bar_v3      — 聚合对比分组柱状图
#   fig5_heatmap_v3  — AUC 热图 (geom_tile, 单色 Blues)
# 输出: analysis/figures_R_v3/ (.png dpi=300 + .pdf)
# 运行: E:\R-4.3.3\bin\Rscript.exe plot_benchmark_v3.R
#       (从 analysis/ 目录运行，或双击后自动定位)

# ── 0. 定位工作目录 ──────────────────────────────────────────────────────────────
script_path <- tryCatch({
  args <- commandArgs(trailingOnly = FALSE)
  ff   <- grep("--file=", args, value = TRUE)
  if (length(ff) > 0) normalizePath(sub("--file=", "", ff[1])) else NA_character_
}, error = function(e) NA_character_)

ANLYS_DIR <- if (!is.na(script_path) && nchar(script_path) > 0) {
  dirname(script_path)
} else {
  "D:/YJ-Agent/project/meeting/QuantImmuBench/analysis"
}
setwd(ANLYS_DIR)
cat("Working dir:", getwd(), "\n")

# ── 1. 安装 / 加载包 ─────────────────────────────────────────────────────────────
# v3 不依赖 ggsci（颜色手写 Okabe-Ito hex）
pkgs <- c("ggplot2", "dplyr", "tidyr", "readr", "scales")
for (p in pkgs) {
  if (!requireNamespace(p, quietly = TRUE)) {
    install.packages(p, repos = "https://cloud.r-project.org", quiet = TRUE)
  }
  library(p, character.only = TRUE)
}

# ── 2. Okabe-Ito 色盲安全调色板（5 工具）───────────────────────────────────────
# 原始 Okabe-Ito 8 色；取其中柔和可区分的 5 色
OI_COLORS <- c(
  "DeepImmuno" = "#56B4E9",  # sky blue
  "PredIG"     = "#E69F00",  # orange
  "IMPROVE"    = "#009E73",  # green
  "NeoTImmuML" = "#CC79A7",  # mauve/purple
  "pTuneos"    = "#D55E00"   # vermillion (Okabe-Ito 第5安全色)
)

# 工具顺序
TOOL_ORDER <- c("DeepImmuno", "PredIG", "IMPROVE", "NeoTImmuML", "pTuneos")

# ── 3. 读数据 ────────────────────────────────────────────────────────────────────
df_metrics <- read_csv("metrics_ds2.csv", show_col_types = FALSE) |>
  mutate(Tool = factor(Tool, levels = TOOL_ORDER))

df_roc <- read_csv("plotdata_roc.csv", show_col_types = FALSE) |>
  mutate(Tool = factor(Tool, levels = TOOL_ORDER))

df_pep <- read_csv("plotdata_perpep.csv", show_col_types = FALSE) |>
  mutate(Tool = factor(Tool, levels = TOOL_ORDER))

# ── 4. 输出目录 ──────────────────────────────────────────────────────────────────
OUT_DIR <- "figures_R_v3"
dir.create(OUT_DIR, showWarnings = FALSE, recursive = TRUE)

# 统一保存函数：同时输出 png + pdf
save_fig <- function(p, name, width = 7, height = 5) {
  png_path <- file.path(OUT_DIR, paste0(name, ".png"))
  pdf_path <- file.path(OUT_DIR, paste0(name, ".pdf"))
  ggsave(png_path, plot = p, width = width, height = height, dpi = 300, bg = "white")
  ggsave(pdf_path, plot = p, width = width, height = height)
  cat("Saved:", png_path, "\n")
  cat("Saved:", pdf_path, "\n")
}

# ── 5. fig1_roc_v3: ROC 折线 ────────────────────────────────────────────────────
# 每工具取 max 聚合 + >0 阈值（最常报的标准 ROC）
# auc 标签来自 df_roc 中每行的 auc 列（常数，取唯一值即可）
df_roc_plot <- df_roc |>
  filter(Aggregation == "mean", Threshold == ">0")

auc_labels <- df_roc_plot |>
  group_by(Tool) |>
  summarise(auc = unique(auc), .groups = "drop") |>
  mutate(label = paste0(Tool, " (AUC=", sprintf("%.3f", auc), ")"))

# 构建图例 label 映射
legend_labels <- setNames(auc_labels$label, as.character(auc_labels$Tool))

fig1 <- ggplot(df_roc_plot, aes(x = fpr, y = tpr, color = Tool)) +
  geom_line(linewidth = 0.8) +
  geom_abline(slope = 1, intercept = 0, linetype = "dashed",
              color = "grey60", linewidth = 0.5) +
  scale_color_manual(values = OI_COLORS, labels = legend_labels) +
  scale_x_continuous(limits = c(0, 1), expand = c(0.01, 0)) +
  scale_y_continuous(limits = c(0, 1), expand = c(0.01, 0)) +
  labs(
    title = "ROC Curves (mean aggregation, threshold >0)",
    x     = "False Positive Rate",
    y     = "True Positive Rate",
    color = NULL
  ) +
  theme_classic(base_size = 12) +
  theme(
    legend.position   = c(0.72, 0.22),
    legend.background = element_rect(fill = "white", color = NA),
    legend.key.size   = unit(0.5, "cm"),
    legend.text       = element_text(size = 9),
    plot.title        = element_text(size = 11, face = "plain")
  )

save_fig(fig1, "fig1_roc_v3", width = 6, height = 5)

# ── 6. fig2_bar_v3: 阈值对比分组柱状图 ─────────────────────────────────────────
# x=工具, fill=Threshold, dodge, y=AUC_ROC
# 取 mean 聚合（单一聚合减少混乱）
df_thr <- df_metrics |>
  filter(Aggregation == "mean") |>
  mutate(Threshold = factor(Threshold, levels = c(">0", ">10", ">median")))

# 柱顶标注
df_thr_lab <- df_thr |>
  mutate(label = sprintf("%.2f", AUC_ROC))

# Threshold 对应的柔和灰阶色
THR_COLORS <- c(">0" = "#4E79A7", ">10" = "#86BCB6", ">median" = "#BAB0AC")

fig2 <- ggplot(df_thr, aes(x = Tool, y = AUC_ROC, fill = Threshold)) +
  geom_col(position = position_dodge(width = 0.7), width = 0.62) +
  geom_text(data = df_thr_lab,
            aes(label = label, y = AUC_ROC + 0.012),
            position = position_dodge(width = 0.7),
            size = 2.8, color = "grey25", vjust = 0) +
  geom_hline(yintercept = 0.5, linetype = "dashed", color = "grey50", linewidth = 0.5) +
  scale_fill_manual(values = THR_COLORS) +
  scale_y_continuous(limits = c(0, 1.0), expand = c(0, 0),
                     breaks = seq(0, 1, 0.2)) +
  labs(
    title = "AUC-ROC by Tool and Threshold (mean aggregation)",
    x     = "Tool",
    y     = "AUC-ROC",
    fill  = "Threshold"
  ) +
  theme_classic(base_size = 12) +
  theme(
    legend.position = "right",
    panel.grid.major.y = element_line(color = "grey92", linewidth = 0.4),
    plot.title = element_text(size = 11, face = "plain")
  )

save_fig(fig2, "fig2_bar_v3", width = 7, height = 5)

# ── 7. fig3_scatter_v3: score vs Elispot 散点 facet ────────────────────────────
# 取 mean 聚合；点低饱和+透明；lm 趋势线细灰带；角标 rho/p
df_scatter <- df_pep |>
  filter(Aggregation == "mean")

# Spearman rho/p 每工具唯一（来自 metrics，取 mean 聚合任一阈值均一样）
df_anno <- df_metrics |>
  filter(Aggregation == "mean", Threshold == ">0") |>
  select(Tool, Spearman_rho, Spearman_pval) |>
  mutate(
    sig_star = case_when(
      Spearman_pval < 0.001 ~ "***",
      Spearman_pval < 0.01  ~ "**",
      Spearman_pval < 0.05  ~ "*",
      TRUE                  ~ "ns"
    ),
    label = paste0("rho=", sprintf("%.3f", Spearman_rho),
                   "\np=",  sprintf("%.3f", Spearman_pval),
                   " (", sig_star, ")")
  )

# 确定每 facet 角标位置（x=max, y=min 区域）
df_pos <- df_scatter |>
  group_by(Tool) |>
  summarise(
    x_pos = quantile(score, 0.05, na.rm = TRUE),
    y_pos = max(Elispot, na.rm = TRUE) * 0.85,
    .groups = "drop"
  ) |>
  left_join(df_anno, by = "Tool")

fig3 <- ggplot(df_scatter, aes(x = score, y = Elispot)) +
  geom_point(aes(color = Tool), alpha = 0.55, size = 1.4, stroke = 0) +
  geom_smooth(method = "lm", formula = y ~ x,
              color = "grey40", fill = "grey80", linewidth = 0.6, alpha = 0.3) +
  geom_text(data = df_pos,
            aes(x = x_pos, y = y_pos, label = label),
            hjust = 0, vjust = 1, size = 3, color = "grey20", lineheight = 1.2) +
  facet_wrap(~Tool, scales = "free_x", nrow = 2) +
  scale_color_manual(values = OI_COLORS, guide = "none") +
  labs(
    title = "Prediction Score vs. ELISpot Readout (mean aggregation)",
    x     = "Predicted Score",
    y     = "ELISpot (SFU)"
  ) +
  theme_classic(base_size = 12) +
  theme(
    strip.background = element_blank(),
    strip.text       = element_text(size = 11, face = "bold"),
    panel.grid.major = element_line(color = "grey93", linewidth = 0.35),
    plot.title       = element_text(size = 11, face = "plain")
  )

save_fig(fig3, "fig3_scatter_v3", width = 8, height = 6)

# ── 8. fig4_bar_v3: 聚合对比分组柱状图 ─────────────────────────────────────────
# x=工具, fill=Aggregation (max/mean/top3mean), y=AUC_ROC
# 取 threshold >0（最宽松，样本量最大）
df_agg <- df_metrics |>
  filter(Threshold == ">0") |>
  mutate(Aggregation = factor(Aggregation, levels = c("max", "mean", "top3mean")))

AGG_COLORS <- c("max" = "#4E79A7", "mean" = "#86BCB6", "top3mean" = "#BAB0AC")

df_agg_lab <- df_agg |>
  mutate(label = sprintf("%.3f", AUC_ROC))

fig4 <- ggplot(df_agg, aes(x = Tool, y = AUC_ROC, fill = Aggregation)) +
  geom_col(position = position_dodge(width = 0.7), width = 0.62) +
  geom_text(data = df_agg_lab,
            aes(label = label, y = AUC_ROC + 0.012),
            position = position_dodge(width = 0.7),
            size = 2.7, color = "grey25", vjust = 0) +
  geom_hline(yintercept = 0.5, linetype = "dashed", color = "grey50", linewidth = 0.5) +
  scale_fill_manual(values = AGG_COLORS,
                    labels = c("max" = "Max", "mean" = "Mean", "top3mean" = "Top-3 Mean")) +
  scale_y_continuous(limits = c(0, 1.0), expand = c(0, 0),
                     breaks = seq(0, 1, 0.2)) +
  labs(
    title = "AUC-ROC by Tool and Aggregation Strategy (threshold >0)",
    x     = "Tool",
    y     = "AUC-ROC",
    fill  = "Aggregation"
  ) +
  theme_classic(base_size = 12) +
  theme(
    legend.position    = "right",
    panel.grid.major.y = element_line(color = "grey92", linewidth = 0.4),
    plot.title         = element_text(size = 11, face = "plain")
  )

save_fig(fig4, "fig4_bar_v3", width = 7, height = 5)

# ── 9. fig5_heatmap_v3: 工具×阈值 AUC 热图 ─────────────────────────────────────
# 取 mean 聚合；fill = AUC_ROC；单色系 Blues；格内标数值
df_heat <- df_metrics |>
  filter(Aggregation == "mean") |>
  mutate(
    Threshold = factor(Threshold, levels = c(">0", ">10", ">median")),
    Tool      = factor(Tool, levels = rev(TOOL_ORDER))   # 热图 y 轴从上到下
  )

# 文字颜色自适应（浅色背景用黑、深色背景用白）
# 分界: AUC > 0.65 时格子较深，用白字；否则黑字
df_heat <- df_heat |>
  mutate(text_color = ifelse(AUC_ROC > 0.65, "white", "grey15"))

fig5 <- ggplot(df_heat, aes(x = Threshold, y = Tool, fill = AUC_ROC)) +
  geom_tile(color = "white", linewidth = 0.8) +
  geom_text(aes(label = sprintf("%.3f", AUC_ROC), color = text_color),
            size = 3.8, fontface = "plain") +
  scale_fill_distiller(palette = "Blues", direction = 1,
                       limits = c(0.40, 0.80),  # TODO: 若 pTuneos AUC 超出 [0.40,0.80] 需调 limits
                       name   = "AUC-ROC") +
  scale_color_identity() +
  scale_x_discrete(expand = c(0, 0)) +
  scale_y_discrete(expand = c(0, 0)) +
  labs(
    title = "AUC-ROC Heatmap: Tool x Threshold (mean aggregation)",
    x     = "Threshold",
    y     = "Tool"
  ) +
  theme_classic(base_size = 12) +
  theme(
    axis.line        = element_blank(),
    axis.ticks       = element_blank(),
    panel.border     = element_rect(color = "grey70", fill = NA, linewidth = 0.6),
    legend.position  = "right",
    legend.key.width = unit(0.4, "cm"),
    plot.title       = element_text(size = 11, face = "plain")
  )

save_fig(fig5, "fig5_heatmap_v3", width = 6, height = 4)

# ── 10. 完成 ─────────────────────────────────────────────────────────────────────
cat("\n=== plot_benchmark_v3.R done ===\n")
cat("Output:", file.path(ANLYS_DIR, OUT_DIR), "\n")
cat("Figures: fig1_roc_v3, fig2_bar_v3, fig3_scatter_v3, fig4_bar_v3, fig5_heatmap_v3\n")
