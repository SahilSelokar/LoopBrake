"""LoopBrake: stops stuck AI agent runs, with a guaranteed limit on stopping good ones."""

__version__ = "0.5.0"

import logging  # noqa: E402

logging.getLogger("loopbrake").addHandler(logging.NullHandler())  # silent unless the app turns logging on

from loopbrake.brake import Brake, Decision, start  # noqa: E402
from loopbrake.calibration import calibrate  # noqa: E402
from loopbrake.watcher import Stopped, watch  # noqa: E402

__all__ = ["watch", "Stopped", "Brake", "Decision", "start", "calibrate", "__version__"]
