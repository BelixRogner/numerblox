# AUTOGENERATED! DO NOT EDIT! File to edit: nbs/03_preprocessing.ipynb (unless otherwise specified).

__all__ = ['BaseProcessor', 'display_processor_info', 'CopyPreProcessor', 'FeatureSelectionPreProcessor']

# Cell
import uuid
import time
import numpy as np
import pandas as pd
import datetime as dt
from typing import Union
from functools import wraps
from typeguard import typechecked
from abc import ABC, abstractmethod
from rich import print as rich_print

from .dataset import Dataset, create_dataset

# Cell
@typechecked
class BaseProcessor(ABC):
    """
    New Preprocessors and Postprocessors should inherit from this object
    and implement the transform method.
    """
    def __init__(self):
        ...

    @abstractmethod
    def transform(self, dataset: Dataset, *args, **kwargs) -> Dataset:
        ...

    def __call__(self, dataset: Dataset, *args, **kwargs) -> Dataset:
        return self.transform(dataset=dataset, *args, **kwargs)

# Cell
def display_processor_info(func):
    """ Fancy console output for data processing. """
    @wraps(func)
    def wrapper(*args, **kwargs):
        tic = dt.datetime.now()
        result = func(*args, **kwargs)
        time_taken = str(dt.datetime.now() - tic)
        class_name = func.__qualname__.split('.')[0]
        rich_print(f":white_check_mark: Finished step [bold]{class_name}[/bold]. Output shape={result.dataf.shape}. Time taken for step: [blue]{time_taken}[/blue]. :white_check_mark:")
        return result
    return wrapper

# Cell
@typechecked
class CopyPreProcessor(BaseProcessor):
    """Copy DataFrame to avoid manipulation of original DataFrame. """
    def __init__(self):
        super(CopyPreProcessor, self).__init__()

    @display_processor_info
    def transform(self, dataset: Dataset, *args, **kwargs) -> Dataset:
        return dataset.copy_dataset()

# Cell
@typechecked
class FeatureSelectionPreProcessor(BaseProcessor):
    """
    Keep only features given and remove features not considered.
    Keep all target, predictions and aux columns.
    """
    def __init__(self):
        super(FeatureSelectionPreProcessor, self).__init__()

    @display_processor_info
    def transform(self, dataset: Dataset, feature_cols: Union[str, list], *args, **kwargs) -> Dataset:
        keep_cols = feature_cols + dataset.target_cols + dataset.prediction_cols + dataset.aux_cols
        dataset.dataf = dataset.dataf.loc[:, keep_cols]
        return Dataset(**dataset.__dict__)