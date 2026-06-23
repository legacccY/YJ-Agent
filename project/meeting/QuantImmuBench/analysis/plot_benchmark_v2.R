# plot_benchmark_v2.R
# 服务: quantimmu-bench — 发表级优美版 (v2)
# 功能: 5 张图 (NPG 配色, circular barplot, lollipop, balloon plot 等)
#       输出到 analysis/figures_R_v2/ (.png dpi=300 + .pdf)
# 运行: E:\R-4.3.3\bin\Rscript.exe plot_benchmark_v2.R
#       (从 analysis/ 目录运行)

# ── 0. 定位工作目录 ────────────────────────────────────────────────────────────
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

# ── 1. 安装/加载包 ─────────────────────────────────────────────────────────────
pkgs <- c("ggplot2", "dplyr", "tidyr", "readr", "scales", "ggrepel", "ggsci")
for (p in pkgs) {
  if (!requireNamespace(p, quietly = TRUE)) {
    install.packages(p, repos = "https://cloud.r-project.org", quiet = TRUE)
  }
  library(p, character.only = TRUE)
}

# ── 2. 读数据 ──────────────────────────────────────────────────────────────────
metrics  <- read_csv("metrics_ds2.csv",    show_col_types = FALSE)
roc_data <- read_csv("plotdata_roc.csv",   show_col_types = FALSE)
perpep   <- read_csv("plotdata_perpep.csv", show_col_types = FALSE)

# ── 3. 全局设置 ────────────────────────────────────────────────────────────────
# 工具顺序（按 max/>0 AUC 降序：PredIG 0.661, IMPROVE 0.621, NeoTImmuML 0.655, DeepImmuno 0.481）
# 视觉习惯：从高到低排列；pTuneos 追加末尾，结果出来后可按 AUC 重排
TOOL_ORDER <- c("PredIG", "NeoTImmuML", "IMPROVE", "DeepImmuno", "pTuneos")

# NPG 调色板（Nature Publishing Group）
# 手动固定 5 色（原 pal_npg("nrc")(4) 扩第 5 色 #F39B7F，与 ggsci NPG 顺序一致）
# NPG 顺序: "#E64B35" "#4DBBD5" "#00A087" "#3C5488" "#F39B7F" ...
TOOL_COLORS <- c(
  "PredIG"     = "#E64B35",   # 朱红
  "NeoTImmuML" = "#4DBBD5",   # 天蓝
  "IMPROVE"    = "#00A087",   # 绿松
  "DeepImmuno" = "#3C5488",   # 深蓝
  "pTuneos"    = "#F39B7F"    # NPG 第5色（salmon/橙粉）
)

# 阈值颜色（3色）
THR_COLORS <- c(">0" = "#E64B35", ">10" = "#4DBBD5", ">median" = "#00A087")
THR_LABELS <- c(">0" = "ELISpot > 0", ">10" = "ELISpot > 10", ">median" = "ELISpot > median")

# 聚合方式颜色
AGG_COLORS <- c("max" = "#E64B35", "mean" = "#4DBBD5", "top3mean" = "#00A087")
AGG_LABELS <- c("max" = "Max", "mean" = "Mean", "top3mean" = "Top-3 Mean")

# 统一基础主题
base_theme <- theme_bw(base_size = 13) +
  theme(
    plot.title        = element_text(face = "bold", size = 14, hjust = 0),
    plot.subtitle     = element_text(size = 11, colour = "grey40", hjust = 0),
    legend.position   = "right",
    legend.title      = element_text(size = 12, face = "bold"),
    legend.text       = element_text(size = 11),
    strip.background  = element_rect(fill = "grey94", colour = "grey70"),
    strip.text        = element_text(size = 12, face = "bold"),
    panel.grid.minor  = element_blank(),
    panel.grid.major  = element_line(colour = "grey92"),
    axis.title        = element_text(size = 12),
    axis.text         = element_text(size = 11),
    plot.margin       = margin(12, 16, 12, 12)
  )

# 输出目录
FIG_DIR <- file.path(ANLYS_DIR, "figures_R_v2")
dir.create(FIG_DIR, showWarnings = FALSE, recursive = TRUE)

save_fig <- function(p, name, w = 8, h = 6) {
  out_png <- file.path(FIG_DIR, paste0(name, ".png"))
  out_pdf <- file.path(FIG_DIR, paste0(name, ".pdf"))
  ggsave(out_png, plot = p, width = w, height = h, dpi = 300, units = "in")
  ggsave(out_pdf, plot = p, width = w, height = h)
  cat("Saved:", out_png, "\n")
  cat("Saved:", out_pdf, "\n")
}

# ════════════════════════════════════════════════════════════════════════════════
# Fig 1: ROC 曲线 (agg=max, >0) — NPG 色 + 右下角图例含 AUC
# ════════════════════════════════════════════════════════════════════════════════
cat("\n--- Fig 1: ROC curves ---\n")

roc1 <- roc_data %>%
  filter(Aggregation == "max", Threshold == ">0") %>%
  mutate(Tool = factor(Tool, levels = TOOL_ORDER))

# 每工具 AUC 标签（图例用）
auc_labels <- roc1 %>%
  distinct(Tool, auc) %>%
  arrange(match(Tool, TOOL_ORDER)) %>%
  mutate(legend_label = paste0(Tool, "  (AUC = ", sprintf("%.3f", auc), ")"))

label_map <- setNames(auc_labels$legend_label, as.character(auc_labels$Tool))

fig1 <- ggplot(roc1, aes(x = fpr, y = tpr, colour = Tool)) +
  # 对角随机线
  geom_abline(slope = 1, intercept = 0,
              linetype = "dashed", colour = "grey55", linewidth = 0.7) +
  # ROC 曲线（加粗，稍透明）
  geom_line(linewidth = 1.35, alpha = 0.9) +
  # 圆角端点标记（右上角终点，可视化完整覆盖）
  scale_colour_manual(values = TOOL_COLORS, labels = label_map) +
  scale_x_continuous(
    expand = c(0.01, 0), limits = c(0, 1),
    labels = scales::percent_format(accuracy = 1),
    breaks = seq(0, 1, 0.2)
  ) +
  scale_y_continuous(
    expand = c(0.01, 0), limits = c(0, 1.02),
    labels = scales::percent_format(accuracy = 1),
    breaks = seq(0, 1, 0.2)
  ) +
  labs(
    title    = "ROC Curves",
    subtitle = "DS2  |  Aggregation = max  |  Threshold: ELISpot > 0",
    x        = "False Positive Rate",
    y        = "True Positive Rate",
    colour   = NULL
  ) +
  base_theme +
  theme(
    legend.position  = "inside",
    legend.position.inside = c(0.98, 0.04),
    legend.justification   = c(1, 0),
    legend.background = element_rect(fill = alpha("white", 0.85),
                                     colour = "grey80", linewidth = 0.4),
    legend.key.width  = unit(1.8, "lines"),
    legend.text       = element_text(size = 10.5, family = "mono"),
    panel.grid.major  = element_line(colour = "grey90")
  ) +
  # 标注随机分类器
  annotate("text", x = 0.72, y = 0.65, label = "Random\nClassifier",
           colour = "grey50", size = 3.2, angle = 42, hjust = 0.5)

# 兜底：旧版 R 不支持 legend.position.inside，检测并回退
fig1_safe <- tryCatch({
  fig1  # 新版 ggplot2 >= 3.5
}, error = function(e) {
  fig1 + theme(legend.position = c(0.98, 0.04),
               legend.justification = c(1, 0))
})

save_fig(fig1_safe, "fig1_roc_v2", w = 7.5, h = 6)

# ════════════════════════════════════════════════════════════════════════════════
# Fig 2: Circular Grouped Barplot (agg=max, 3 阈值)
# 模板来源: R Graph Gallery #297，按 AUC 域 0-1 调整 ylim
# ════════════════════════════════════════════════════════════════════════════════
cat("\n--- Fig 2: Circular barplot ---\n")

# 准备数据：每行 = group(工具) + individual(阈值) + value(AUC)
circ_raw <- metrics %>%
  filter(Aggregation == "max") %>%
  select(group = Tool, individual = Threshold, value = AUC_ROC) %>%
  mutate(
    group      = factor(group, levels = TOOL_ORDER),
    individual = factor(individual, levels = c(">0", ">10", ">median"),
                        labels = c("ELI>0", "ELI>10", "ELI>med"))
  ) %>%
  arrange(group, individual)

# 组间插入空行（empty_bar 个）
empty_bar <- 2
n_groups   <- nlevels(circ_raw$group)

# 为每组追加 empty_bar 行 NA
to_add <- data.frame(
  group      = rep(levels(circ_raw$group), each = empty_bar),
  individual = rep(NA, n_groups * empty_bar),
  value      = rep(NA, n_groups * empty_bar),
  stringsAsFactors = FALSE
)
to_add$group <- factor(to_add$group, levels = TOOL_ORDER)

circ_data <- bind_rows(circ_raw, to_add) %>%
  arrange(group, individual) %>%
  mutate(id = row_number())

# 计算每条的旋转角度（用于文字旋转）
number_of_bar <- nrow(circ_data)
label_data    <- circ_data %>%
  mutate(
    angle = 90 - 360 * (id - 0.5) / number_of_bar,
    hjust = ifelse(angle < -90, 1, 0),
    angle = ifelse(angle < -90, angle + 180, angle)
  )

# 每组起止 id（用于外圈工具名标注）
base_data <- circ_data %>%
  group_by(group) %>%
  summarise(
    start = min(id),
    end   = max(id) - empty_bar,
    .groups = "drop"
  ) %>%
  rowwise() %>%
  mutate(title_x = mean(c(start, end))) %>%
  ungroup() %>%
  # 计算每组中心角度（与 label_data 同算法），用于外圈文字旋转
  mutate(
    angle = 90 - 360 * (title_x - 0.5) / number_of_bar,
    hjust = ifelse(angle < -90, 1, 0),
    angle = ifelse(angle < -90, angle + 180, angle)
  )

# 参考圈数据（y = 0.5, 0.6, 0.7）
ref_lines <- data.frame(
  yintercept = c(0.5, 0.6, 0.7),
  label      = c("0.50", "0.60", "0.70")
)

# AUC 值域 0-1，ylim 下限设负值做中心洞（圆心干净留空）
Y_MIN      <- -0.45
Y_MAX      <- max(circ_data$value, na.rm = TRUE) + 0.28  # 外圈留余量给工具名
LABEL_Y    <- max(circ_data$value, na.rm = TRUE) + 0.10  # 工具名 y 位置（柱顶之上）
REF_ANNO_X <- 1.8   # 参考环数值固定在此 x（避开柱子，放在组间空档）

fig2 <- ggplot(circ_data, aes(x = as.factor(id), y = value, fill = group)) +
  # 参考圆环（极坐标下 geom_hline → 圆）
  geom_hline(data = ref_lines, aes(yintercept = yintercept),
             colour = "grey72", linewidth = 0.4, linetype = "dashed",
             inherit.aes = FALSE) +
  # 主柱
  geom_bar(stat = "identity", alpha = 0.87, width = 0.85) +
  # 柱顶 AUC 值标注（旋转对齐）
  geom_text(
    data = label_data %>% filter(!is.na(value)),
    aes(x = id, y = value + 0.025,
        label = sprintf("%.3f", value),
        hjust = hjust, angle = angle),
    size = 2.6, colour = "grey20", fontface = "bold",
    inherit.aes = FALSE
  ) +
  # 参考环数值标注（固定在 x≈1.8，组间空档，不堆圆心）
  geom_text(
    data = ref_lines,
    aes(x = REF_ANNO_X, y = yintercept + 0.012, label = label),
    size = 2.5, colour = "grey52", hjust = 0.5,
    inherit.aes = FALSE
  ) +
  # 工具名移到外圈弧上（沿组中心角旋转，y = LABEL_Y）
  geom_text(
    data = base_data,
    aes(x = title_x, y = LABEL_Y,
        label = group,
        hjust = hjust, angle = angle),
    colour = "grey10", size = 3.4, fontface = "bold",
    inherit.aes = FALSE
  ) +
  scale_fill_manual(
    values = TOOL_COLORS,
    guide  = guide_legend(title = "Tool", nrow = 2, byrow = TRUE)
  ) +
  ylim(Y_MIN, Y_MAX) +
  labs(
    title    = "AUC-ROC by Tool and Threshold",
    subtitle = "Aggregation = max  |  Bars within each group (clockwise): ELISpot>0, >10, >median",
    fill     = "Tool"
  ) +
  theme_minimal(base_size = 13) +
  theme(
    plot.title       = element_text(face = "bold", size = 14, hjust = 0.5),
    plot.subtitle    = element_text(size = 10.5, colour = "grey40", hjust = 0.5),
    legend.position  = "bottom",
    legend.text      = element_text(size = 11),
    legend.title     = element_text(size = 12, face = "bold"),
    axis.text        = element_blank(),
    axis.title       = element_blank(),
    panel.grid       = element_blank(),
    plot.margin      = margin(24, 24, 24, 24)
  ) +
  coord_polar(start = 0)

save_fig(fig2, "fig2_circular_auc_v2", w = 8, h = 8)

# ════════════════════════════════════════════════════════════════════════════════
# Fig 3: 散点 + 趋势线 + rug (agg=max, facet 4 工具)
# 精致版：角标 rho/p-value 文字框 + rug + lm 趋势带
# ════════════════════════════════════════════════════════════════════════════════
cat("\n--- Fig 3: Scatter + smooth ---\n")

# rho/p 标签（来自 metrics，agg=max, threshold=>0 的 Spearman）
rho_labels <- metrics %>%
  filter(Aggregation == "max", Threshold == ">0") %>%
  select(Tool, Spearman_rho, Spearman_pval) %>%
  mutate(
    p_str    = ifelse(Spearman_pval < 0.001, "p < 0.001",
               ifelse(Spearman_pval < 0.01,  paste0("p = ", sprintf("%.3f", Spearman_pval)),
                      paste0("p = ", sprintf("%.3f", Spearman_pval)))),
    rho_str  = sprintf("rho = %.3f", Spearman_rho),
    anno     = paste0(rho_str, "\n", p_str),
    sig_star = ifelse(Spearman_pval < 0.05, "*", "")
  )

fig3_data <- perpep %>%
  filter(Aggregation == "max") %>%
  mutate(Tool = factor(Tool, levels = TOOL_ORDER)) %>%
  left_join(rho_labels %>% select(Tool, anno, Spearman_rho, Spearman_pval),
            by = "Tool")

# 每个 facet 的 x 范围（用于定位文字框）
fig3_xranges <- fig3_data %>%
  group_by(Tool) %>%
  summarise(
    xmin   = min(score, na.rm = TRUE),
    xmax   = max(score, na.rm = TRUE),
    ymax   = max(Elispot, na.rm = TRUE),
    .groups = "drop"
  ) %>%
  left_join(rho_labels %>% select(Tool, anno, Spearman_pval), by = "Tool") %>%
  mutate(
    text_x = xmax,
    text_y = ymax,
    # 显著性用颜色区分
    text_col = ifelse(Spearman_pval < 0.05, "#E64B35", "grey40")
  )

fig3 <- ggplot(fig3_data, aes(x = score, y = Elispot, colour = Tool)) +
  # 点（加透明度避免重叠）
  geom_point(alpha = 0.5, size = 1.9, shape = 16) +
  # rug 边际分布
  geom_rug(sides = "b", alpha = 0.25, linewidth = 0.4, colour = "grey50") +
  # lm 趋势线 + 置信带
  geom_smooth(
    method  = "lm", se = TRUE,
    colour  = "grey25", fill = "grey85",
    linewidth = 0.85, alpha = 0.35
  ) +
  # Spearman rho/p 文字标注（右上角）
  geom_text(
    data = fig3_xranges,
    aes(x = text_x, y = text_y, label = anno, colour = NULL),
    hjust = 1.02, vjust = 1.08,
    size = 3.1, lineheight = 1.35,
    colour = fig3_xranges$text_col,
    fontface = "plain",
    inherit.aes = FALSE
  ) +
  facet_wrap(~ Tool, scales = "free_x", ncol = 2) +
  scale_colour_manual(values = TOOL_COLORS, guide = "none") +
  scale_y_continuous(labels = scales::comma_format()) +
  labs(
    title    = "Predicted Score vs ELISpot",
    subtitle = "DS2  |  Aggregation = max  |  Colour = tool (NPG)  |  Red annotation = significant (p < 0.05)",
    x        = "Predicted Immunogenicity Score",
    y        = "ELISpot (SFC)"
  ) +
  base_theme +
  theme(
    strip.text      = element_text(size = 12, face = "bold"),
    panel.grid.major = element_line(colour = "grey93")
  )

save_fig(fig3, "fig3_scatter_v2", w = 9, h = 7.5)

# ════════════════════════════════════════════════════════════════════════════════
# Fig 4: Lollipop — 聚合方式对比 (阈值 >10)
# geom_segment (竹竿) + geom_point (圆) + 0.5 参考线
# ════════════════════════════════════════════════════════════════════════════════
cat("\n--- Fig 4: Lollipop ---\n")

fig4_data <- metrics %>%
  filter(Threshold == ">10") %>%
  mutate(
    Tool        = factor(Tool, levels = TOOL_ORDER),
    # 先保留原始 key 做颜色映射，再加 label 列用于图例文字
    Agg_key     = Aggregation,
    Aggregation = factor(Aggregation, levels = c("max", "mean", "top3mean"),
                         labels = c("Max", "Mean", "Top-3 Mean")),
    # dodge 偏移量（手动，避免 position_dodge 与 segment 不对齐）
    dodge_offset = as.numeric(Aggregation) - 2  # -1, 0, +1
  )

# dodge 宽度
DODGE_W <- 0.28

fig4_dodged <- fig4_data %>%
  mutate(
    x_pos = as.numeric(Tool) + dodge_offset * DODGE_W
  )

fig4 <- ggplot(fig4_dodged) +
  # 参考线 AUC=0.5（随机）
  geom_hline(yintercept = 0.5, linetype = "dashed",
             colour = "grey40", linewidth = 0.75) +
  annotate("text", x = 0.52, y = 0.502, label = "Random (0.5)",
           colour = "grey40", size = 3.1, hjust = 0, vjust = 0) +
  # 竹竿（从 0.3 出发，让图更好看；不从 0 出发避免底部拥挤）
  geom_segment(
    aes(x = x_pos, xend = x_pos,
        y = 0.3, yend = AUC_ROC,
        colour = Aggregation),
    linewidth = 1.1, alpha = 0.75
  ) +
  # 圆球
  geom_point(
    aes(x = x_pos, y = AUC_ROC, colour = Aggregation),
    size = 4.5, alpha = 0.95
  ) +
  # AUC 值标注（圆球右上方）
  geom_text(
    aes(x = x_pos + 0.04, y = AUC_ROC + 0.008,
        label = sprintf("%.3f", AUC_ROC),
        colour = Aggregation),
    size = 2.8, hjust = 0, fontface = "bold"
  ) +
  scale_colour_manual(
    values = setNames(AGG_COLORS, c("Max", "Mean", "Top-3 Mean")),
    guide  = guide_legend(title = "Aggregation", override.aes = list(size = 4))
  ) +
  scale_x_continuous(
    breaks = 1:nlevels(fig4_data$Tool),
    labels = levels(fig4_data$Tool),
    limits = c(0.4, nlevels(fig4_data$Tool) + 0.7)
  ) +
  scale_y_continuous(
    limits = c(0.28, 0.82),  # TODO: 若 pTuneos AUC > 0.82 需扩上限
    breaks = seq(0.3, 0.8, 0.1),
    expand = c(0, 0)
  ) +
  labs(
    title    = "AUC-ROC by Aggregation Method",
    subtitle = "Threshold: ELISpot > 10  |  NPG colour by aggregation",
    x        = NULL,
    y        = "AUC-ROC",
    colour   = "Aggregation"
  ) +
  base_theme +
  theme(
    legend.position  = "right",
    panel.grid.major.x = element_blank(),
    panel.grid.major.y = element_line(colour = "grey90"),
    axis.text.x      = element_text(size = 12, face = "bold")
  )

save_fig(fig4, "fig4_lollipop_v2", w = 9, h = 6)

# ════════════════════════════════════════════════════════════════════════════════
# Fig 5: Balloon Plot — 替换丑热力图
# geom_point(aes(size=AUC, color=AUC)) + viridis + 数值标注
# 工具(y) × 阈值(x) AUC 气泡图（agg=max）
# ════════════════════════════════════════════════════════════════════════════════
cat("\n--- Fig 5: Balloon plot ---\n")

fig5_data <- metrics %>%
  filter(Aggregation == "max") %>%
  mutate(
    Tool = factor(Tool,
                  levels = rev(TOOL_ORDER)),   # 从上到下: DeepImmuno -> PredIG
    Threshold = factor(Threshold,
                       levels = c(">0", ">10", ">median"),
                       labels = c("ELISpot > 0", "ELISpot > 10", "ELISpot > median")),
    # 文字颜色预计算（存为列，避免 discrete/continuous aes 冲突）
    txt_col = ifelse(AUC_ROC > 0.59, "white", "grey20")
  )

fig5 <- ggplot(fig5_data, aes(x = Threshold, y = Tool)) +
  # 底色参考方块（淡灰，帮助对齐视线）
  geom_tile(fill = "grey97", colour = "grey88", linewidth = 0.5) +
  # 气泡（大小 + 颜色双编码 AUC）
  geom_point(
    aes(size = AUC_ROC, colour = AUC_ROC),
    alpha = 0.9
  ) +
  # AUC 数值标注（高 AUC 白字，低 AUC 深字；colour 固定不进 scale）
  geom_text(
    aes(label = sprintf("%.3f", AUC_ROC)),
    colour    = fig5_data$txt_col,   # 固定向量，不经 aes scale 映射
    size      = 3.5,
    fontface  = "bold",
    inherit.aes = TRUE
  ) +
  # viridis 颜色映射（plasma/magma 暖色，或 viridis 冷暖）
  scale_colour_viridis_c(
    option   = "plasma",       # 紫→橙→黄，视觉冲击力强
    name     = "AUC-ROC",
    limits   = c(0.43, 0.76),  # TODO: 若 pTuneos AUC 超出 [0.43,0.76] 需调 limits
    breaks   = c(0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75),
    labels   = sprintf("%.2f", c(0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75)),
    guide    = guide_colorbar(
      barwidth  = 0.9,
      barheight = 8,
      title.position = "top",
      title.hjust    = 0.5
    )
  ) +
  # 气泡大小图例
  scale_size_continuous(
    name   = "AUC-ROC",
    range  = c(6, 22),
    limits = c(0.43, 0.76),
    breaks = c(0.45, 0.55, 0.65, 0.75),
    guide  = "none"             # 颜色条已足够，隐藏重复尺寸图例
  ) +
  labs(
    title    = "AUC-ROC Balloon Chart — Tool × Threshold",
    subtitle = "Aggregation = max  |  Bubble size & colour encode AUC-ROC  |  Plasma colormap",
    x        = NULL,
    y        = NULL
  ) +
  base_theme +
  theme(
    legend.position  = "right",
    panel.grid       = element_blank(),
    panel.border     = element_rect(colour = "grey80", fill = NA, linewidth = 0.6),
    axis.text.x      = element_text(size = 12),
    axis.text.y      = element_text(size = 12, face = "bold"),
    plot.title       = element_text(face = "bold", size = 14)
  )

save_fig(fig5, "fig5_balloon_v2", w = 9, h = 5.5)

# ════════════════════════════════════════════════════════════════════════════════
cat("\n=== All figures saved to:", FIG_DIR, "===\n")
cat("Files: fig1_roc_v2, fig2_circular_auc_v2, fig3_scatter_v2,\n")
cat("       fig4_lollipop_v2, fig5_balloon_v2  (each .png + .pdf)\n")
