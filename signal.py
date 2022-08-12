import configparser
import os
from datetime import datetime
from typing import List

import pandas as pd
from binance import Client
from pandas import DataFrame as df

api_key = os.environ.get("BINANCE_API_KEY")
api_secret = os.environ.get("BINANCE_API_SECRET")

HEADER_MAP = ("open_time", "open", "high", "low", "close", "volume", "close_time", "txn")
READABLE_DT = lambda ts: datetime.fromtimestamp(ts // 1000).strftime("%Y-%m-%d %H:%M")
SCHEDULE = {Client.KLINE_INTERVAL_4HOUR: [3, 7, 11, 15, 19, 23]}


class Config:
    def __init__(self, config_file: str):
        self.config = configparser.ConfigParser()
        self.config.read(config_file)

    def get_symbols(self) -> List[str]:
        return self.config["scanner"]["symbols"]


class SignalClient:
    def __init__(self, api_key: str, api_secret: str) -> None:
        self.client = Client(api_key, api_secret)

    def load_data(
        self, symbol: str, interval: str = Client.KLINE_INTERVAL_4HOUR, start_str: str = "26 day ago UTC"
    ) -> df:
        klines = self.client.get_historical_klines(
            symbol=symbol,
            interval=interval,
            start_str=start_str,
        )
        return df.from_dict([{k: v for k, v in zip(HEADER_MAP, item)} for item in klines])

    def MACD(
        self,
        ohlc: df,
        period_fast: int = 12,
        period_slow: int = 26,
        signal: int = 9,
        column: str = "close",
        adjust: bool = True,
    ) -> df:

        EMA_fast = pd.Series(
            ohlc[column].ewm(ignore_na=False, span=period_fast, adjust=adjust).mean(),
            name="EMA_fast",
        )
        EMA_slow = pd.Series(
            ohlc[column].ewm(ignore_na=False, span=period_slow, adjust=adjust).mean(),
            name="EMA_slow",
        )
        MACD = pd.Series(EMA_fast - EMA_slow, name="MACD")
        MACD_signal = pd.Series(MACD.ewm(ignore_na=False, span=signal, adjust=adjust).mean(), name="SIGNAL")
        # open_time = ohlc["open_time"].apply(READABLE_DT)
        return pd.concat([ohlc["open_time"], MACD, MACD_signal], axis=1)


if __name__ == "__main__":
    cli = SignalClient(
        api_key=api_key,
        api_secret=api_secret,
    )
    cfg = Config(
        config_file="config.ini",
    )

    symbols = cfg.get_symbols()
    current = datetime.now()

    for symbol in set(symbols):
        ohlc = cli.load_data(symbol=symbol)
        result = cli.MACD(ohlc)
        if result["open_time"].iat[-1] > current:
            print(f"bullish symbol: {symbol}")
