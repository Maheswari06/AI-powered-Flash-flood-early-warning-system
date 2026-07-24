"""
ARGUS SDK — Deploy flood early warning AI for any river basin

pip install argus-flood-sdk

Quick start (10 lines):
    from argus import Basin, ARGUSDeployment

    basin = Basin.from_config("my_basin.yaml")
    deployment = ARGUSDeployment(basin)
    deployment.connect_data_sources()
    deployment.train_models()
    deployment.start()
    # ARGUS is now running for your basin

Full documentation: https://docs.argus.foundation/sdk
Basin registry: https://registry.argus.foundation/basins
"""

from .basin import Basin
from .deployment import ARGUSDeployment, TrainingReport, ServiceStatus, DataSourceStatus
from .prediction import PredictionClient
from .alert import AlertClient
from .causal import CausalClient
from .trainers import (
    DataConnectorFactory, XGBoostTrainer, PINNTrainer, CausalDAGBuilder,
    TestResult, TrainingResult, DAGResult, FEATURES,
)

__version__ = "3.0.0"
__author__ = "ARGUS Foundation"
__license__ = "Apache 2.0"

__all__ = [
    "Basin",
    "ARGUSDeployment",
    "TrainingReport",
    "ServiceStatus",
    "DataSourceStatus",
    "PredictionClient",
    "AlertClient",
    "CausalClient",
]
