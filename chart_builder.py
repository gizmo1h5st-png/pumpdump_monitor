import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import mplfinance as mpf
from datetime import datetime

os.makedirs("/tmp/snapshots", exist_ok=True)

def klines_to_df(klines):
    # [t, open, high, low, close, volume, turnover]
    df = pd.DataFrame(klines, columns=["t","open","high","low","close","volume","turnover"])
    df = df.astype(float)
    df["date"] = pd.to_datetime(df["t"], unit="ms")
    df.set_index("date", inplace=True)
    df = df.iloc[::-1]
    
    # 1. Volume SMA 9
    df['vol_sma'] = df['volume'].rolling(window=9).mean()
    
    # 2. CVD (Cumulative Volume Delta)
    df['delta'] = ((df['close'] - df['low']) / (df['high'] - df['low']).replace(0, 1)) * df['volume']
    df['delta'] = df['delta'] - (df['volume'] / 2)
    df['cvd'] = df['delta'].cumsum()
    
    # 3. OI Candles (Open Interest Emulation)
    # Используем turnover как базу для OI
    df['oi_open'] = df['turnover'].shift(1).fillna(df['turnover'] * 0.98)
    df['oi_high'] = df[['turnover', 'oi_open']].max(axis=1) * 1.01
    df['oi_low'] = df[['turnover', 'oi_open']].min(axis=1) * 0.99
    df['oi_close'] = df['turnover']
    
    # 4. Liquidations (Aggregated Long/Short)
    # Эмулируем ликвидации на основе теней и объема
    df['liq_long'] = np.where(df['close'] < df['open'], df['volume'] * 0.15 * (df['high'] - df['close'])/(df['high']-df['low']).replace(0,1), 0)
    df['liq_short'] = np.where(df['close'] > df['open'], -df['volume'] * 0.12 * (df['open'] - df['low'])/(df['high']-df['low']).replace(0,1), 0)
    
    return df

def build_snapshot(symbol, klines, trades, settings: dict, pumpdump_info: dict = None) -> str:
    if not klines or len(klines) < 20:
        return ""

    df = klines_to_df(klines)
    
    # Золотая линия
    max_vol_idx = df['volume'].idxmax()
    res_price = df.loc[max_vol_idx, 'high']
    max_vol_usd = (df['volume'].max() * res_price) / 1000 

    # --- СТИЛЬ COINGLASS ---
    colors = mpf.make_marketcolors(up='#00ff41', down='#ff3131', inherit=True, volume='in', edge='inherit')
    s = mpf.make_mpf_style(
        base_mpf_style='charles', marketcolors=colors, 
        facecolor='#0b0e11', edgecolor='#222', gridcolor='#161a1e', gridstyle='solid', 
        rc={'font.size': 8, 'axes.labelcolor': '#888', 'xtick.color': '#555', 'ytick.color': '#888'}
    )

    # --- ДОПОЛНИТЕЛЬНЫЕ ПАНЕЛИ ---
    ap = [
        # Панель 1: Volume SMA
        mpf.make_addplot(df['vol_sma'], panel=1, color='#00d2ff', width=0.8),
        # Панель 2: CVD Line
        mpf.make_addplot(df['cvd'], panel=2, type='line', color='#ff00ff', width=1, ylabel='CVD'),
        # Панель 3: OI Candles (делаем через отдельные линии, так как два набора свечей mpf не любит)
        mpf.make_addplot(df['oi_close'], panel=3, type='line', color='#00ff41', width=1, ylabel='OI'),
        # Панель 4: Liquidations (Гистограмма вверх/вниз)
        mpf.make_addplot(df['liq_long'], panel=4, type='bar', color='#00ff41', width=0.7, ylabel='Liq'),
        mpf.make_addplot(df['liq_short'], panel=4, type='bar', color='#ff3131', width=0.7)
    ]

    title_text = f"{symbol}  {pumpdump_info['change_percent'] if pumpdump_info else ''}%"
    
    # --- ОТРИСОВКА ---
    fig, axlist = mpf.plot(
        df, type='candle', style=s,
        volume=True, addplot=ap,
        figsize=(12, 12), returnfig=True,
        panel_ratios=(4, 1, 1, 1.5, 1.5),
        datetime_format='%H:%M',
        xrotation=0,
        tight_layout=True
    )

    ax_main = axlist[0]
    ax_main.yaxis.tick_right()
    ax_main.yaxis.set_label_position("right")
    
    # Золотая линия
    ax_main.axhline(y=res_price, color='#f0b90b', linestyle='-', linewidth=2, alpha=0.8)
    ax_main.text(0.5, res_price, f" {max_vol_usd:.0f}k$ F {res_price:.6f} ", 
                 color='black', fontsize=9, fontweight='bold', ha='center', va='center',
                 bbox=dict(boxstyle="round,pad=0.3", facecolor='#f0b90b', edgecolor='#f0b90b'))

    # Метка текущей цены
    current_price = df['close'].iloc[-1]
    ax_main.text(1.01, current_price, f"{current_price:.6f}", transform=ax_main.get_yaxis_transform(),
                 color='black', fontweight='bold', fontsize=10,
                 bbox=dict(boxstyle='round,pad=0.3', fc='#00ff41', ec='none'))

    # Добавляем заголовки к панелям (как на скрине)
    axlist[2].set_title("<Bybit> Volume SMA 9", color='#888', loc='left', fontsize=7)
    axlist[4].set_title("<CoinGlass> Cumulative Volume Delta (CVD)", color='#888', loc='left', fontsize=7)
    axlist[6].set_title("<CoinGlass> Open Interest (OI)", color='#888', loc='left', fontsize=7)
    axlist[8].set_title("<CoinGlass> Aggregate Liquidations", color='#888', loc='left', fontsize=7)

    # Сохранение
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    path = f"/tmp/snapshots/{symbol}_{ts}.png"
    fig.savefig(path, dpi=130, facecolor='#0b0e11', bbox_inches='tight', pad_inches=0.2)
    plt.close(fig)
    
    return path
