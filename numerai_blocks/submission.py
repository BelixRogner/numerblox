# AUTOGENERATED! DO NOT EDIT! File to edit: nbs/09_submission.ipynb (unless otherwise specified).

__all__ = ['BaseSubmittor', 'NumeraiClassicSubmittor', 'NumeraiSignalsSubmittor']

# Cell
import os
import uuid
import numpy as np
import pandas as pd
from typing import Union
from copy import deepcopy
from random import choices
from tqdm.auto import tqdm
from datetime import datetime
from abc import abstractmethod
from typeguard import typechecked
from string import ascii_uppercase
from rich import print as rich_print
from numerapi import NumerAPI, SignalsAPI
from dateutil.relativedelta import relativedelta, FR

from .download import BaseIO
from .key import Key

# Cell
@typechecked
class BaseSubmittor(BaseIO):
    def __init__(self, directory_path: str, api: Union[NumerAPI, SignalsAPI]):
        super().__init__(directory_path)
        self.api = api

    @abstractmethod
    def save_csv(
        self,
        dataf: pd.DataFrame,
        file_name: str,
        cols: Union[str, list],
        *args,
        **kwargs,
    ):
        """
        For Numerai Classic: Save index column + 'cols' (targets) to CSV.
        For Numerai Signals: Save ticker, friday_date, data_type and signal columns to CSV.
        """
        ...

    def upload_predictions(self, file_name: str, model_name: str, *args, **kwargs):
        """
        Upload CSV file to Numerai for given model name.
        :param file_name: File name/path relative to directory_path.
        :param model_name: Lowercase raw model name (For example, 'integration_test').
        """
        full_path = str(self.dir / file_name)
        model_id = self._get_model_id(model_name=model_name)
        api_type = str(self.api.__class__.__name__)
        rich_print(
            f":airplane: {api_type}: Uploading predictions from '{full_path}' for model [bold blue]'{model_name}'[/bold blue] (model_id='{model_id}') :airplane:"
        )
        self.api.upload_predictions(
            file_path=full_path, model_id=model_id, *args, **kwargs
        )
        rich_print(
            f":thumbs_up: {api_type} submission of '{full_path}' for [bold blue]{model_name}[/bold blue] is successful! :thumbs_up:"
        )

    def full_submission(
        self,
        dataf: pd.DataFrame,
        file_name: str,
        model_name: str,
        cols: Union[str, list],
        *args,
        **kwargs,
    ):
        """
        Save DataFrame to csv and upload predictions through API.
        *args, **kwargs are passed to numerapi API.
        """
        self.save_csv(dataf=dataf, file_name=file_name, cols=cols)
        self.upload_predictions(
            file_name=file_name, model_name=model_name, *args, **kwargs
        )

    def combine_csvs(self, csv_paths: list,
                     aux_cols: list,
                     era_col: str = None,
                     pred_col: str = 'prediction') -> pd.DataFrame:
        """
        Read in csv files and combine all predictions with a rank mean.
        Multi-target predictions will be averaged out.
        :param csv_paths: List of full paths to .csv prediction files.
        :param aux_cols: ['id'] for Numerai Classic and
        For example ['ticker', 'last_friday', 'data_type'] for Numerai Signals.
        All aux_cols will be stored as index.
        :param era_col: Column indicating era ('era' or 'last_friday').
        Will be used for Grouping the rank mean if given. Skip groupby if no era_col provided.
        :param pred_col: 'prediction' for Numerai Classic and 'signal' for Numerai Signals.
        """
        all_datafs = [pd.read_csv(path, index_col=aux_cols) for path in tqdm(csv_paths)]
        final_dataf = pd.concat(all_datafs, axis="columns")
        # Remove issue of duplicate columns
        numeric_cols = final_dataf.select_dtypes(include=np.number).columns
        final_dataf.rename({k: str(v) for k, v in zip(numeric_cols, range(len(numeric_cols)))},
                           axis=1,
                           inplace=True)
        # Combine all numeric columns with rank mean
        num_dataf = final_dataf.select_dtypes(include=np.number)
        num_dataf = num_dataf.groupby(era_col) if era_col else num_dataf
        final_dataf[pred_col] = num_dataf.rank(pct=True, method="first").mean(axis=1)
        return final_dataf[[pred_col]]

    def _get_model_id(self, model_name: str) -> str:
        """
        Get ID needed for prediction uploading.
        :param model_name: Raw lowercase model name
        of Numerai model that you have access to.
        """
        return self.get_model_mapping[model_name]

    @property
    def get_model_mapping(self) -> dict:
        """Mapping between raw model names and model IDs."""
        return self.api.get_models()

    def _check_value_range(self, dataf: pd.DataFrame, cols: Union[str, list]):
        """ Check if all predictions are in range (0...1). """
        cols = [cols] if isinstance(cols, str) else cols
        for col in cols:
            if not dataf[col].between(0, 1).all():
                min_val, max_val = dataf[col].min(), dataf[col].max()
                raise ValueError(
                    f"Values must be between 0 and 1. \
Found min value of '{min_val}' and max value of '{max_val}' for column '{col}'."
                )

    def __call__(
            self,
            dataf: pd.DataFrame,
            file_name: str,
            model_name: str,
            cols: Union[str, list],
            *args,
            **kwargs,
    ):
        """
        The most common use case will be to create a CSV and submit it immediately after that.
        full_submission handles this.
        """
        self.full_submission(
            dataf=dataf,
            file_name=file_name,
            model_name=model_name,
            cols=cols,
            *args,
            **kwargs,
        )


# Cell
@typechecked
class NumeraiClassicSubmittor(BaseSubmittor):
    """
    Submit for Numerai Classic.
    :param directory_path: Base directory to save and read prediction files from.
    :param key: Key object (numerai-blocks.key.Key) containing valid credentials for Numerai Classic.
    *args, **kwargs will be passed to NumerAPI initialization.
    """
    def __init__(self, directory_path: str, key: Key, *args, **kwargs):
        api = NumerAPI(public_id=key.pub_id, secret_key=key.secret_key, *args, **kwargs)
        super().__init__(
            directory_path=directory_path, api=api
        )

    def save_csv(
        self,
        dataf: pd.DataFrame,
        file_name: str,
        cols: Union[str, list] = "prediction",
        *args,
        **kwargs,
    ):
        """
        :param dataf: DataFrame which should have at least the following columns:
        1. id (as index column)
        2. cols (for example, 'prediction', ['prediction'] or [ALL_NUMERAI_TARGETS]).
        :param file_name: .csv file path .
        :param cols: All prediction columns.
        For example, 'prediction', ['prediction'] or [ALL_NUMERAI_TARGETS].
        """
        self._check_value_range(dataf=dataf, cols=cols)

        full_path = str(self.dir / file_name)
        rich_print(
            f":page_facing_up: Saving predictions CSV to '{full_path}'. :page_facing_up:"
        )
        dataf.loc[:, cols].to_csv(full_path, *args, **kwargs)

# Cell
@typechecked
class NumeraiSignalsSubmittor(BaseSubmittor):
    """
    Submit for Numerai Signals
    :param directory_path: Base directory to save and read prediction files from.
    :param key: Key object (numerai-blocks.key.Key) containing valid credentials for Numerai Signals.
    *args, **kwargs will be passed to SignalsAPI initialization.
    """

    def __init__(self, directory_path: str, key: Key, *args, **kwargs):
        api = SignalsAPI(
            public_id=key.pub_id, secret_key=key.secret_key, *args, **kwargs
        )
        super().__init__(
            directory_path=directory_path, api=api
        )
        self.supported_ticker_formats = [
            "cusip",
            "sedol",
            "ticker",
            "numerai_ticker",
            "bloomberg_ticker",
        ]

    def save_csv(
        self, dataf: pd.DataFrame, file_name: str, cols: list = None, *args, **kwargs
    ):
        """
        :param dataf: DataFrame which should have at least the following columns:
         1. One of supported ticker formats (cusip, sedol, ticker, numerai_ticker or bloomberg_ticker)
         2. signal (Values between 0 and 1 (exclusive))
         Additional columns for if you include validation data (optional):
         3. friday_date (YYYYMMDD format date indication)
         4. data_type ('val' and 'live' partitions)

         :param file_name: .csv file path.
         :param cols: All cols that should be passed to CSV. Defaults to 2 standard columns.
          ('bloomberg_ticker', 'signal')
        """
        if not cols:
            cols = ["bloomberg_ticker", "signal"]

        self._check_ticker_format(cols=cols)
        self._check_value_range(dataf=dataf, cols="signal")

        full_path = str(self.dir / file_name)
        rich_print(
            f":page_facing_up: Saving Signals predictions CSV to '{full_path}'. :page_facing_up:"
        )
        dataf.loc[:, cols].reset_index(drop=True).to_csv(
            full_path, index=False, *args, **kwargs
        )

    def _check_ticker_format(self, cols: list):
        """ Check for valid ticker format. """
        valid_tickers = set(cols).intersection(set(self.supported_ticker_formats))
        if not valid_tickers:
            raise NotImplementedError(
                f"No supported ticker format in {cols}). \
Supported: '{self.supported_ticker_formats}'"
            )
