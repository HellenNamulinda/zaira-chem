import os
import json
import shutil

from .files import SingleFile
from .standardize import Standardize
from .folding import Folds

from . import PARAMETERS_FILE

from ..vars import BASE_DIR
from ..vars import SESSION_FILE

from ..vars import DATA_SUBFOLDER
from ..vars import DESCRIPTORS_SUBFOLDER
from ..vars import MODELS_SUBFOLDER
from ..vars import POOL_SUBFOLDER
from ..vars import LITE_SUBFOLDER

from ..tools.melloddy.pipeline import MelloddyTunerTrainPipeline


class TrainSetup(object):
    def __init__(self, input_file, output_dir, time_budget, parameters):
        self.params = self._load_params(parameters)
        self.input_file = os.path.abspath(input_file)
        self.output_dir = os.path.abspath(output_dir)
        self.time_budget = time_budget

    def _load_params(self, params):
        if params is None:
            return None
        with open(params, "r") as f:
            params = json.load(f)
        return params

    def _save_params(self):
        with open(os.path.join(self.output_dir, DATA_SUBFOLDER, PARAMETERS_FILE), "w") as f:
            json.dump(self.params, f, indent=4)

    def _make_output_dir(self):
        if os.path.exists(self.output_dir):
            shutil.rmtree(self.output_dir)
        os.makedirs(self.output_dir)

    def _open_session(self):
        data = {"output_dir": self.output_dir}
        with open(os.path.join(BASE_DIR, SESSION_FILE), "w") as f:
            json.dump(data, f)

    def _make_subfolder(self, name):
        os.makedirs(os.path.join(self.output_dir, name))

    def _make_subfolders(self):
        self._make_subfolder(DATA_SUBFOLDER)
        self._make_subfolder(DESCRIPTORS_SUBFOLDER)
        self._make_subfolder(MODELS_SUBFOLDER)
        self._make_subfolder(POOL_SUBFOLDER)
        self._make_subfolder(LITE_SUBFOLDER)

    def _normalize_input(self):
        f = SingleFile(self.input_file, self.params)
        f.process()

    def _melloddy_tuner_run(self):
        MelloddyTunerTrainPipeline(os.path.join(self.output_dir, DATA_SUBFOLDER)).run()

    def _standardize(self):
        Standardize(os.path.join(self.output_dir, DATA_SUBFOLDER)).run()

    def _folds(self):
        Folds(os.path.join(self.output_dir, DATA_SUBFOLDER)).run()

    def setup(self):
        self._make_output_dir()
        self._open_session()
        self._make_subfolders()
        self._save_params()
        self._normalize_input()
        self._melloddy_tuner_run()
        self._standardize()
        self._folds()
