# AUTOGENERATED! DO NOT EDIT! File to edit: nbs/03_preprocessing.ipynb (unless otherwise specified).

__all__ = ['BaseProcessor', 'display_processor_info', 'CopyPreProcessor', 'FeatureSelectionPreProcessor',
           'TargetSelectionPreProcessor', 'GroupStatsPreProcessor', 'TalibFeatureGenerator', 'KatsuFeatureGenerator',
           'AwesomePreProcessor']

# Cell
import os
import time
import numpy as np
import pandas as pd
import datetime as dt
from copy import deepcopy
from tqdm.auto import tqdm
from functools import wraps, partial
from typing import Union, List, Tuple
from multiprocessing import Pool
from typeguard import typechecked
from abc import ABC, abstractmethod
from rich import print as rich_print

from .numerframe import NumerFrame, create_numerframe

try:
    from talib import abstract as tab
except ImportError:
    print("WARNING: TA-Lib is not installed for this environment. If you are using TA-Lib check https://mrjbq7.github.io/ta-lib/install.html for instructions on installation.")

# Ignore Pandas SettingWithCopyWarning
pd.options.mode.chained_assignment = None

# Cell
class BaseProcessor(ABC):
    """ Common functionality for preprocessors and postprocessors. """
    def __init__(self):
        ...

    @abstractmethod
    def transform(self, dataf: Union[pd.DataFrame, NumerFrame], *args, **kwargs) -> NumerFrame:
        ...

    def __call__(self, dataf: Union[pd.DataFrame, NumerFrame], *args, **kwargs) -> NumerFrame:
        return self.transform(dataf=dataf, *args, **kwargs)

# Cell
def display_processor_info(func):
    """ Fancy console output for data processing. """
    @wraps(func)
    def wrapper(*args, **kwargs):
        tic = dt.datetime.now()
        result = func(*args, **kwargs)
        time_taken = str(dt.datetime.now() - tic)
        class_name = func.__qualname__.split('.')[0]
        rich_print(f":white_check_mark: Finished step [bold]{class_name}[/bold]. Output shape={result.shape}. Time taken for step: [blue]{time_taken}[/blue]. :white_check_mark:")
        return result
    return wrapper

# Cell
@typechecked
class CopyPreProcessor(BaseProcessor):
    """Copy DataFrame to avoid manipulation of original DataFrame. """
    def __init__(self):
        super().__init__()

    @display_processor_info
    def transform(self, dataf: Union[pd.DataFrame, NumerFrame]) -> NumerFrame:
        return NumerFrame(dataf.copy())

# Cell
@typechecked
class FeatureSelectionPreProcessor(BaseProcessor):
    """
    Keep only features given + all target, predictions and aux columns.
    """
    def __init__(self, feature_cols: Union[str, list]):
        super().__init__()
        self.feature_cols = feature_cols

    @display_processor_info
    def transform(self, dataf: NumerFrame) -> NumerFrame:
        keep_cols = self.feature_cols + dataf.target_cols + dataf.prediction_cols + dataf.aux_cols
        dataf = dataf.loc[:, keep_cols]
        return NumerFrame(dataf)

# Cell
@typechecked
class TargetSelectionPreProcessor(BaseProcessor):
    """
    Keep only features given + all target, predictions and aux columns.
    """
    def __init__(self, target_cols: Union[str, list]):
        super().__init__()
        self.target_cols = target_cols

    @display_processor_info
    def transform(self, dataf: NumerFrame) -> NumerFrame:
        keep_cols = self.target_cols + dataf.feature_cols + dataf.prediction_cols + dataf.aux_cols
        dataf = dataf.loc[:, keep_cols]
        return NumerFrame(dataf)

# Cell
class GroupStatsPreProcessor(BaseProcessor):
    """
    WARNING: Only supported for Version 1 (legacy) data. \n
    Calculate group statistics for all data groups. \n
    | :param groups: Groups to create features for. All groups by default.
    """
    def __init__(self, groups: list = None):
        super().__init__()
        self.all_groups = ["intelligence", "wisdom", "charisma",
                           "dexterity", "strength", "constitution"]
        self.group_names = groups if groups else self.all_groups

    @display_processor_info
    def transform(self, dataf: NumerFrame, *args, **kwargs) -> NumerFrame:
        """ Check validity and add group features. """
        self._check_data_validity(dataf=dataf)
        dataf = dataf.pipe(self._add_group_features)
        return NumerFrame(dataf)

    def _add_group_features(self, dataf: pd.DataFrame) -> pd.DataFrame:
        """ Mean, standard deviation and skew for each group. """
        for group in self.group_names:
            cols = [col for col in dataf.columns if group in col]
            dataf[f"feature_{group}_mean"] = dataf[cols].mean(axis=1)
            dataf[f"feature_{group}_std"] = dataf[cols].std(axis=1)
            dataf[f"feature_{group}_skew"] = dataf[cols].skew(axis=1)
        return dataf

    def _check_data_validity(self, dataf: NumerFrame):
        """ Make sure this is only used for version 1 data. """
        assert hasattr(dataf.meta, 'version'), f"Version should be specified for '{self.__class__.__name__}' This Preprocessor will only work on version 1 data."
        assert getattr(dataf.meta, 'version') == 1, f"'{self.__class__.__name__}' only works on version 1 data. Got version: '{getattr(dataf.meta, 'version')}'."

# Cell
class TalibFeatureGenerator(BaseProcessor):
    """
    Generate relevant features available in TA-Lib. \n
    More info: https://mrjbq7.github.io/ta-lib \n
    Input DataFrames for these functions should have the following columns defined:
    ['open', 'high', 'low', 'close', 'volume'] \n
    | Make sure that all values are sorted in chronological order (by ticker). \n
    | :param windows: List of ranges for window features.
    Windows will be applied for all features specified in self.window_features. \n
    | :param ticker_col: Which column to groupby for feature generation.
    """
    def __init__(self, windows: List[int], ticker_col: str = "bloomberg_ticker"):
        super().__init__()
        try:
            import talib
        except ImportError:
            raise ImportError("TA-Lib is not installed and required to use TalibFeatureGenerator. Check https://mrjbq7.github.io/ta-lib/install.html for more info on installation.")

        self.windows = windows
        self.ticker_col = ticker_col
        self.window_features = ["NATR", "ADXR", "AROONOSC", "DX", "MFI",
                                "MINUS_DI", "MINUS_DM", "MOM", "ROCP", "ROCR100",
                                "PLUS_DI", "PLUS_DM", "BETA", "RSI",
                                "ULTOSC", "TRIX", "ADXR", "CCI",
                                "CMO", "WILLR"]
        self.no_window_features = ["AD", "OBV", "APO", "MACD", "PPO"]
        self.hlocv_cols = ['open', 'high', 'low', 'close', 'volume']

    def get_no_window_features(self, dataf: pd.DataFrame):
        for func in tqdm(self.no_window_features, desc="No window features"):
            dataf.loc[:, f"feature_{func}"] = dataf.groupby(self.ticker_col)\
                .apply(lambda x: pd.Series(self._no_window(x, func)).bfill())\
                .values.astype(np.float32)
        return dataf

    def get_window_features(self, dataf: pd.DataFrame):
        for win in tqdm(self.windows, position=0, desc="Window features"):
            for func in tqdm(self.window_features, position=1):
                dataf.loc[:, f"feature_{func}_{win}"] = dataf.groupby(self.ticker_col)\
                    .apply(lambda x: pd.Series(self._window(x, func, win)).bfill())\
                    .values.astype(np.float32)
        return dataf

    def get_all_features(self, dataf: pd.DataFrame) -> pd.DataFrame:
        dataf = self.get_no_window_features(dataf)
        dataf = self.get_window_features(dataf)
        return dataf

    def transform(self, dataf: pd.DataFrame, *args, **kwargs) -> NumerFrame:
        return NumerFrame(self.get_all_features(dataf=dataf))

    def _no_window(self, dataf: pd.DataFrame, func) -> pd.Series:
        inputs = self.__get_inputs(dataf)
        if func in ['MACD']:
            # MACD outputs tuple of 3 elements (value, signal and hist)
            return tab.Function(func)(inputs['close'])[0]
        else:
            return tab.Function(func)(inputs)

    def _window(self, dataf: pd.DataFrame, func, window: int) -> pd.Series:
        inputs = self.__get_inputs(dataf)
        if func in ['ULTOSC']:
            # ULTOSC requires 3 timeperiods as input
            return tab.Function(func)(inputs['high'], inputs['low'], inputs['close'],
                                      timeperiod1=window, timeperiod2=window*2,
                                      timeperiod3=window*4)
        else:
            return tab.Function(func)(inputs, timeperiod=window)

    def __get_inputs(self, dataf: pd.DataFrame) -> dict:
        return {col: dataf[col].values.astype(np.float64) for col in self.hlocv_cols}

# Cell
class KatsuFeatureGenerator(BaseProcessor):
    """
    Effective feature engineering setup based on Katsu's starter notebook.
    Based on source by Katsu1110: https://www.kaggle.com/code1110/numeraisignals-starter-for-beginners

    :param windows: Time interval to apply for window features: \n
    1. Percentage Rate of change \n
    2. Volatility \n
    3. Moving Average gap \n
    :param ticker_col: Columns with tickers to iterate over. \n
    :param close_col: Column name where you have closing price stored.
    """
    def __init__(self, windows: list = [20, 40, 60],
                 ticker_col: str = 'ticker',
                 close_col: str = 'close',
                 num_cores: int = None):
        super().__init__()
        self.windows = windows
        self.ticker_col = ticker_col
        self.close_col = close_col
        self.num_cores = num_cores if num_cores else os.cpu_count()

    @display_processor_info
    def transform(self, dataf: NumerFrame) -> NumerFrame:
        """ Multiprocessing feature engineering. """
        tickers = dataf.loc[:, self.ticker_col].unique().tolist()
        rich_print(f"Feature engineering for {len(tickers)} tickers using {self.num_cores} CPU cores.")
        with Pool(self.num_cores) as p:
            feature_dfs = list(tqdm(p.imap(partial(self.feature_engineering,
                                                   dataf=deepcopy(dataf)), tickers),
                                    total=len(tickers)))
        dataf = pd.concat(feature_dfs)
        return NumerFrame(dataf)

    def feature_engineering(self, ticker: str, dataf: pd.DataFrame) -> pd.DataFrame:
        """ Feature engineering for single ticker. """
        feature_df = dataf.query(f"{self.ticker_col} == '{ticker}'")
        close_series = feature_df.loc[:, 'close']
        for x in self.windows:
            feature_df.loc[:, f"feature_{self.close_col}_ROCP_{x}"] = close_series.pct_change(x)

            feature_df.loc[:, f"feature_{self.close_col}_VOL_{x}"] = (
                    np.log1p(close_series)
                        .pct_change()
                        .rolling(x)
                        .std()
                )

            feature_df.loc[:, f"feature_{self.close_col}_MA_gap_{x}days"] = close_series / close_series.rolling(x).mean()

        feature_df.loc[:, 'feature_RSI'] = self._rsi(close_series, 14)
        macd, macd_signal = self._macd(close_series, 12, 26, 9)
        feature_df.loc[:, 'feature_MACD'], feature_df.loc[:, 'feature_MACD_signal'] = macd, macd_signal
        return feature_df.ffill().bfill()

    @staticmethod
    def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
        """
        See source https://github.com/peerchemist/finta
        and fix https://www.tradingview.com/wiki/Talk:Relative_Strength_Index_(RSI)
        """
        delta = close.diff()
        up, down = delta.copy(), delta.copy()
        up[up < 0] = 0
        down[down > 0] = 0

        _gain = up.ewm(com=(period - 1), min_periods=period).mean()
        _loss = down.abs().ewm(com=(period - 1), min_periods=period).mean()

        RS = _gain / _loss
        return pd.Series(100 - (100 / (1 + RS)))

    def _macd(self, close: pd.Series, span1=12, span2=26, span3=9) -> Tuple[pd.Series, pd.Series]:
        """ Compute MACD and MACD signal. """
        exp1 = self.__ema1(close, span1)
        exp2 = self.__ema1(close, span2)
        macd = 100 * (exp1 - exp2) / exp2
        signal = self.__ema1(macd, span3)
        return macd, signal

    @staticmethod
    def __ema1(series: pd.Series, span: int) -> pd.Series:
        """ Exponential moving average """
        a = 2 / (span + 1)
        return series.ewm(alpha=a).mean()

# Cell
class AwesomePreProcessor(BaseProcessor):
    """ TEMPLATE - Do some awesome preprocessing. """
    def __init__(self, *args, **kwargs):
        super().__init__()

    @display_processor_info
    def transform(self, dataf: NumerFrame, *args, **kwargs) -> NumerFrame:
        # Do processing
        ...
        # Parse all contents of NumerFrame to the next pipeline step
        return NumerFrame(dataf)