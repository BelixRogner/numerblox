# AUTOGENERATED! DO NOT EDIT! File to edit: nbs/05_postprocessing.ipynb (unless otherwise specified).

__all__ = ['MeanEnsembler', 'FeatureNeutralizer', 'FeaturePenalizer', 'AwesomePostProcessor']

# Cell
import scipy
import numpy as np
import pandas as pd
import tensorflow as tf
import scipy.stats as sp
from tqdm.auto import tqdm
from typeguard import typechecked
from rich import print as rich_print
from sklearn.preprocessing import MinMaxScaler

from .preprocessing import BaseProcessor, display_processor_info
from .dataset import Dataset

# Cell
@typechecked
class MeanEnsembler(BaseProcessor):
    """ Take simple mean of multiple cols and store in new col. """
    def __init__(self, cols: list, final_col_name: str):
        super(MeanEnsembler, self).__init__()
        self.cols = cols
        self.final_col_name = final_col_name
        assert final_col_name.startswith("prediction"), f"final_col name should start with 'prediction'. Got {final_col_name}"

    @display_processor_info
    def transform(self, dataset: Dataset, *args, **kwargs) -> Dataset:
        dataset.dataf.loc[:, self.final_col_name] = dataset.dataf.loc[:, self.cols].mean(axis=1)
        rich_print(f":stew: Ensembled [blue]'{self.cols}'[blue] with simple mean and saved in [bold]'{self.final_col_name}'[bold] :stew:")
        return Dataset(**dataset.__dict__)

# Cell
@typechecked
class FeatureNeutralizer(BaseProcessor):
    """ Feature """
    def __init__(self, feature_names: list,
                 pred_name: str = "prediction",
                 proportion=0.5):
        super(FeatureNeutralizer, self).__init__()
        assert 0. <= proportion <= 1., f"'proportion' should be a float in range [0...1]. Got '{proportion}'."
        self.proportion = proportion
        self.feature_names = feature_names
        self.pred_name = pred_name
        self.new_col_name = f"{self.pred_name}_neutralized_{self.proportion}"

    @display_processor_info
    def transform(self, dataset: Dataset, *args, **kwargs) -> Dataset:
        neutralized_preds = dataset.dataf.groupby("era")\
            .apply(lambda x: self.normalize_and_neutralize(x, [self.pred_name], self.feature_names))
        dataset.dataf.loc[:, self.new_col_name] = MinMaxScaler().fit_transform(neutralized_preds)
        rich_print(f":robot: Neutralized [bold blue]'{self.pred_name}'[bold blue] with proportion [bold]'{self.proportion}'[/bold] :robot:")
        rich_print(f"New neutralized column = [bold green]'{self.new_col_name}'[/bold green].")
        return Dataset(**dataset.__dict__)

    def _neutralize(self, df, columns, by):
        scores = df[columns]
        exposures = df[by].values
        scores = scores - self.proportion * exposures.dot(np.linalg.pinv(exposures).dot(scores))
        return scores / scores.std()

    @staticmethod
    def _normalize(dataf: pd.DataFrame):
        normalized_ranks = (dataf.rank(method="first") - 0.5) / len(dataf)
        return sp.norm.ppf(normalized_ranks)

    def normalize_and_neutralize(self, df, columns, by):
        # Convert the scores to a normal distribution
        df[columns] = self._normalize(df[columns])
        df[columns] = self._neutralize(df, columns, by)
        return df[columns]

# Cell
@typechecked
class FeaturePenalizer(BaseProcessor):
    """ Feature penalization with Tensorflow. """
    def __init__(self, model_list: list, max_exposure: float, risky_feature_names: list = None, pred_name: str = "prediction"):
        super(FeaturePenalizer, self).__init__()
        self.model_list = model_list
        assert 0. <= max_exposure <= 1., f"'max_exposure' should be a float in range [0...1]. Got '{max_exposure}'."
        self.max_exposure = max_exposure
        self.risky_feature_names = risky_feature_names
        self.pred_name = pred_name

    @display_processor_info
    def transform(self, dataset: Dataset, *args, **kwargs) -> Dataset:
        risky_feature_names = dataset.feature_cols if not self.risky_feature_names else self.risky_feature_names
        for model_name in self.model_list:
            penalized_data = self.reduce_all_exposures(
                            dataset.dataf,
                            self.pred_name,
                            neutralizers=risky_feature_names,
                            max_exp=self.max_exposure,
                        )
            new_pred_col = f"prediction_{self.pred_name}_{model_name}_FP_{self.max_exposure}"
            dataset.dataf.loc[:, new_pred_col] = penalized_data[self.pred_name]
        return Dataset(**dataset.__dict__)

    def reduce_all_exposures(self, df: pd.DataFrame,
                             column: str = "prediction",
                             neutralizers: list = None,
                             normalize=True,
                             gaussianize=True,
                             era_col: str = "era",
                             max_exp: float = 0.1
                             ):
        if neutralizers is None:
            neutralizers = [x for x in df.columns if x.startswith("feature")]
        neutralized = []

        for era in tqdm(df[era_col].unique()):
            df_era = df[df[era_col] == era]
            scores = df_era.loc[:, column].values
            exposure_values = df_era[neutralizers].values

            if normalize:
                scores2 = []
                for x in scores.T:
                    x = (scipy.stats.rankdata(x, method='ordinal') - .5) / len(x)
                    if gaussianize:
                        x = scipy.stats.norm.ppf(x)
                    scores2.append(x)
                scores = np.array(scores2)[0]

            scores, weights = self.reduce_exposure(scores, exposure_values,
                                              max_exp, len(neutralizers), None)

            scores /= tf.math.reduce_std(scores)
            scores -= tf.reduce_min(scores)
            scores /= tf.reduce_max(scores)
            neutralized.append(scores.numpy())

        predictions = pd.DataFrame(np.concatenate(neutralized),
                                   columns=[column], index=df.index)
        return predictions

    def reduce_exposure(self, prediction, features, max_exp, input_size=50, weights=None):
        model = tf.keras.models.Sequential([
            tf.keras.layers.Input(input_size),
            tf.keras.experimental.LinearModel(use_bias=False),
        ])
        feats = tf.convert_to_tensor(features - 0.5, dtype=tf.float32)
        pred = tf.convert_to_tensor(prediction, dtype=tf.float32)
        if weights is None:
            optimizer = tf.keras.optimizers.Adamax()
            start_exp = self.__exposures(feats, pred[:, None])
            target_exps = tf.clip_by_value(start_exp, -max_exp, max_exp)
            self._train_loop(model, optimizer, feats, pred, target_exps)
        else:
            model.set_weights(weights)
        return pred[:,None] - model(feats), model.get_weights()


    def _train_loop(self, model, optimizer, feats, pred, target_exps):
        for i in range(1000000):
            loss, grads = self.__train_loop_body(model, feats, pred, target_exps)
            optimizer.apply_gradients(zip(grads, model.trainable_variables))
            if loss < 1e-7:
                break

    @tf.function(experimental_relax_shapes=True)
    def __train_loop_body(self, model, feats, pred, target_exps):
        with tf.GradientTape() as tape:
            exps = self.exposures(feats, pred[:, None] - model(feats, training=True))
            loss = tf.reduce_sum(tf.nn.relu(tf.nn.relu(exps) - tf.nn.relu(target_exps)) +
                                 tf.nn.relu(tf.nn.relu(-exps) - tf.nn.relu(-target_exps)))
        return loss, tape.gradient(loss, model.trainable_variables)

    @staticmethod
    @tf.function(experimental_relax_shapes=True, experimental_compile=True)
    def __exposures(x, y):
        x = x - tf.math.reduce_mean(x, axis=0)
        x = x / tf.norm(x, axis=0)
        y = y - tf.math.reduce_mean(y, axis=0)
        y = y / tf.norm(y, axis=0)
        return tf.matmul(x, y, transpose_a=True)

# Cell
@typechecked
class AwesomePostProcessor(BaseProcessor):
    """
    - TEMPLATE -
    Do some awesome postprocessing.
    """
    def __init__(self, *args, **kwargs):
        super(AwesomePostProcessor, self).__init__()

    @display_processor_info
    def transform(self, dataset: Dataset, *args, **kwargs) -> Dataset:
        # Do processing
        ...
        # Add new column for manipulated data (optional)
        new_column_name = "NEW_COLUMN_NAME"
        dataset.dataf.loc[:, f"prediction_{new_column_name}"] = ...
        ...
        # Parse all contents of Dataset to the next pipeline step
        return Dataset(**dataset.__dict__)