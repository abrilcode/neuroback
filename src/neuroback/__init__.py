"""NeuroBack: closed-loop, alpha-phase-locked visual stimulation for OpenBCI.

Research and teaching software. Not a medical device.
"""

__version__ = "2.0.0"

from .closedloop import ClosedLoop, run_offline
from .phase import ARForecast, EcHT, LegacyZeroCrossing

__all__ = ["ClosedLoop", "run_offline", "EcHT", "ARForecast", "LegacyZeroCrossing", "__version__"]
