"""LoopBrake: stops stuck AI agent runs, with a guaranteed limit on stopping good ones."""

__version__ = "0.2.0"

from loopbrake.brake import Brake, Decision, start  # noqa: E402
from loopbrake.calibration import calibrate  # noqa: E402

__all__ = ["Brake", "Decision", "start", "calibrate", "__version__"]
