import joblib
import os
import json
import numpy as np
from sklearn.preprocessing import RobustScaler
from sklearn.feature_selection import VarianceThreshold
from sklearn.decomposition import PCA
from umap import UMAP

from . import GLOBAL_UNSUPERVISED_FILE_NAME
from .raw import DESCRIPTORS_SUBFOLDER, RawLoader
from . import DescriptorBase
from ..utils.matrices import Hdf5, Data

MAX_NA = 0.2

INDIVIDUAL_UNSUPERVISED_FILE_NAME = "individual_unsupervised.h5"

MAX_COMPONENTS = 1024


class NanFilter(object):
    def __init__(self):
        self._name = "nan_filter"

    def fit(self, X):
        max_na = int((1 - MAX_NA) * X.shape[0])
        idxs = []
        for j in range(X.shape[1]):
            c = np.sum(np.isnan(X[:, j]))
            if c > max_na:
                continue
            else:
                idxs += [j]
        self.col_idxs = idxs
        print(
            "Nan filtering, original columns {0}, final columns {1}".format(
                X.shape[1], len(self.col_idxs)
            )
        )

    def transform(self, X):
        return X[:, self.col_idxs]

    def save(self, file_name):
        joblib.dump(self, file_name)

    def load(self, file_name):
        return joblib.load(file_name)


class Scaler(object):
    def __init__(self):
        self._name = "scaler"
        self.abs_limit = 10
        self.skip = False

    def set_skip(self):
        self.skip = True

    def fit(self, X):
        if self.skip:
            return
        self.scaler = RobustScaler()
        self.scaler.fit(X)

    def transform(self, X):
        if self.skip:
            return X
        X = self.scaler.transform(X)
        X = np.clip(X, -self.abs_limit, self.abs_limit)
        return X

    def save(self, file_name):
        joblib.dump(self, file_name)

    def load(self, file_name):
        return joblib.load(file_name)


class Imputer(object):
    def __init__(self):
        self._name = "imputer"
        self._fallback = 0

    def fit(self, X):
        ms = []
        for j in range(X.shape[1]):
            vals = X[:, j]
            mask = ~np.isnan(vals)
            vals = vals[mask]
            if len(vals) == 0:
                m = self._fallback
            else:
                m = np.median(vals)
            ms += [m]
        self.impute_values = np.array(ms)

    def transform(self, X):
        for j in range(X.shape[1]):
            mask = np.isnan(X[:, j])
            X[mask, j] = self.impute_values[j]
        return X

    def save(self, file_name):
        joblib.dump(self, file_name)

    def load(self, file_name):
        return joblib.load(file_name)


class VarianceFilter(object):
    def __init__(self):
        self._name = "variance_filter"

    def fit(self, X):
        self.sel = VarianceThreshold()
        self.sel.fit(X)

    def transform(self, X):
        return self.sel.transform(X)

    def save(self, file_name):
        joblib.dump(self, file_name)

    def load(self, file_name):
        return joblib.load(file_name)


class Pca(object):
    def __init__(self):
        self._name = "pca"

    def fit(self, X):
        n_components = np.min([MAX_COMPONENTS, X.shape[0], X.shape[1]])
        # self.pca = PCA(n_components=n_components, whiten=True)
        # self.pca.fit(X)
        self.pca = None

    def transform(self, X):
        return X
        return self.pca.transform(X)

    def save(self, file_name):
        joblib.dump(self, file_name)

    def load(self, file_name):
        return joblib.load(file_name)


class UnsupervisedUmap(object):
    def __init__(self):
        self._name = "unsupervised_umap"

    def fit(self, X):
        # self.reducer = UMAP(densmap=False)
        # self.reducer.fit(X)
        self.reducer = None

    def transform(self, X):
        return X
        return self.reducer.transform(X)

    def save(self, file_name):
        joblib.dump(self, file_name)

    def load(self, file_name):
        return joblib.load(file_name)


class IndividualUnsupervisedTransformations(DescriptorBase):
    def __init__(self):
        DescriptorBase.__init__(self)
        self.pipeline = [
            (0, -1, NanFilter),
            (1, 0, Imputer),
            (2, 1, VarianceFilter),
            (3, 2, Scaler),
            (4, 3, Pca),
        ]
        self._name = INDIVIDUAL_UNSUPERVISED_FILE_NAME
        self._is_predict = self.is_predict()

    def done_eos_iter(self):
        with open(
            os.path.join(self.path, DESCRIPTORS_SUBFOLDER, "done_eos.json"), "r"
        ) as f:
            data = json.load(f)
        for eos_id in data:
            yield eos_id

    def run(self):
        rl = RawLoader()
        for eos_id in self.done_eos_iter():
            path = os.path.join(self.path, DESCRIPTORS_SUBFOLDER, eos_id)
            if not self._is_predict:
                trained_path = path
            else:
                trained_path = os.path.join(
                    self.trained_path, DESCRIPTORS_SUBFOLDER, eos_id
                )
            data = rl.open(eos_id)
            data = data.load()
            X = {}
            X[-1] = data.values()
            for step in self.pipeline:
                curr, prev = step[0], step[1]
                algo = step[-1]()
                if algo._name == "scaler":
                    if data.is_sparse():
                        print(
                            "Skipping normalization of {0} as it is sparse".format(
                                eos_id
                            )
                        )
                        algo.set_skip()
                if not self._is_predict:
                    algo.fit(X[prev])
                    algo.save(os.path.join(trained_path, algo._name + ".joblib"))
                else:
                    algo = algo.load(os.path.join(trained_path, algo._name + ".joblib"))
                X[curr] = algo.transform(X[prev])
            file_name = os.path.join(
                self.path, DESCRIPTORS_SUBFOLDER, eos_id, self._name
            )
            data._values = X[4]
            Hdf5(file_name).save(data)
            data.save_info(file_name.split(".")[0] + ".json")


class StackedUnsupervisedTransformations(DescriptorBase):
    def __init__(self):
        DescriptorBase.__init__(self)
        self.pipeline = None  # TODO

    def run(self):
        Xs = []
        keys = None
        inputs = None
        for eos_id in self.done_eos_iter():
            file_name = os.path.join(
                self.path,
                DESCRIPTORS_SUBFOLDER,
                eos_id,
                INDIVIDUAL_UNSUPERVISED_FILE_NAME,
            )
            data = Hdf5(file_name).load()
            Xs += [data.values()]
            if keys is None:
                keys = data.keys()
            if inputs is None:
                inputs = data.inputs()
        if not self._is_predict:
            trained_path = os.path.join(self.path, DESCRIPTORS_SUBFOLDER)
        else:
            trained_path = os.path.join(self.trained_path, DESCRIPTORS_SUBFOLDER)
        X = np.hstack(Xs)
        print("Working on PCA. Shape", X.shape)
        algo = Pca()
        if not self._is_predict:
            algo.fit(X)
            algo.save(os.path.join(trained_path, algo._name + ".joblib"))
        else:
            algo = algo.load(os.path.join(trained_path, algo._name + ".joblib"))
        X = algo.transform(X)
        file_name = os.path.join(
            self.path, DESCRIPTORS_SUBFOLDER, GLOBAL_UNSUPERVISED_FILE_NAME
        )
        data = Data()
        data.set(inputs=inputs, keys=keys, values=X, features=None)
        Hdf5(file_name).save(data)
        data.save_info(file_name.split(".")[0] + ".json")
        print("Working on unsupervised Umap. Shape", X.shape)
        algo = UnsupervisedUmap()
        if not self._is_predict:
            algo.fit(X)
            algo.save(os.path.join(trained_path, algo._name + ".joblib"))
        else:
            algo = algo.load(os.path.join(trained_path, algo._name + ".joblib"))
        try:
            X = algo.transform(X)
            file_name = os.path.join(
                self.path,
                DESCRIPTORS_SUBFOLDER,
                GLOBAL_UNSUPERVISED_FILE_NAME.split(".h5")[0] + "_unsupervised_umap.h5",
            )
            data = Data()
            data.set(inputs=inputs, keys=keys, values=X, features=None)
            Hdf5(file_name).save(data)
        except:
            pass
