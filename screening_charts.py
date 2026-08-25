# -*- coding: utf-8 -*-
"""
因子篩選平台的圖表產生——matplotlib 畫圖、轉 base64 內嵌進報告 HTML。

架構檢討第3項(2026-08-25)拆自 factor_screening.py，見 screening_gates.py 開頭
的說明。這支模組只負責「拿算好的資料畫圖」，不做任何統計計算(算好的資料
由 screening_gates.py 提供)，也不組HTML骨架(那是 screening_render.py 的事，
它會把這裡回傳的 base64 字串塞進 <img> 標籤)。
"""
import numpy as np
import matplotlib.pyplot as plt

import factor_validation_analysis as fva
import update_dashboard as ud
from transform_modes import _resolve_source

# 跟儀表板一致的情緒分級色階(淺色模式)，用在分數走勢圖的背景色帶
TIER_COLORS = ["#2f6b4f", "#5c8a6e", "#6b7280", "#b1592f", "#a6362f"]


# ================================================================ 熱力圖
def heatmap_chart_base64(heatmap_data, title, cmap="RdBu_r"):
    if heatmap_data is None:
        return None
    grid = heatmap_data["grid"]
    hold_days = heatmap_data["hold_days"]
    buckets = heatmap_data["buckets"]
    fig, ax = plt.subplots(figsize=(7.6, 4.0), dpi=140)
    finite = grid[np.isfinite(grid)]
    vmax = float(np.percentile(np.abs(finite), 98)) if finite.size else 1.0
    vmax = vmax if vmax > 0 else 1.0
    im = ax.imshow(grid, cmap=cmap, vmin=-vmax, vmax=vmax, aspect="auto")
    ax.set_xticks(range(len(hold_days)))
    ax.set_xticklabels(hold_days, fontsize=8)
    ax.set_yticks(range(buckets))
    ax.set_yticklabels([f"D{i + 1}" for i in range(buckets)], fontsize=8)
    ax.set_xlabel("持有天數", fontsize=9)
    ax.set_ylabel(f"分數分組（D1恐懼 → D{buckets}貪婪）", fontsize=9)
    ax.set_title(title, fontsize=10)
    for i in range(grid.shape[0]):
        for j in range(grid.shape[1]):
            if np.isfinite(grid[i, j]):
                ax.text(j, i, f"{grid[i, j]:.1f}", ha="center", va="center", fontsize=6, color="#1a1a1a")
    unit_str = "殖利率變動 (bp)" if fva.TARGET == "UST_10Yr" else "報酬 (%)"
    fig.colorbar(im, ax=ax, shrink=0.8, label=unit_str)
    fig.tight_layout()
    return fva.fig_to_base64(fig)



# ================================================================ 回測權益曲線圖
def backtest_chart_base64(bt, label):
    """權益曲線圖：策略 vs 無條件買進持有，並標出樣本內/外分界。"""
    if bt is None:
        return None
    fig, ax = plt.subplots(figsize=(7.6, 3.6), dpi=140)
    ax.plot(bt["curve"].index, bt["curve"], color="#1e3a5f", linewidth=1.4,
            label="因子策略（累積價格報酬 bp）")
    ax.plot(bt["curve_bh"].index, bt["curve_bh"], color="#a6742a", linewidth=1.1,
            linestyle="--", alpha=0.85, label="對照：無條件買進持有")
    ax.axhline(0, color="#888", linewidth=0.8)
    ax.axvline(bt["split_date"], color="#a6362f", linewidth=1.0, linestyle=":", alpha=0.8)
    ax.text(bt["split_date"], ax.get_ylim()[1], " 樣本外起點 ", fontsize=7.5,
            color="#a6362f", va="top", ha="left")
    ax.set_ylabel("累積報酬 (bp)", fontsize=9)
    ax.tick_params(labelsize=8)
    ax.legend(fontsize=8, loc="upper left", frameon=False)
    ax.set_title(f"{label}：回測權益曲線（部位＝(50−分數)/50，死區空手）", fontsize=10)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    return fva.fig_to_base64(fig)



# ================================================================ 單一因子報告用的圖表
def score_trend_chart_base64(main_df, key, label):
    """圖1:分數走勢圖。背景疊五色情緒分級色帶(跟儀表板一致)，右軸疊美國10年期
    公債殖利率(UST_10Yr)當視覺參考——殖利率純粹對照用，不參與任何統計計算，
    這點也跟儀表板現有每個因子卡片的第一張圖完全一致的做法。"""
    if key not in main_df.columns:
        return None
    score = main_df[key].dropna()
    if score.empty:
        return None
    fig, ax = plt.subplots(figsize=(7.6, 3.6), dpi=140)
    prev = 0
    for i, th in enumerate(ud._G["label_thresholds"]):
        hi = min(th["lt"], 100)
        ax.axhspan(prev, hi, color=TIER_COLORS[i % len(TIER_COLORS)], alpha=0.10, zorder=0)
        prev = th["lt"]
    ax.plot(main_df.index, main_df[key], color="#1e3a5f", linewidth=1.2, label=label, zorder=3)
    ax.set_ylim(0, 100)
    ax.set_ylabel("分數 (0–100)", fontsize=9)
    ax.tick_params(labelsize=8)
    if "UST_10Yr" in main_df.columns:
        ax2 = ax.twinx()
        ax2.plot(main_df.index, main_df["UST_10Yr"], color="#a6742a", linewidth=1.0,
                  linestyle="--", alpha=0.75, zorder=2)
        ax2.set_ylabel("10年期公債殖利率 (%，僅供對照)", fontsize=9, color="#a6742a")
        ax2.tick_params(labelsize=8, colors="#a6742a")
    ax.set_title(f"{label}：分數走勢（疊加美國10年期公債殖利率，僅供對照）", fontsize=10)
    for spine in ["top"]:
        ax.spines[spine].set_visible(False)
    fig.tight_layout()
    return fva.fig_to_base64(fig)


def fear_greed_overlay_chart_base64(main_df, key, label, fear_threshold=25, greed_threshold=75):
    """圖1b：ZN期貨價格走勢 + 恐懼/貪婪散點疊圖。
    在ZN期貨的時間軸上，用綠點標出因子分數<25（極度恐懼）的日子，
    用紅點標出分數>75（極度貪婪）的日子，讓使用者直觀看到
    「恐懼/貪婪分別發生在哪個價位、哪個時間點」。"""
    target = fva.TARGET  # ZN_futures
    if target not in main_df.columns or key not in main_df.columns:
        return None
    price = main_df[target].dropna()
    score = main_df[key].reindex(price.index)
    if price.empty or score.dropna().empty:
        return None

    fear_mask = score < fear_threshold
    greed_mask = score > greed_threshold
    n_fear = int(fear_mask.sum())
    n_greed = int(greed_mask.sum())

    fig, ax = plt.subplots(figsize=(7.6, 3.6), dpi=140)

    # 底層：ZN期貨價格線
    ax.plot(price.index, price.values, color="#888888", linewidth=0.9, alpha=0.6, zorder=1)

    # 恐懼散點（綠色）
    if n_fear > 0:
        fear_dates = price.index[fear_mask.reindex(price.index, fill_value=False)]
        ax.scatter(fear_dates, price.loc[fear_dates], color="#2f6b4f", s=12, alpha=0.7,
                   edgecolors="none", zorder=3, label=f"分數<{fear_threshold} 極度恐懼（{n_fear}天）")

    # 貪婪散點（紅色）
    if n_greed > 0:
        greed_dates = price.index[greed_mask.reindex(price.index, fill_value=False)]
        ax.scatter(greed_dates, price.loc[greed_dates], color="#a6362f", s=12, alpha=0.7,
                   edgecolors="none", zorder=3, label=f"分數>{greed_threshold} 極度貪婪（{n_greed}天）")

    y_label = "10年期美債殖利率 (%)" if target == "UST_10Yr" else "ZN期貨價格"
    chart_title = f"{label}：恐懼與貪婪在10年期美債殖利率時間軸上的分布" if target == "UST_10Yr" else f"{label}：恐懼與貪婪在ZN期貨時間軸上的分布"
    ax.set_ylabel(y_label, fontsize=9)
    ax.set_title(chart_title, fontsize=10)
    ax.legend(fontsize=8, loc="upper left", frameon=False)
    ax.tick_params(labelsize=8)
    ax.spines["top"].set_visible(False)
    fig.tight_layout()
    return fva.fig_to_base64(fig)


def raw_data_chart_base64(config, main_df, label):
    """圖2:原始資料走勢圖。依候選因子選的轉換模式，對應現有七個因子在儀表板上
    各自第二張圖的呈現邏輯(例如動能秀ZN期貨+125日均線、殖利率曲線形狀秀
    10年期+2年期殖利率原始數值)。"""
    mode = config["mode"]
    sources = config["sources"]
    params = config.get("params", {})
    window = params.get("window")

    try:
        if mode in ("ma_deviation", "moving_average"):
            series, _ = _resolve_source(sources["series"], main_df)
            series = series.reindex(main_df.index)
            ma = series.rolling(window, min_periods=window).mean() if window else None
            fig, ax = plt.subplots(figsize=(7.6, 3.2), dpi=140)
            ax.plot(main_df.index, series, color="#1e3a5f", linewidth=1.1, label="原始數列")
            if ma is not None:
                ax.plot(main_df.index, ma, color="#a6742a", linewidth=1.1, label=f"{window}日移動平均")
        elif mode == "range_position":
            series, _ = _resolve_source(sources["series"], main_df)
            series = series.reindex(main_df.index)
            hi = series.rolling(window, min_periods=window).max() if window else None
            lo = series.rolling(window, min_periods=window).min() if window else None
            fig, ax = plt.subplots(figsize=(7.6, 3.2), dpi=140)
            ax.plot(main_df.index, series, color="#1e3a5f", linewidth=1.1, label="原始數列")
            if hi is not None:
                ax.plot(main_df.index, hi, color="#a6362f", linewidth=0.9, alpha=0.75, label=f"{window}日滾動高點")
                ax.plot(main_df.index, lo, color="#2f6b4f", linewidth=0.9, alpha=0.75, label=f"{window}日滾動低點")
        elif mode == "return_spread":
            series_a, _ = _resolve_source(sources["a"], main_df)
            series_b, _ = _resolve_source(sources["b"], main_df)
            series_a, series_b = series_a.reindex(main_df.index), series_b.reindex(main_df.index)
            base_a, base_b = series_a.dropna().iloc[0] if series_a.dropna().size else None, \
                series_b.dropna().iloc[0] if series_b.dropna().size else None
            fig, ax = plt.subplots(figsize=(7.6, 3.2), dpi=140)
            if base_a:
                ax.plot(main_df.index, series_a / base_a * 100, color="#1e3a5f", linewidth=1.1,
                        label="數列A（指數化，起點=100）")
            if base_b:
                ax.plot(main_df.index, series_b / base_b * 100, color="#a6742a", linewidth=1.1,
                        label="數列B（指數化，起點=100）")
        elif mode == "value_spread":
            series_a, _ = _resolve_source(sources["a"], main_df)
            series_b, _ = _resolve_source(sources["b"], main_df)
            series_a, series_b = series_a.reindex(main_df.index), series_b.reindex(main_df.index)
            fig, ax = plt.subplots(figsize=(7.6, 3.2), dpi=140)
            ax.plot(main_df.index, series_a, color="#1e3a5f", linewidth=1.1, label="數列A")
            ax.plot(main_df.index, series_b, color="#a6742a", linewidth=1.1, label="數列B")
        elif mode == "rolling_stat":
            series, _ = _resolve_source(sources["series"], main_df)
            series = series.reindex(main_df.index)
            med = series.rolling(window, min_periods=window).median() if window else None
            fig, ax = plt.subplots(figsize=(7.6, 3.2), dpi=140)
            ax.plot(main_df.index, series, color="#1e3a5f", linewidth=1.1, label="原始數列")
            if med is not None:
                ax.plot(main_df.index, med, color="#a6742a", linewidth=1.1, label=f"{window}日滾動中位數")
        else:
            return None
    except Exception:
        return None

    ax.legend(fontsize=8, loc="upper left", frameon=False)
    ax.tick_params(labelsize=8)
    ax.set_title(f"{label}：原始資料走勢", fontsize=10)
    ax.spines["top"].set_visible(False)
    fig.tight_layout()
    return fva.fig_to_base64(fig)


