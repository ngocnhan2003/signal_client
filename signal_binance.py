import json
import os
from configparser import ConfigParser
from datetime import datetime, timedelta, timezone
from typing import List

import pandas as pd
import requests
from binance import Client
from pandas import DataFrame as df

api_key = os.environ.get("BINANCE_API_KEY")
api_secret = os.environ.get("BINANCE_API_SECRET")
slack_url = os.environ.get("SLACK_URL")

HEADER_MAP = ("open_time", "open", "high", "low", "close", "volume", "close_time", "txn")
VNT = timezone(timedelta(hours=+7), "VNT")

readable_dt = lambda ts: datetime.fromtimestamp(ts // 1000).astimezone(VNT).strftime("%Y-%m-%d %H:%M")
ruler = {
    (False, True): "🟢 BULLISH",
    (True, False): "🔴 BEARISH",
}

class Report:
    def __init__(self, slack_url: str) -> None:
        self.params = {
            "url": slack_url,
            "headers": {
                "Content-Type": "application/json",
            },
        }

    def put_message(self, message) -> bool:
        res = requests.post(
            **self.params,
            data=json.dumps(
                {
                    "text": message,
                }
            ),
        )
        return res.status_code == 200


class Config:
    def __init__(self, config_file: str):
        self.config = ConfigParser()
        self.config.read(config_file)

    def get_symbols(self) -> List[str]:
        return self.config["scanner"]["symbols"].split(",")


class SignalClient:
    def __init__(self, api_key: str, api_secret: str):
        self.client = Client(api_key, api_secret)

    def load_data(
        self,
        symbol: str,
        interval: str = Client.KLINE_INTERVAL_4HOUR,
        limit: int = 104,
    ) -> df:
        klines = self.client.get_historical_klines(
            symbol=symbol,
            interval=interval,
            limit=limit,
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
        MACD = pd.Series(
            EMA_fast - EMA_slow,
            name="MACD",
        )
        MACD_signal = pd.Series(
            MACD.ewm(ignore_na=False, span=signal, adjust=adjust).mean(),
            name="SIGNAL",
        )
        # open_time = ohlc["open_time"].apply(READABLE_DT)
        return pd.concat([ohlc["open_time"], MACD, MACD_signal], axis=1)


if __name__ == "__main__":
    cli = SignalClient(api_key, api_secret)
    cfg = Config("config.ini")
    rpt = Report(slack_url)

    symbols = cfg.get_symbols()

    for symbol in set(symbols):
        ohlc = cli.load_data(symbol=symbol)
        result = cli.MACD(ohlc)
        last_values = tuple((result["MACD"] > result["SIGNAL"]).tail(2))

        if message := ruler.get(last_values):
            open_time = readable_dt(result["open_time"].iat[-1])
            close = ohlc["close"].iat[-1]
            message += f" ❖ {symbol} ${close}\n{open_time}"
            rpt.put_message(message)
            print(message)
