import pandas as pd
from io import StringIO

def ohlcv_sample_data() -> pd.DataFrame:
    """
    Provides a sample OHLCV pandas DataFrame for testing.
    The data is realistic-looking and includes a mix of up and down candles.
    """
    csv_data = """
timestamp,open,high,low,close,volume
1672531200000,16500,16550,16450,16520,100
1672617600000,16520,16600,16510,16580,120
1672704000000,16580,16620,16480,16500,150
1672790400000,16500,16530,16400,16420,110
1672876800000,16420,16700,16410,16680,200
1672963200000,16680,16800,16650,16750,180
1673049600000,16750,16770,16700,16720,90
1673136000000,16720,16750,16680,16700,130
1673222400000,16700,16710,16550,16580,160
1673308800000,16580,16650,16570,16630,140
"""
    df = pd.read_csv(StringIO(csv_data))
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df = df.set_index('timestamp')
    return df
