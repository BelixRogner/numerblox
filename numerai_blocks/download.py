# AUTOGENERATED! DO NOT EDIT! File to edit: nbs/01_download.ipynb (unless otherwise specified).

__all__ = ['BaseIO', 'BaseDownloader', 'NumeraiClassicDownloader', 'YahooFinanceDownloader', 'AwesomeCustomDownloader']

# Cell
import os
import glob
import json
import shutil
from rich.tree import Tree
from datetime import datetime
from rich.console import Console
from typeguard import typechecked
from pathlib import Path, PosixPath
from abc import ABC, abstractmethod
from rich import print as rich_print
from numerapi import NumerAPI, SignalsAPI
from dateutil.relativedelta import relativedelta, FR

from google.cloud import storage

# Cell
@typechecked
class BaseIO(ABC):
    """
    Basic functionality for IO like downloading and uploading.
    :param directory_path: Base folder for IO. Will be created if it does not exist.
    """

    def __init__(self, directory_path: str):
        self.dir = Path(directory_path)
        self._create_directory()

    def remove_base_directory(self):
        """Remove directory with all contents."""
        abs_path = self.dir.resolve()
        rich_print(
            f":warning: [red]Deleting directory for '{self.__class__.__name__}[/red]' :warning:\nPath: '{abs_path}'"
        )
        shutil.rmtree(abs_path)

    def download_file_from_gcs(self, bucket_name: str, gcs_path: str):
        """
        Get file from GCS bucket and download to local directory.
        :param gcs_path: Path to file on GCS bucket.
        """
        blob_path = str(self.dir.resolve())
        blob = self._get_gcs_blob(bucket_name=bucket_name, blob_path=blob_path)
        blob.download_to_filename(gcs_path)
        rich_print(
            f":cloud: :page_facing_up: Downloaded GCS object '{gcs_path}' from bucket '{blob.bucket.id}' to local directory '{blob_path}'. :page_facing_up: :cloud:"
        )

    def upload_file_to_gcs(self, bucket_name: str, gcs_path: str, local_path: str):
        """
        Upload file to some GCS bucket.
        :param gcs_path: Path to file on GCS bucket.
        """
        blob = self._get_gcs_blob(bucket_name=bucket_name, blob_path=gcs_path)
        blob.upload_from_filename(local_path)
        rich_print(
            f":cloud: :page_facing_up: Local file '{local_path}' uploaded to '{gcs_path}' in bucket {blob.bucket.id}:page_facing_up: :cloud:"
        )

    def download_directory_from_gcs(self, bucket_name: str, gcs_path: str):
        """
        Copy full directory from GCS bucket to local environment.
        :param gcs_path: Name of directory on GCS bucket.
        """
        blob_path = str(self.dir.resolve())
        blob = self._get_gcs_blob(bucket_name=bucket_name, blob_path=blob_path)
        for gcs_file in glob.glob(gcs_path + "/**", recursive=True):
            if os.path.isfile(gcs_file):
                blob.download_to_filename(blob_path)
        rich_print(
            f":cloud: :folder: Directory '{gcs_path}' from bucket '{blob.bucket.id}' downloaded to '{blob_path}' :folder: :cloud:"
        )

    def upload_directory_to_gcs(self, bucket_name: str, gcs_path: str):
        """
        Upload full base directory to GCS bucket.
        :param gcs_path: Name of directory on GCS bucket.
        """
        blob = self._get_gcs_blob(bucket_name=bucket_name, blob_path=gcs_path)
        for local_path in glob.glob(str(self.dir) + "/**", recursive=True):
            if os.path.isfile(local_path):
                blob.upload_from_filename(local_path)
        rich_print(
            f":cloud: :folder: Directory '{self.dir}' uploaded to '{gcs_path}' in bucket {blob.bucket.id} :folder: :cloud:"
        )

    def _get_gcs_blob(self, bucket_name: str, blob_path: str) -> storage.Blob:
        """Create blob that interacts with Google Cloud Storage (GCS)"""
        client = storage.Client()
        # https://console.cloud.google.com/storage/browser/[bucket_name]
        bucket = client.get_bucket(bucket_name)
        blob = bucket.blob(blob_path)
        return blob

    def _append_folder(self, folder: str) -> Path:
        """
        Return base directory Path appended with 'folder'.
        Create directory if it does not exist.
        """
        dir = Path(self.dir / folder)
        dir.mkdir(parents=True, exist_ok=True)
        return dir

    def _create_directory(self):
        """Create base directory if it does not exist."""
        if not self.dir.is_dir():
            rich_print(
                f"No existing directory found at '[blue]{self.dir}[/blue]'. Creating directory..."
            )
            self.dir.mkdir(parents=True, exist_ok=True)

    @property
    def get_all_files(self) -> list:
        """Return all contents in directory."""
        return list(self.dir.iterdir())

    @property
    def is_empty(self) -> bool:
        """Check if directory is empty."""
        return not bool(self.get_all_files)

# Cell
@typechecked
class BaseDownloader(BaseIO):
    """
    Abstract base class for downloaders.
    :param directory_path: Base folder to download files to.
    """

    def __init__(self, directory_path: str):
        super().__init__(directory_path=directory_path)

    @abstractmethod
    def download_training_data(self, *args, **kwargs):
        """Download all necessary files needed for training."""
        ...

    @abstractmethod
    def download_inference_data(self, *args, **kwargs):
        """Download minimal amount of files needed for weekly inference."""
        ...

    @staticmethod
    def _load_json(file_path: str, verbose=False, *args, **kwargs) -> dict:
        """Load JSON from file and return as dictionary."""
        with open(file_path) as json_file:
            json_data = json.load(json_file, *args, **kwargs)
        if verbose:
            rich_print(json_data)
        return json_data

    def __call__(self, *args, **kwargs):
        """
        The most common use case will be to get weekly inference data. So calling the class itself returns inference data.
        """
        self.download_inference_data(*args, **kwargs)

# Cell
class NumeraiClassicDownloader(BaseDownloader):
    """
    -WARNING- Version 1 (legacy) is deprecated. Only supporting version 2+.
    Downloading from NumerAPI for Numerai Classic data.

    :param directory_path: Base folder to download files to.
    All *args, **kwargs will be passed to NumerAPI initialization.
    """

    def __init__(self, directory_path: str, *args, **kwargs):
        super().__init__(directory_path=directory_path)
        self.napi = NumerAPI(*args, **kwargs)
        self.current_round = self.napi.get_current_round()
        # NumerAPI filenames corresponding to version, class and data type
        self.version_mapping = {
            2: {
                "train": {
                    "int8": [
                        "numerai_training_data_int8.parquet",
                        "numerai_validation_data_int8.parquet"
                    ],
                    "float": [
                        "numerai_training_data.parquet",
                        "numerai_validation_data.parquet"
                    ],
                },
                "inference": {
                    "int8": ["numerai_tournament_data_int8.parquet"],
                    "float": ["numerai_tournament_data.parquet"]
                },
                "live": {
                    "int8": ['numerai_live_data_int8.parquet'],
                    "float": ['numerai_live_data.parquet']
                },
                "example": [
                    "example_predictions.parquet",
                    "example_validation_predictions.parquet",
                ],
            },
        }

    def download_training_data(
        self, subfolder: str = "", version: int = 2, int8: bool = False
    ):
        """
        Get Numerai classic training and validation data.
        :param subfolder: Specify folder to create folder within directory root. Saves in directory root by default.
        :param version: Numerai dataset version (2=super massive dataset (parquet))
        :param int8: Integer version of data
        """
        dir = self._append_folder(subfolder)
        data_type = "int8" if int8 else "float"
        train_val_files = self._get_version_mapping(version)["train"][data_type]
        for file in train_val_files:
            self.download_single_dataset(
                filename=file, dest_path=str(dir.joinpath(file))
            )

    def download_inference_data(
        self,
        subfolder: str = "",
        version: int = 2,
        int8: bool = False,
        round_num: int = None,
    ):
        """
        Get Numerai classic inference data.
        :param subfolder: Specify folder to create folder within directory root. Saves in directory root by default.
        :param version: Numerai dataset version (2=super massive dataset (parquet))
        :param int8: Integer version of data
        :param round_num: Numerai tournament round number. Downloads latest round by default.
        """
        dir = self._append_folder(subfolder)
        data_type = "int8" if int8 else "float"
        inference_files = self._get_version_mapping(version)["inference"][data_type]
        for file in inference_files:
            self.download_single_dataset(
                filename=file, dest_path=str(dir.joinpath(file)), round_num=round_num
            )

    def download_single_dataset(
        self, filename: str, dest_path: str, round_num: int = None
    ):
        """
        Download one of the available datasets through NumerAPI.

        :param filename: Name as listed in NumerAPI (Check NumerAPI().list_datasets())
        :param dest_path: Full path where file will be saved.
        :param round_num: Numerai tournament round number. Downloads latest round by default.
        """
        assert (
            filename in self.napi.list_datasets()
        ), f"Dataset '{filename}' not available in NumerAPI. Available datasets are {self.napi.list_datasets()}."
        rich_print(
            f":file_folder: [green]Downloading[/green] '{filename}' :file_folder:"
        )
        self.napi.download_dataset(
            filename=filename, dest_path=dest_path, round_num=round_num
        )

    def download_live_data(
            self,
            subfolder: str = "",
            version: int = 2,
            int8: bool = False,
            round_num: int = None
    ):
        """
        Download all live data in specified folder for given version.

        :param subfolder: Specify folder to create folder within directory root. Saves in directory root by default.
        :param version: Numerai dataset version (2=super massive dataset (parquet))
        :param int8: Integer version of data
        :param round_num: Numerai tournament round number. Downloads latest round by default.
        """
        dir = self._append_folder(subfolder)
        data_type = "int8" if int8 else "float"
        live_files = self._get_version_mapping(version)["live"][data_type]
        for file in live_files:
            self.download_single_dataset(
                filename=file, dest_path=str(dir.joinpath(file)), round_num=round_num
            )

    def download_example_data(
        self, subfolder: str = "", version: int = 2, round_num: int = None
    ):
        """
        Download all example prediction data in specified folder for given version.

        :param subfolder: Specify folder to create folder within directory root. Saves in directory root by default.
        :param version: Numerai dataset version (2=super massive dataset (parquet))
        :param round_num: Numerai tournament round number. Downloads latest round by default.
        """
        dir = self._append_folder(subfolder)
        example_files = self._get_version_mapping(version)["example"]
        for file in example_files:
            self.download_single_dataset(
                filename=file, dest_path=str(dir.joinpath(file)), round_num=round_num
            )

    def get_classic_features(self, subfolder: str = "", *args, **kwargs) -> dict:
        """
        Download feature overview (stats and feature sets) through NumerAPI and load.
        :param subfolder: Specify folder to create folder within directory root. Saves in directory root by default.
        *args, **kwargs will be passed to the JSON loader.
        """
        dir = self._append_folder(subfolder)
        filename = "features.json"
        dest_path = str(dir.joinpath(filename))
        self.download_single_dataset(filename=filename, dest_path=dest_path)
        json_data = self._load_json(dest_path, *args, **kwargs)
        return json_data

    def _get_version_mapping(self, version: int) -> dict:
        """Check if version is supported and return file mapping for version."""
        try:
            mapping_dictionary = self.version_mapping[version]
        except KeyError:
            raise NotImplementedError(
                f"Version '{version}' is not available. Available versions are {list(self.version_mapping.keys())}"
            )
        return mapping_dictionary

# Cell
class YahooFinanceDownloader(BaseDownloader):
    """
    Download Yahoo Finance data through opensignals.
    https://github.com/councilofelders/opensignals

    :param directory_path: Base folder to download files to.
    """

    def __init__(self, directory_path: str, *args, **kwargs):
        super().__init__(directory_path=directory_path)
        self.api = SignalsAPI()
        self.universe_url = self.api.TICKER_UNIVERSE_URL

    def download_inference_data(self, *args, **kwargs):
        """(minimal) weekly inference downloading here."""
        last_friday = int(
            str((datetime.now() + relativedelta(weekday=FR(-1))).date()).replace(
                "-", ""
            )
        )
        # yahoo.download_data(self.dir)

    def download_training_data(self, *args, **kwargs):
        """Training dataset downloading here."""
        ...

# Cell
class AwesomeCustomDownloader(BaseDownloader):
    """
    - TEMPLATE -
    Download awesome financial data from who knows where.

    :param directory_path: Base folder to download files to.
    """

    def __init__(self, directory_path: str, *args, **kwargs):
        super().__init__(directory_path=directory_path)

    def download_inference_data(self, *args, **kwargs):
        """(minimal) weekly inference downloading here."""
        ...

    def download_training_data(self, *args, **kwargs):
        """Training + validation dataset downloading here."""
        ...