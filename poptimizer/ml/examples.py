"""Набор обучающих примеров."""
import copy
from typing import Optional, Tuple

import pandas as pd

from poptimizer.ml import feature

TRAIN_VAL_SPLIT = 0.9


class Examples:
    """Позволяет сформировать набор обучающих примеров и меток к ним.

    Разбить данные на обучающую и валидирующую выборку или получить полный набор данных.
    """

    def __init__(self, tickers: Tuple[str, ...], date: pd.Timestamp, params: tuple):
        """Обучающие примеры состоят из признаков на основе данных для тикеров до указанной даты.

        :param tickers:
            Тикеры, для которых нужно составить обучающие примеры.
        :param date:
            Последняя дата, до которой можно использовать данные.
        :param params:
            Параметры признаков ML-модели.
        """
        self._tickers = tickers
        self._date = date
        self._params = params

        self._test_labels_params = copy.deepcopy(params[0][1])
        self._test_labels_params["days"] = 1
        self._features = [
            getattr(feature, params[0][0])(tickers, date, self._test_labels_params)
        ] + [
            getattr(feature, cls_name)(tickers, date, feat_params)
            for cls_name, feat_params in params
        ]

    @property
    def tickers(self):
        """Используемые тикеры."""
        return self._tickers

    def get_features_names(self) -> list:
        """Название признаков."""
        rez = []
        for feat in self._features[2:]:
            rez.extend(feat.col_names)
        return rez

    def categorical_features(self, params: Optional[tuple] = None) -> list:
        """Массив с указанием номеров признаков с категориальными данными."""
        params = params or self._params
        cat_flag = []
        for feat, (_, feat_param) in zip(self._features[2:], params[1:]):
            cat_flag.extend(feat.is_categorical(feat_param))
        return [n for n, flag in enumerate(cat_flag) if flag]

    def get_params_space(self) -> list:
        """Формирует общее вероятностное пространство модели."""
        return [(feat.name, feat.get_params_space()) for feat in self._features[1:]]

    def get_all(self, params: tuple) -> pd.DataFrame:
        """Получить все обучающие примеры.

        Значение признаков создается в том числе для не используемых признаков.
        """
        data = [self._features[0].get(self._test_labels_params)] + [
            feat.get(feat_params)
            for feat, (_, feat_params) in zip(self._features[1:], params)
        ]
        data = pd.concat(data, axis=1)
        return data

    def train_val_pool_params(
        self, params: Optional[tuple] = None
    ) -> Tuple[dict, dict]:
        """Данные для создание catboost.Pool с обучающими и валидационными примерами.

        Вес у данных обратно пропорционален квадрату СКО - что эквивалентно максимизации функции
        правдоподобия для нормального распределения.
        """
        params = params or self._params
        df = self.get_all(params).dropna(axis=0)
        dates = df.index.get_level_values(0)
        val_start = dates[int(len(dates) * TRAIN_VAL_SPLIT)]
        df_val = df[dates >= val_start]
        label_days = params[0][1]["days"]
        train_end = dates[dates < val_start].unique()[-label_days]
        df_train = df.loc[dates <= train_end]
        train_params = dict(
            data=df_train.iloc[:, 2:],
            label=df_train.iloc[:, 1],
            weight=1 / df_train.iloc[:, 2] ** 2,
            cat_features=self.categorical_features(params),
            feature_names=list(df.columns[2:]),
        )
        val_params = dict(
            data=df_val.iloc[:, 2:],
            label=df_val.iloc[:, 1],
            weight=1 / df_val.iloc[:, 2] ** 2,
            cat_features=self.categorical_features(params),
            feature_names=list(df.columns[2:]),
        )
        return train_params, val_params

    def train_predict_pool_params(self) -> Tuple[dict, dict]:
        """Данные для создание catboost.Pool с примерами для прогноза.

        Вес у данных обратно пропорционален квадрату СКО - что эквивалентно максимизации функции
        правдоподобия для нормального распределения.
        """
        df = self.get_all(self._params)
        dates = df.index.get_level_values(0)
        df_predict = df.loc[dates == self._date]
        predict_params = dict(
            data=df_predict.iloc[:, 2:],
            label=None,
            weight=1 / df_predict.iloc[:, 2] ** 2,
            cat_features=self.categorical_features(),
            feature_names=list(df.columns[2:]),
        )
        df = df.dropna(axis=0)
        train_params = dict(
            data=df.iloc[:, 2:],
            label=df.iloc[:, 1],
            weight=1 / df.iloc[:, 2] ** 2,
            cat_features=self.categorical_features(),
            feature_names=list(df.columns[2:]),
        )
        return train_params, predict_params
