import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import mplfinance as mpf
from datetime import datetime

os.makedirs("/tmp/snapshots", exist_ok=True)

def klines_to_df(klines):
    # Bybit: [t, open, high, low, close, volume, turnover]
    df = pd.DataFrame(klines, columns=["t","open","high","low","close","volume","turnover"])
    df = df.astype(float)
    df["date"] = pd.to_datetime(df["t"], unit="ms")
    df.set_index("date", inplace=True)
    df = df.iloc[::-1]
    
    # Эмуляция дельты на основе свечей (Buyer Volume vs Seller Volume)
    # Используем простую модель: (Close - Low) / (High - Low) * Volume
    df['delta'] = ((df['close'] - df['low']) / (df['high'] - df['low']).replace(0, 1)) * df['volume']
    df['delta'] = df['delta'] - (df['volume'] / 2) # Центрируем
    
    # Кумулятивная дельта (Ликвидация/CVD)
    df['cvd'] = df['delta'].cumsum()
    
    # Открытый интерес (OI) - эмулируем на основе turnover/volume для визуализации уровня интереса
    df['oi'] = df['turnover'].rolling(window=3).mean()
    
    return df

def build_snapshot(symbol, klines, trades, settings: dict, pumpdump_info: dict = None) -> str:
    if not klines or len(klines) < 20:
        return ""

    df = klines_to_df(klines)
    
    # Золотая линия (сопротивление по макс объему)
    max_vol_idx = df['volume'].idxmax()
    res_price = df.loc[max_vol_idx, 'high']
    max_vol_usd = (df['volume'].max() * res_price) / 1000 

    # --- СТИЛЬ ---
    colors = mpf.make_marketcolors(up='#00ff41', down='#ff3131', inherit=True, volume='in', edge='inherit')
    s = mpf.make_mpf_style(
        base_mpf_style='charles', marketcolors=colors, 
        facecolor='#0b0e11', edgecolor='#444', gridcolor='#222', gridstyle='dotted', 
        rc={'font.size': 8, 'axes.labelcolor': 'white', 'xtick.color': '#888', 'ytick.color': '#888'}
    )

    # --- ДОПОЛНИТЕЛЬНЫЕ ПАНЕЛИ ---
    ap = [
        # 1. Дельта объема (полная)
        mpf.make_addplot(df['delta'], panel=2, type='bar', color=['#00ff41' if x > 0 else '#ff3131' for x in df['delta']], width=0.8, ylabel='Delta'),
        # 2. Уровень интереса (OI)
        mpf.make_addplot(df['oi'], panel=3, type='line', color='#f0b90b', width=1, ylabel='OI'),
        # 3. Ликвидации/CVD
        mpf.make_addplot(df['cvd'], panel=4, type='area', color='#3d5afe', alpha=0.3, ylabel='CVD')
    ]

    title_text = f"{symbol}  {pumpdump_info['change_percent'] if pumpdump_info else ''}%"
    
    # --- ОТРИСОВКА ---
    fig, axlist = mpf.plot(
        df, type='candle', style=s,
        volume=True, addplot=ap,
        figsize=(12, 10), returnfig=True,
        panel_ratios=(4, 1, 1, 1, 1), # 5 панелей
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

    # Надписи
    ax_main.text(0.02, 0.95, f"TF: {settings.get('timeframe', '5')}m", transform=ax_main.transAxes, color='gray')
    ax_main.set_title(title_text, color='white', loc='left', fontsize=14, fontweight='bold')

    # Сохранение
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    path = f"/tmp/snapshots/{symbol}_{ts}.png"
    fig.savefig(path, dpi=120, facecolor='#0b0e11', bbox_inches='tight', pad_inches=0.2)
    plt.close(fig)
    
    return path
