"""K线形态识别信号引擎。

纯 pandas 向量化实现 15 种经典蜡烛图形态识别：
- 单根形态 (5): 锤子线、倒锤子、射击之星、十字星、纺锤线
- 双根形态 (6): 看涨/看跌吞没、看涨/看跌孕线、刺穿线、乌云盖顶
- 三根形态 (4): 晨星、暮星、三白兵、三乌鸦

信号约定: 1=做多, -1=做空, 0=观望
"""

from typing import Dict

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# 向量化辅助函数
# ---------------------------------------------------------------------------


def _body(open_prices: pd.Series, close_prices: pd.Series) -> pd.Series:
    """实体长度（绝对值）。

    Args:
        open_prices: 开盘价序列。
        close_prices: 收盘价序列。

    Returns:
        每根K线的实体长度。
    """
    return (close_prices - open_prices).abs()


def _range(high_prices: pd.Series, low_prices: pd.Series) -> pd.Series:
    """K线振幅（最高 - 最低）。

    Args:
        high_prices: 最高价序列。
        low_prices: 最低价序列。

    Returns:
        每根K线的振幅。
    """
    return high_prices - low_prices


def _upper_shadow(
    open_prices: pd.Series,
    close_prices: pd.Series,
    high_prices: pd.Series,
) -> pd.Series:
    """上影线长度。

    Args:
        open_prices: 开盘价序列。
        close_prices: 收盘价序列。
        high_prices: 最高价序列。

    Returns:
        每根K线的上影线长度。
    """
    return high_prices - pd.concat([open_prices, close_prices], axis=1).max(axis=1)


def _lower_shadow(
    open_prices: pd.Series,
    close_prices: pd.Series,
    low_prices: pd.Series,
) -> pd.Series:
    """下影线长度。

    Args:
        open_prices: 开盘价序列。
        close_prices: 收盘价序列。
        low_prices: 最低价序列。

    Returns:
        每根K线的下影线长度。
    """
    return pd.concat([open_prices, close_prices], axis=1).min(axis=1) - low_prices


# ---------------------------------------------------------------------------
# 信号引擎
# ---------------------------------------------------------------------------


class SignalEngine:
    """K线形态识别信号引擎。

    纯向量化实现，通过看涨/看跌形态评分生成综合交易信号。

    Attributes:
        body_pct: 十字星判定阈值，实体占振幅比例。
        shadow_ratio: 影线与实体的长度比阈值。
    """

    def __init__(self, body_pct: float = 0.1, shadow_ratio: float = 2.0):
        """初始化K线形态信号引擎。

        Args:
            body_pct: 十字星实体/振幅比阈值，默认 0.1。
            shadow_ratio: 影线与实体长度比，默认 2.0。
        """
        self.body_pct = body_pct
        self.shadow_ratio = shadow_ratio

    # -----------------------------------------------------------------------
    # 单根形态
    # -----------------------------------------------------------------------

    def _detect_hammer(
        self,
        open_prices: pd.Series,
        high_prices: pd.Series,
        low_prices: pd.Series,
        close_prices: pd.Series,
    ) -> pd.Series:
        """检测锤子线（Hammer）—— 看涨。

        条件：下影线 >= shadow_ratio * 实体，上影线 < 实体，实体 > 0，振幅 > 0。

        Args:
            open_prices: 开盘价。
            high_prices: 最高价。
            low_prices: 最低价。
            close_prices: 收盘价。

        Returns:
            信号序列：1=检测到锤子线，0=未检测到。
        """
        bd = _body(open_prices, close_prices)
        rng = _range(high_prices, low_prices)
        ls = _lower_shadow(open_prices, close_prices, low_prices)
        us = _upper_shadow(open_prices, close_prices, high_prices)
        cond = (ls >= self.shadow_ratio * bd) & (us < bd) & (bd > 0) & (rng > 0)
        return cond.astype(int)

    def _detect_inverted_hammer(
        self,
        open_prices: pd.Series,
        high_prices: pd.Series,
        low_prices: pd.Series,
        close_prices: pd.Series,
    ) -> pd.Series:
        """检测倒锤子（Inverted Hammer）—— 看涨。

        条件：上影线 >= shadow_ratio * 实体，下影线 < 实体。

        Args:
            open_prices: 开盘价。
            high_prices: 最高价。
            low_prices: 最低价。
            close_prices: 收盘价。

        Returns:
            信号序列：1=检测到倒锤子，0=未检测到。
        """
        bd = _body(open_prices, close_prices)
        us = _upper_shadow(open_prices, close_prices, high_prices)
        ls = _lower_shadow(open_prices, close_prices, low_prices)
        cond = (us >= self.shadow_ratio * bd) & (ls < bd) & (bd > 0)
        return cond.astype(int)

    def _detect_shooting_star(
        self,
        open_prices: pd.Series,
        high_prices: pd.Series,
        low_prices: pd.Series,
        close_prices: pd.Series,
    ) -> pd.Series:
        """检测射击之星（Shooting Star）—— 看跌。

        形态与倒锤子相同，但需出现在上涨趋势之后（前一根收盘 > 前两根收盘）。

        Args:
            open_prices: 开盘价。
            high_prices: 最高价。
            low_prices: 最低价。
            close_prices: 收盘价。

        Returns:
            信号序列：-1=检测到射击之星，0=未检测到。
        """
        bd = _body(open_prices, close_prices)
        us = _upper_shadow(open_prices, close_prices, high_prices)
        ls = _lower_shadow(open_prices, close_prices, low_prices)
        uptrend = close_prices.shift(1) > close_prices.shift(2)
        cond = (us >= self.shadow_ratio * bd) & (ls < bd) & (bd > 0) & uptrend
        return -(cond.astype(int))

    def _detect_doji(
        self,
        open_prices: pd.Series,
        high_prices: pd.Series,
        low_prices: pd.Series,
        close_prices: pd.Series,
    ) -> pd.Series:
        """检测十字星（Doji）—— 中性（信号为0）。

        条件：实体/振幅 < body_pct 且振幅 > 0。

        Args:
            open_prices: 开盘价。
            high_prices: 最高价。
            low_prices: 最低价。
            close_prices: 收盘价。

        Returns:
            信号序列：始终为0（中性形态，不产生方向信号）。
        """
        # 十字星为中性，不贡献方向分数
        return pd.Series(0, index=open_prices.index)

    def _detect_spinning_top(
        self,
        open_prices: pd.Series,
        high_prices: pd.Series,
        low_prices: pd.Series,
        close_prices: pd.Series,
    ) -> pd.Series:
        """检测纺锤线（Spinning Top）—— 中性（信号为0）。

        条件：实体/振幅 < 0.3，上影线 > 实体，下影线 > 实体，且不是十字星。

        Args:
            open_prices: 开盘价。
            high_prices: 最高价。
            low_prices: 最低价。
            close_prices: 收盘价。

        Returns:
            信号序列：始终为0（中性形态，不产生方向信号）。
        """
        # 纺锤线为中性，不贡献方向分数
        return pd.Series(0, index=open_prices.index)

    # -----------------------------------------------------------------------
    # 双根形态
    # -----------------------------------------------------------------------

    def _detect_engulfing(
        self,
        open_prices: pd.Series,
        high_prices: pd.Series,
        low_prices: pd.Series,
        close_prices: pd.Series,
    ) -> pd.Series:
        """检测吞没形态（Engulfing）。

        看涨吞没：前一根看跌，当前看涨，当前实体包含前一根实体。+1
        看跌吞没：前一根看涨，当前看跌，当前实体包含前一根实体。-1

        Args:
            open_prices: 开盘价。
            high_prices: 最高价。
            low_prices: 最低价。
            close_prices: 收盘价。

        Returns:
            信号序列：1=看涨吞没，-1=看跌吞没，0=无。
        """
        previous_open = open_prices.shift(1)
        previous_close = close_prices.shift(1)
        prev_bear = previous_close < previous_open
        prev_bull = previous_close > previous_open
        curr_bull = close_prices > open_prices
        curr_bear = close_prices < open_prices

        bullish = (
            prev_bear
            & curr_bull
            & (close_prices >= previous_open)
            & (open_prices <= previous_close)
        )
        bearish = (
            prev_bull
            & curr_bear
            & (close_prices <= previous_open)
            & (open_prices >= previous_close)
        )

        sig = pd.Series(0, index=open_prices.index)
        sig[bullish] = 1
        sig[bearish] = -1
        return sig

    def _detect_harami(
        self,
        open_prices: pd.Series,
        high_prices: pd.Series,
        low_prices: pd.Series,
        close_prices: pd.Series,
    ) -> pd.Series:
        """检测孕线形态（Harami）。

        看涨孕线：前一根看跌大实体，当前小实体被包含在前一根实体内。+1
        看跌孕线：前一根看涨大实体，当前小实体被包含在前一根实体内。-1

        Args:
            open_prices: 开盘价。
            high_prices: 最高价。
            low_prices: 最低价。
            close_prices: 收盘价。

        Returns:
            信号序列：1=看涨孕线，-1=看跌孕线，0=无。
        """
        bd = _body(open_prices, close_prices)
        previous_open = open_prices.shift(1)
        previous_close = close_prices.shift(1)
        bd1 = _body(previous_open, previous_close)

        prev_bear = previous_close < previous_open
        prev_bull = previous_close > previous_open
        large_prev = bd1 > bd

        # 当前实体完全在前一根实体内
        prev_top = pd.concat([previous_open, previous_close], axis=1).max(axis=1)
        prev_bot = pd.concat([previous_open, previous_close], axis=1).min(axis=1)
        curr_top = pd.concat([open_prices, close_prices], axis=1).max(axis=1)
        curr_bot = pd.concat([open_prices, close_prices], axis=1).min(axis=1)
        contained = (curr_top <= prev_top) & (curr_bot >= prev_bot)

        bullish = prev_bear & large_prev & contained
        bearish = prev_bull & large_prev & contained

        sig = pd.Series(0, index=open_prices.index)
        sig[bullish] = 1
        sig[bearish] = -1
        return sig

    def _detect_piercing_line(
        self,
        open_prices: pd.Series,
        high_prices: pd.Series,
        low_prices: pd.Series,
        close_prices: pd.Series,
    ) -> pd.Series:
        """检测刺穿线（Piercing Line）—— 看涨。

        条件：前一根看跌，当前开盘低于前一根最低价，当前收盘高于前一根实体中点。

        Args:
            open_prices: 开盘价。
            high_prices: 最高价。
            low_prices: 最低价。
            close_prices: 收盘价。

        Returns:
            信号序列：1=检测到刺穿线，0=无。
        """
        previous_open = open_prices.shift(1)
        previous_close = close_prices.shift(1)
        previous_low = low_prices.shift(1)
        prev_bear = previous_close < previous_open
        curr_bull = close_prices > open_prices
        opens_below = open_prices < previous_low
        mid1 = (previous_open + previous_close) / 2
        closes_above_mid = close_prices > mid1

        cond = prev_bear & curr_bull & opens_below & closes_above_mid
        return cond.astype(int)

    def _detect_dark_cloud(
        self,
        open_prices: pd.Series,
        high_prices: pd.Series,
        low_prices: pd.Series,
        close_prices: pd.Series,
    ) -> pd.Series:
        """检测乌云盖顶（Dark Cloud Cover）—— 看跌。

        条件：前一根看涨，当前开盘高于前一根最高价，当前收盘低于前一根实体中点。

        Args:
            open_prices: 开盘价。
            high_prices: 最高价。
            low_prices: 最低价。
            close_prices: 收盘价。

        Returns:
            信号序列：-1=检测到乌云盖顶，0=无。
        """
        previous_open = open_prices.shift(1)
        previous_close = close_prices.shift(1)
        previous_high = high_prices.shift(1)
        prev_bull = previous_close > previous_open
        curr_bear = close_prices < open_prices
        opens_above = open_prices > previous_high
        mid1 = (previous_open + previous_close) / 2
        closes_below_mid = close_prices < mid1

        cond = prev_bull & curr_bear & opens_above & closes_below_mid
        return -(cond.astype(int))

    # -----------------------------------------------------------------------
    # 三根形态
    # -----------------------------------------------------------------------

    def _detect_morning_star(
        self,
        open_prices: pd.Series,
        high_prices: pd.Series,
        low_prices: pd.Series,
        close_prices: pd.Series,
    ) -> pd.Series:
        """检测晨星（Morning Star）—— 看涨。

        条件：
        - Day1 看跌
        - Day2 小实体且向下跳空（Day2最高 < Day1最低）
        - Day3 看涨且收盘高于 Day1 实体中点

        Args:
            open_prices: 开盘价。
            high_prices: 最高价。
            low_prices: 最低价。
            close_prices: 收盘价。

        Returns:
            信号序列：1=检测到晨星，0=无。
        """
        day1_open = open_prices.shift(2)
        day1_close = close_prices.shift(2)
        day2_open = open_prices.shift(1)
        day2_close = close_prices.shift(1)
        day2_high = high_prices.shift(1)
        bd2 = _body(day2_open, day2_close)
        rng2 = _range(high_prices.shift(1), low_prices.shift(1))
        safe_rng2 = rng2.replace(0, np.nan)

        day1_bear = day1_close < day1_open
        day2_small = bd2 / safe_rng2 < 0.3
        day2_gap = day2_high < low_prices.shift(2)  # Day2 high < Day1 low
        day3_bull = close_prices > open_prices
        mid1 = (day1_open + day1_close) / 2
        day3_above_mid = close_prices > mid1

        cond = day1_bear & day2_small & day2_gap & day3_bull & day3_above_mid
        return cond.astype(int).fillna(0).astype(int)

    def _detect_evening_star(
        self,
        open_prices: pd.Series,
        high_prices: pd.Series,
        low_prices: pd.Series,
        close_prices: pd.Series,
    ) -> pd.Series:
        """检测暮星（Evening Star）—— 看跌。

        条件：
        - Day1 看涨
        - Day2 小实体且向上跳空（Day2最低 > Day1最高）
        - Day3 看跌且收盘低于 Day1 实体中点

        Args:
            open_prices: 开盘价。
            high_prices: 最高价。
            low_prices: 最低价。
            close_prices: 收盘价。

        Returns:
            信号序列：-1=检测到暮星，0=无。
        """
        day1_open = open_prices.shift(2)
        day1_close = close_prices.shift(2)
        day2_open = open_prices.shift(1)
        day2_close = close_prices.shift(1)
        day2_low = low_prices.shift(1)
        bd2 = _body(day2_open, day2_close)
        rng2 = _range(high_prices.shift(1), low_prices.shift(1))
        safe_rng2 = rng2.replace(0, np.nan)

        day1_bull = day1_close > day1_open
        day2_small = bd2 / safe_rng2 < 0.3
        day2_gap = day2_low > high_prices.shift(2)  # Day2 low > Day1 high
        day3_bear = close_prices < open_prices
        mid1 = (day1_open + day1_close) / 2
        day3_below_mid = close_prices < mid1

        cond = day1_bull & day2_small & day2_gap & day3_bear & day3_below_mid
        return -(cond.astype(int).fillna(0).astype(int))

    def _detect_three_white_soldiers(
        self,
        open_prices: pd.Series,
        high_prices: pd.Series,
        low_prices: pd.Series,
        close_prices: pd.Series,
    ) -> pd.Series:
        """检测三白兵（Three White Soldiers）—— 看涨。

        条件：连续3根阳线，每根收盘递增，每根开盘在前一根实体内。

        Args:
            open_prices: 开盘价。
            high_prices: 最高价。
            low_prices: 最低价。
            close_prices: 收盘价。

        Returns:
            信号序列：1=检测到三白兵，0=无。
        """
        day1_open = open_prices.shift(2)
        day1_close = close_prices.shift(2)
        day2_open = open_prices.shift(1)
        day2_close = close_prices.shift(1)

        bull1 = day1_close > day1_open
        bull2 = day2_close > day2_open
        bull3 = close_prices > open_prices

        close_up = (day2_close > day1_close) & (close_prices > day2_close)

        # 每根开盘在前一根实体内
        open2_in = (day2_open >= day1_open) & (day2_open <= day1_close)
        open3_in = (open_prices >= day2_open) & (open_prices <= day2_close)

        cond = bull1 & bull2 & bull3 & close_up & open2_in & open3_in
        return cond.astype(int).fillna(0).astype(int)

    def _detect_three_black_crows(
        self,
        open_prices: pd.Series,
        high_prices: pd.Series,
        low_prices: pd.Series,
        close_prices: pd.Series,
    ) -> pd.Series:
        """检测三乌鸦（Three Black Crows）—— 看跌。

        条件：连续3根阴线，每根收盘递减，每根开盘在前一根实体内。

        Args:
            open_prices: 开盘价。
            high_prices: 最高价。
            low_prices: 最低价。
            close_prices: 收盘价。

        Returns:
            信号序列：-1=检测到三乌鸦，0=无。
        """
        day1_open = open_prices.shift(2)
        day1_close = close_prices.shift(2)
        day2_open = open_prices.shift(1)
        day2_close = close_prices.shift(1)

        bear1 = day1_close < day1_open
        bear2 = day2_close < day2_open
        bear3 = close_prices < open_prices

        close_dn = (day2_close < day1_close) & (close_prices < day2_close)

        # 每根开盘在前一根实体内（阴线实体：open在上，close在下）
        open2_in = (day2_open <= day1_open) & (day2_open >= day1_close)
        open3_in = (open_prices <= day2_open) & (open_prices >= day2_close)

        cond = bear1 & bear2 & bear3 & close_dn & open2_in & open3_in
        return -(cond.astype(int).fillna(0).astype(int))

    # -----------------------------------------------------------------------
    # 主入口
    # -----------------------------------------------------------------------

    def generate(self, data_map: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]:
        """对每个标的运行全部形态检测，汇总评分生成信号。

        Args:
            data_map: 标的代码到 OHLCV DataFrame 的映射。
                DataFrame 需包含 open/high/low/close 列，index 为 datetime。

        Returns:
            标的代码到信号 Series 的映射（1=做多, -1=做空, 0=观望）。

        Example:
            >>> engine = SignalEngine()
            >>> signals = engine.generate({"BTC-USDT": df})
            >>> signals["BTC-USDT"].value_counts()
        """
        result = {}
        for code, df in data_map.items():
            open_prices = df["open"]
            high_prices = df["high"]
            low_prices = df["low"]
            close_prices = df["close"]

            # 收集所有形态的信号分数
            scores = pd.DataFrame(index=df.index)

            # 单根形态
            scores["hammer"] = self._detect_hammer(
                open_prices, high_prices, low_prices, close_prices
            )
            scores["inv_hammer"] = self._detect_inverted_hammer(
                open_prices, high_prices, low_prices, close_prices
            )
            scores["shooting_star"] = self._detect_shooting_star(
                open_prices, high_prices, low_prices, close_prices
            )
            scores["doji"] = self._detect_doji(
                open_prices, high_prices, low_prices, close_prices
            )
            scores["spinning_top"] = self._detect_spinning_top(
                open_prices, high_prices, low_prices, close_prices
            )

            # 双根形态
            scores["engulfing"] = self._detect_engulfing(
                open_prices, high_prices, low_prices, close_prices
            )
            scores["harami"] = self._detect_harami(
                open_prices, high_prices, low_prices, close_prices
            )
            scores["piercing"] = self._detect_piercing_line(
                open_prices, high_prices, low_prices, close_prices
            )
            scores["dark_cloud"] = self._detect_dark_cloud(
                open_prices, high_prices, low_prices, close_prices
            )

            # 三根形态
            scores["morning_star"] = self._detect_morning_star(
                open_prices, high_prices, low_prices, close_prices
            )
            scores["evening_star"] = self._detect_evening_star(
                open_prices, high_prices, low_prices, close_prices
            )
            scores["three_white"] = self._detect_three_white_soldiers(
                open_prices, high_prices, low_prices, close_prices
            )
            scores["three_black"] = self._detect_three_black_crows(
                open_prices, high_prices, low_prices, close_prices
            )

            total = scores.sum(axis=1)
            result[code] = pd.Series(
                np.sign(total).astype(int), index=df.index, name="signal"
            )
        return result


# ---------------------------------------------------------------------------
# 数据获取
# ---------------------------------------------------------------------------


def _fetch_okx(inst_id: str, bar: str = "1D", limit: int = 300) -> pd.DataFrame:
    """从 OKX 获取K线数据。

    Args:
        inst_id: 交易对，如 "BTC-USDT"。
        bar: K线周期，默认 "1D"。
        limit: 获取数量，默认 300。

    Returns:
        包含 open/high/low/close/volume 列的 DataFrame，index 为 datetime。

    Raises:
        KeyError: 当 API 返回格式异常时。
    """
    import requests

    resp = requests.get("https://www.okx.com/api/v5/market/candles", params={
        "instId": inst_id, "bar": bar, "limit": str(limit)
    })
    candles = resp.json()["data"]
    columns = ["ts", "open", "high", "low", "close",
               "vol", "volCcy", "volCcyQuote", "confirm"]
    df = pd.DataFrame(reversed(candles), columns=columns)
    df["ts"] = pd.to_datetime(df["ts"].astype("int64"), unit="ms")
    df = df.set_index("ts")
    for col in ["open", "high", "low", "close"]:
        df[col] = df[col].astype(float)
    df["volume"] = df["vol"].astype(float)
    return df


if __name__ == "__main__":
    symbols = ["BTC-USDT", "ETH-USDT", "SOL-USDT"]
    data_map = {}
    for sym in symbols:
        print(f"Fetching {sym} ...")
        data_map[sym] = _fetch_okx(sym)

    engine = SignalEngine()
    signals = engine.generate(data_map)

    for sym in symbols:
        sig = signals[sym]
        buys = (sig == 1).sum()
        sells = (sig == -1).sum()
        holds = (sig == 0).sum()
        print(f"\n{sym} ({len(sig)} bars)")
        print(f"  Long:  {buys}")
        print(f"  Short: {sells}")
        print(f"  Hold:  {holds}")
        # 显示最近的非零信号
        nonzero = sig[sig != 0]
        if len(nonzero) > 0:
            last = nonzero.iloc[-1]
            label = "Long" if last == 1 else "Short"
            print(f"  Latest signal: {label} @ {nonzero.index[-1]:%Y-%m-%d}")
