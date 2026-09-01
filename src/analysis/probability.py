"""Log-odds primitives for the scoring model (SPEC-05 B7).

Three units coexist in the scoring code: points of winrate (`delta2`, or
`winrate - 50`), log-odds (internal composition, additive), and probability
(what's ever shown to the user). This module is the only place that converts
between them — see SPEC-05 §7 "Pièges connus" for why mixing them inline is
the main source of bugs in this kind of refactor.
"""

import math

from ..config_constants import analysis_config


def logit(p: float) -> float:
    """Log-odds of probability p, clamped to avoid +/-inf at the boundaries."""
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def sigmoid(x: float) -> float:
    """Inverse of logit: maps any real to a probability in ]0, 1[.

    Numerically stable for large |x|: naively computing 1/(1+exp(-x)) raises
    OverflowError once exp(-x) overflows a float (x below roughly -710), so
    the two symmetric branches below each only ever call exp() on a
    non-positive argument.
    """
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    z = math.exp(x)
    return z / (1.0 + z)


def winrate_points_to_logit(points: float) -> float:
    """Points of winrate (e.g. delta2, or winrate - 50) -> log-odds contribution.

    Linear approximation valid near p=0.5: d(logit)/dp = 4 at p=0.5,
    so +1 point of winrate (0.01 in probability) ~= +0.04 in log-odds
    (`analysis_config.LOGIT_PER_WINRATE_POINT`).
    """
    return points * analysis_config.LOGIT_PER_WINRATE_POINT
