# plot_benchmark.R
# 服务: quantimmu-bench
# 功能: 读 export_plot_data.py 生成的 CSV, 用 ggplot2 画 5 张顶会风格图
#       输出到 analysis/figures_R/ (.png + .pdf, dpi=300)
# 运行: E:\R-4.3.3\bin\Rscript.exe plot_benchmark.R
#       (从 analysis/ 目录运行, 或脚本内 setwd 自动定位)

# ── 0. 定位工作目录 ────────────────────────────────────────────────────────────
script_path <- tryCatch(
  normalizePath(sys.frame(1)$ofile),
  error = function(e) normalizePath(commandArgs(trailingOnly = FALSE)[
    grep("--file=", commandArgs(trailingOnly = FALSE))
  ][1] |> sub("--file=", "", x = _))
)
# 兜底: 手动改这里
ANLYS_DIR <- if (!is.na(script_path) && nchar(script_path) > 0) {
  dirname(script_path)
} else {
  "D:/YJ-Agent/project/meeting/QuantImmuBench/analysis"
}
setwd(ANLYS_DIR)
cat("Working dir:", getwd(), "\n")

# ── 1. 安装/加载包 ─────────────────────────────────────────────────────────────
pkgs <- c("ggplot2", "dplyr", "tidyr", "readr", "scales", "ggrepel")
for (p in pkgs) {
  if (!requireNamespace(p, quietly = TRUE)) {
    install.packages(p, repos = "https://cloud.r-project.org", quiet = TRUE)
  }
  library(p, character.only = TRUE)
}

# ── 2. 读数据 ──────────────────────────────────────────────────────────────────
metrics  <- read_csv("metrics_ds2.csv",   show_col_types = FALSE)
roc_data <- read_csv("plotdata_roc.csv",  show_col_types = FALSE)
perpep   <- read_csv("plotdata_perpep.csv", show_col_types = FALSE)

# ── 3. 全局设置 ────────────────────────────────────────────────────────────────
TOOL_COLORS <- c(
  "DeepImmuno" = "#E6693E",
  "PredIG"     = "#4C9BE8",
  "IMPROVE"    = "#3DA851",
  "NeoTImmuML" = "#9B59B6",
  "pTuneos"    = "#D55E00"
)
TOOL_ORDER <- c("PredIG", "NeoTImmuML", "IMPROVE", "DeepImmuno", "pTuneos")

base_theme <- theme_bw(base_size = 12) +
  theme(
    plot.title       = element_text(face = "bold", size = 13),
    legend.position  = "bottom",
    legend.title     = element_text(size = 11),
    strip.background = element_rect(fill = "grey92", colour = "grey70"),
    strip.text       = element_text(size = 11, face = "bold"),
    panel.grid.minor = element_blank()
  )

FIG_DIR <- file.path(ANLYS_DIR, "figures_R")
dir.create(FIG_DIR, showWarnings = FALSE)

save_fig <- function(p, name, w = 8, h = 6) {
  ggsave(file.path(FIG_DIR, paste0(name, ".png")),
         plot = p, width = w, height = h, dpi = 300, units = "in")
  ggsave(file.path(FIG_DIR, paste0(name, ".pdf")),
         plot = p, width = w, height = h)
  cat("Saved:", name, "\n")
}

# ── Fig 1: ROC 曲线 (DS2, agg=max, >0) ────────────────────────────────────────
roc1 <- roc_data %>%
  filter(Aggregation == "max", Threshold == ">0")

# AUC 标签 (每工具唯一)
auc_labels <- roc1 %>%
  distinct(Tool, auc) %>%
  mutate(label = paste0(Tool, " (AUC=", sprintf("%.3f", auc), ")"),
         Tool  = factor(Tool, levels = TOOL_ORDER))

roc1 <- roc1 %>%
  mutate(Tool = factor(Tool, levels = TOOL_ORDER))

fig1 <- ggplot(roc1, aes(x = fpr, y = tpr, colour = Tool)) +
  geom_line(linewidth = 1.2) +
  geom_abline(slope = 1, intercept = 0, linetype = "dashed",
              colour = "grey50", linewidth = 0.8) +
  scale_colour_manual(
    values = TOOL_COLORS,
    labels = setNames(auc_labels$label, auc_labels$Tool)
  ) +
  scale_x_continuous(expand = c(0.01, 0), limits = c(0, 1),
                     labels = scales::percent_format()) +
  scale_y_continuous(expand = c(0.01, 0), limits = c(0, 1.02),
                     labels = scales::percent_format()) +
  labs(
    title   = "ROC Curves — DS2, ELISpot > 0, Aggregation = max",
    x       = "False Positive Rate",
    y       = "True Positive Rate",
    colour  = NULL
  ) +
  base_theme +
  theme(legend.position = "right")

save_fig(fig1, "fig1_roc_curves_ds2", w = 8, h = 6)

# ── Fig 2: AUC 柱状 (agg=max, 3 阈值) ─────────────────────────────────────────
fig2_data <- metrics %>%
  filter(Aggregation == "max") %>%
  mutate(
    Tool      = factor(Tool, levels = TOOL_ORDER),
    Threshold = factor(Threshold, levels = c(">0", ">10", ">median"))
  )

fig2 <- ggplot(fig2_data, aes(x = Tool, y = AUC_ROC, fill = Threshold)) +
  geom_col(position = position_dodge(width = 0.75), width = 0.65) +
  geom_hline(yintercept = 0.5, linetype = "dashed", colour = "grey40",
             linewidth = 0.7) +
  geom_text(aes(label = sprintf("%.3f", AUC_ROC)),
            position = position_dodge(width = 0.75),
            vjust = -0.4, size = 3.2, fontface = "bold") +
  scale_fill_manual(
    values = c(">0" = "#5B9BD5", ">10" = "#ED7D31", ">median" = "#70AD47"),
    labels = c(">0" = "ELISpot > 0", ">10" = "ELISpot > 10",
               ">median" = "ELISpot > median")
  ) +
  scale_y_continuous(limits = c(0, 0.85), expand = c(0, 0)) +  # TODO: 若 pTuneos AUC > 0.85 需扩上限
  labs(
    title = "AUC-ROC by Tool and Threshold  (Aggregation = max)",
    x     = NULL,
    y     = "AUC-ROC",
    fill  = "Threshold"
  ) +
  base_theme +
  theme(legend.position = "bottom")

save_fig(fig2, "fig2_auc_bar_thresholds", w = 9, h = 6)

# ── Fig 3: 预测分 vs ELISpot 散点 (4 工具 facet, agg=max) ────────────────────
# Spearman rho 标签从 metrics 取 (agg=max, >0)
rho_labels <- metrics %>%
  filter(Aggregation == "max", Threshold == ">0") %>%
  select(Tool, Spearman_rho, Spearman_pval) %>%
  mutate(
    sig   = ifelse(Spearman_pval < 0.05, "*", "ns"),
    label = paste0("rho = ", sprintf("%.3f", Spearman_rho), sig)
  )

fig3_data <- perpep %>%
  filter(Aggregation == "max") %>%
  left_join(rho_labels %>% select(Tool, label), by = "Tool") %>%
  mutate(Tool_label = paste0(Tool, "\n", label),
         Tool       = factor(Tool, levels = TOOL_ORDER))

# 重排 facet label
tool_label_map <- fig3_data %>%
  distinct(Tool, Tool_label) %>%
  arrange(Tool)

fig3_data <- fig3_data %>%
  mutate(Tool_label = factor(Tool_label,
                             levels = tool_label_map$Tool_label))

fig3 <- ggplot(fig3_data, aes(x = score, y = Elispot, colour = Tool)) +
  geom_point(alpha = 0.55, size = 1.8) +
  geom_smooth(method = "lm", se = TRUE, colour = "black",
              linewidth = 0.8, fill = "grey80") +
  facet_wrap(~ Tool_label, scales = "free_x", ncol = 2) +
  scale_colour_manual(values = TOOL_COLORS, guide = "none") +
  labs(
    title = "Predicted Score vs ELISpot  (DS2, Aggregation = max)",
    x     = "Predicted Immunogenicity Score",
    y     = "ELISpot (SFC)"
  ) +
  base_theme +
  theme(strip.text = element_text(size = 10))

save_fig(fig3, "fig3_score_vs_elispot_scatter", w = 9, h = 7)

# ── Fig 4: 聚合方式对比 (阈值 >10) ────────────────────────────────────────────
fig4_data <- metrics %>%
  filter(Threshold == ">10") %>%
  mutate(
    Tool        = factor(Tool, levels = TOOL_ORDER),
    Aggregation = factor(Aggregation, levels = c("max", "mean", "top3mean"))
  )

fig4 <- ggplot(fig4_data, aes(x = Tool, y = AUC_ROC, fill = Aggregation)) +
  geom_col(position = position_dodge(width = 0.75), width = 0.65) +
  geom_hline(yintercept = 0.5, linetype = "dashed", colour = "grey40",
             linewidth = 0.7) +
  geom_text(aes(label = sprintf("%.3f", AUC_ROC)),
            position = position_dodge(width = 0.75),
            vjust = -0.4, size = 3.2) +
  scale_fill_manual(
    values = c("max" = "#4472C4", "mean" = "#ED7D31", "top3mean" = "#A9D18E"),
    labels = c("max" = "Max", "mean" = "Mean", "top3mean" = "Top-3 Mean")
  ) +
  scale_y_continuous(limits = c(0, 0.82), expand = c(0, 0)) +  # TODO: 若 pTuneos AUC > 0.82 需扩上限
  labs(
    title = "AUC-ROC by Aggregation Method  (Threshold = ELISpot > 10)",
    x     = NULL,
    y     = "AUC-ROC",
    fill  = "Aggregation"
  ) +
  base_theme +
  theme(legend.position = "bottom")

save_fig(fig4, "fig4_aggregation_comparison", w = 9, h = 6)

# ── Fig 5: 工具 × 阈值 AUC 热图 (agg=max) ────────────────────────────────────
fig5_data <- metrics %>%
  filter(Aggregation == "max") %>%
  mutate(
    Tool      = factor(Tool, levels = rev(TOOL_ORDER)),
    Threshold = factor(Threshold, levels = c(">0", ">10", ">median"),
                       labels = c("ELISpot > 0", "ELISpot > 10",
                                  "ELISpot > median"))
  )

fig5 <- ggplot(fig5_data, aes(x = Threshold, y = Tool, fill = AUC_ROC)) +
  geom_tile(colour = "white", linewidth = 1) +
  geom_text(aes(label = sprintf("%.3f", AUC_ROC)),
            size = 4, fontface = "bold",
            colour = ifelse(fig5_data$AUC_ROC > 0.62, "white", "grey20")) +
  scale_fill_gradient2(
    low     = "#D73027",
    mid     = "#FEE08B",
    high    = "#1A9850",
    midpoint = 0.55,
    limits  = c(0.44, 0.72),
    name    = "AUC-ROC",
    guide   = guide_colorbar(barwidth = 10, barheight = 0.8,
                              title.position = "top")
  ) +
  labs(
    title = "AUC-ROC Heatmap — Tool × Threshold  (Aggregation = max)",
    x     = NULL,
    y     = NULL
  ) +
  base_theme +
  theme(
    legend.position  = "bottom",
    panel.grid       = element_blank(),
    axis.text        = element_text(size = 12),
    panel.border     = element_blank()
  )

save_fig(fig5, "fig5_auc_heatmap", w = 8, h = 5)

cat("\nAll figures saved to:", FIG_DIR, "\n")
