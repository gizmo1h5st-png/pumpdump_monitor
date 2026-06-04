import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import mplfinance as mpf
from datetime import datetime

os.makedirs("/tmp/snapshots", exist_ok=True)

def klines_to_df(klines):
    df = pd.DataFrame(klines, columns=["t","open","high","low","close","volume","turnover"])
    df = df.astype(float)
    df["date"] = pd.to_datetime(df["t"], unit="ms")
    df.set_index("date", inplace=True)
    return df.iloc[::-1]

def build_snapshot(symbol, klines, trades, settings: dict, pumpdump_info: dict = None) -> str:
    if not klines or len(klines) < 20:
        return ""

    df = klines_to_df(klines)
    
    # --- 1. РАСЧЕТ ДЕЛЬТЫ ОБЪЕМА ---
    # Создаем пустую серию для дельты
    df['delta'] = 0.0
    if trades:
        # Пытаемся распределить сделки по свечам для отрисовки нижней панели
        for t in trades:
            t_time = pd.to_datetime(float(t['time']), unit='ms')
            qty = float(t['size'])
            side = 1 if t['side'] == 'Buy' else -1
            # Находим ближайшую свечу
            idx = df.index.get_indexer([t_time], method='pad')[0]
            if idx != -1:
                df.iloc[idx, df.columns.get_loc('delta')] += (qty * side)

    # --- 2. ПОИСК "ЗОЛОТОЙ ЛИНИИ" (Крупная заявка/сопротивление) ---
    max_vol_idx = df['volume'].idxmax()
    resistance_price = df.loc[max_vol_idx, 'high']
    max_vol_usd = (df['volume'].max() * resistance_price) / 1000 # в тыс $

    # --- 3. НАСТРОЙКА СТИЛЯ ---
    colors = mpf.make_marketcolors(up='#00ff41', down='#ff3131', inherit=True, volume='in', edge='inherit')
    s = mpf.make_mpf_style(base_mpf_style='charles', marketcolors=colors, 
                           facecolor='#0b0e11', edgecolor='#444', gridcolor='#222', 
                           gridstyle='dotted', rc={'font.size': 8, 'axes.labelcolor': 'white', 'xtick.color': 'gray', 'ytick.color': 'gray'})

    # Создаем дополнительные графики (Дельта)
    delta_plot = mpf.make_addplot(df['delta'], panel=2, type='bar', color=['#00ff41' if x > 0 else '#ff3131' for x in df['delta']], width=0.7)

    # Подготовка текста для золотой метки
    title_text = f"{symbol}  {pumpdump_info['change_percent'] if pumpdump_info else ''}%"
    
    # --- 4. ОТРИСОВКА ---
    fig, axlist = mpf.plot(
        df, type='candle', style=s,
        volume=True, addplot=[delta_plot],
        figsize=(12, 8), returnfig=True,
        panel_ratios=(4, 1, 1), # Пропорции панелей
        tight_layout=True,
        datetime_format='%H:%M',
        xrotation=0
    )

    ax_main = axlist[0]
    ax_vol = axlist[2]
    ax_delta = axlist[4]

    # Добавляем Золотую линию (Заявка)
    ax_main.axhline(y=resistance_price, color='#f0b90b', linestyle='-', linewidth=1.5, alpha=0.8)
    
    # Текст над золотой линией (как на скрине)
    ax_main.text(0.5, resistance_price, f"{max_vol_usd:.0f}k$ F {resistance_price:.6f}", 
                 color='black', fontsize=8, fontweight='bold', ha='center', va='center',
                 bbox=dict(boxstyle="round,pad=0.2", facecolor='#f0b90b', edgecolor='#f0b90b'))

    # Добавляем плашку Buy/Sell справа
    if pumpdump_info:
        side_color = '#00ff41' if pumpdump_info['direction'] == 'PUMP' else '#ff3131'
        ax_main.text(1.02, 0.5, pumpdump_info['direction'], transform=ax_main.transAxes,
                     color='white', fontweight='bold', bbox=dict(facecolor=side_color, edgecolor='none', boxstyle='round,pad=0.3'))

    # Надписи ТФ
    ax_main.text(0.95, 0.95, f"TF: {settings.get('timeframe', '5')}m", transform=ax_main.transAxes, color='white', ha='right')
    ax_main.set_title(title_text, color='white', loc='left', fontsize=12, fontweight='bold')

    # Сохранение
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    path = f"/tmp/snapshots/{symbol}_{ts}.png"
    fig.savefig(path, dpi=120, facecolor='#0b0e11')
    plt.close(fig)
    
    return path
