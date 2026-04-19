"""Pure-geometry module for smooth G1-continuous deviation lines around marine obstacles.

Algorithm: 3-arc "tight bump" (LRL Dubins-style curve).

    Arc1(L, sweep theta) -> Arc2(R, sweep 2*theta) -> Arc3(L, sweep theta)

All three arcs have radius = vessel turn_radius_m (the hard safety floor on radius
of curvature). The sweep angle theta is chosen so the curve apex lies exactly at
the required clearance height above the chord:

    theta = acos(1 - h_clear / (2 * R))

where h_clear = perpendicular distance from chord to farthest buffer vertex, plus
clearance_m. This makes the deviation hug the obstacle as tightly as the turn
radius allows -- maximizing coverage area while respecting vessel maneuvering.

Geometry in local coordinates (E' = origin, chord +x, deviation +y):

    Arc 1: CCW, center (0, R), from (0, 0) to (R sin T, R(1 - cos T))
    Arc 2: CW,  center (2R sin T, R(1 - 2 cos T)),
           from end of arc 1 to (3R sin T, R(1 - cos T))
    Arc 3: CCW, center (4R sin T, R), to (4R sin T, 0) = X'

Peak:   (2R sin T, 2R(1 - cos T)) = (X_center, h_clear) at mid-arc-2.
X span: 4R sin T (total along chord).

G1 continuity verified at both arc junctions: tangent directions match by
construction (each junction connects two arcs whose centers are separated by 2R,
externally tangent, with the vessel passing through the tangent point in matching
rotation direction).

Failure modes:
- DeviationTooShort: upstream entry/exit closer to obstacle center than R sin T
  (line not long enough to fit detour). Caller hand-routes.
- DeviationTooTall: h_clear > 3R (obstacle perpendicular extent too large;
  theta would exceed 120 deg making the detour highly aggressive).

No QGIS imports: tuples of floats throughout, so this module is importable without
the QGIS Python environment and unit-testable with plain `python -m unittest`.
"""

from __future__ import annotations

import math
from typing import Callable, Iterable, List, Tuple


class DeviationTooShort(ValueError):
    """Upstream entry/exit too close to obstacle for a detour at this radius."""


class DeviationTooTall(ValueError):
    """Obstacle clearance requirement exceeds 3 * turn_radius_m."""


_XY = Tuple[float, float]

# Cap theta at 120 deg: vessel briefly heads backward relative to the chord
# between arcs 1 and 3. Beyond 120 deg the backward-heading portion is long
# enough that the detour is not practical.
_THETA_MAX_RAD = math.radians(120.0)
# h_clear threshold matching the theta cap: 2R(1 - cos 120 deg) = 3R.
# Exposed as a fraction of R for the raise message.
_H_CLEAR_MAX_FRAC = 2.0 * (1.0 - math.cos(_THETA_MAX_RAD))  # == 3.0


# ------------------------- Vector helpers ---------------------------------

def _sub(a: _XY, b: _XY) -> _XY:
    return (a[0] - b[0], a[1] - b[1])


def _add(a: _XY, b: _XY) -> _XY:
    return (a[0] + b[0], a[1] + b[1])


def _scale(a: _XY, k: float) -> _XY:
    return (a[0] * k, a[1] * k)


def _dot(a: _XY, b: _XY) -> float:
    return a[0] * b[0] + a[1] * b[1]


def _norm(a: _XY) -> float:
    return math.hypot(a[0], a[1])


def _unit(a: _XY) -> _XY:
    n = _norm(a)
    if n < 1e-12:
        raise ValueError("cannot unit-normalize a zero-length vector")
    return (a[0] / n, a[1] / n)


def _perp_ccw(a: _XY) -> _XY:
    """Rotate 90 degrees counterclockwise."""
    return (-a[1], a[0])


# ------------------------- Arc / straight sampling ------------------------

def _sample_arc(
    center: _XY,
    start: _XY,
    end: _XY,
    radius: float,
    direction: str,
    point_ctor: Callable[[float, float], object],
) -> List[object]:
    """Sample points on an arc from start to end around center.

    `direction` is 'ccw' or 'cw'. Returns points EXCLUDING the start,
    INCLUDING the end. Caller prepends start. Angular step min(5 deg,
    2*acos(1 - 0.5/R)) for 0.5m max chord error.
    """
    cx, cy = center
    theta_start = math.atan2(start[1] - cy, start[0] - cx)
    theta_end = math.atan2(end[1] - cy, end[0] - cx)
    delta = theta_end - theta_start
    if direction == "ccw":
        while delta <= 0.0:
            delta += 2.0 * math.pi
    elif direction == "cw":
        while delta >= 0.0:
            delta -= 2.0 * math.pi
    else:
        raise ValueError(f"direction must be 'ccw' or 'cw', got {direction!r}")

    dtheta_cap = min(math.radians(5.0), 2.0 * math.acos(max(-1.0, 1.0 - 0.5 / radius)))
    n_steps = max(2, int(math.ceil(abs(delta) / dtheta_cap)))
    step = delta / n_steps
    pts = []
    for i in range(1, n_steps + 1):
        t = theta_start + i * step
        pts.append(point_ctor(cx + radius * math.cos(t), cy + radius * math.sin(t)))
    return pts


def _sample_straight(
    start: _XY,
    end: _XY,
    step: float,
    point_ctor: Callable[[float, float], object],
) -> List[object]:
    """Sample points on a straight from start to end.

    Returns points EXCLUDING the start, INCLUDING the end. Spacing `step`;
    returns just [end] if the segment is shorter than step.
    """
    length = _norm(_sub(end, start))
    if length < 1e-9:
        return []
    if length <= step:
        return [point_ctor(end[0], end[1])]
    d_hat = _unit(_sub(end, start))
    n_full = int(math.floor(length / step))
    pts = []
    for i in range(1, n_full + 1):
        d = i * step
        pts.append(point_ctor(start[0] + d_hat[0] * d, start[1] + d_hat[1] * d))
    last_d = n_full * step
    if length - last_d > 1e-6:
        pts.append(point_ctor(end[0], end[1]))
    return pts


# ------------------------- Public API -------------------------------------

def build_smooth_deviation(
    entry: _XY,
    exit_: _XY,
    peak: _XY,
    turn_radius_m: float,
    clearance_m: float,
    buffer_polygon_pts: Iterable[_XY],
    point_ctor: Callable[[float, float], object],
) -> List[object]:
    """Build a G1-continuous 3-arc "tight bump" deviation polyline.

    The polyline starts at `entry` and ends at `exit_` (both included exactly).
    The bump apex sits at exactly h_clear above the chord (perpendicular
    distance), where h_clear = max buffer-vertex perpendicular extent plus
    clearance_m. This hugs the obstacle as closely as the turn radius allows.

    Args:
        entry: first point of the connector (upstream's far-entry).
        exit_: last point of the connector (upstream's far-exit).
        peak: any point on the obstacle side of the chord; used only to resolve
            which side of the line to deviate toward (sign of n-hat).
        turn_radius_m: arc radius used for all three arcs. Vessel turn-radius
            floor -- every point on the returned curve has radius of curvature
            equal to turn_radius_m.
        clearance_m: extra perpendicular clearance beyond the obstacle buffer
            boundary.
        buffer_polygon_pts: iterable of (x, y) vertices of the obstacle buffer
            polygon (single polygon or union-cluster vertices). Used to compute
            h_clear. Pass empty iterable for a minimum-amplitude bump.
        point_ctor: callable (x, y) -> point-like object. QgsPointXY in
            production; tuple/namedtuple in tests.

    Returns:
        list of point_ctor(x, y) objects from entry to exit inclusive.

    Raises:
        DeviationTooShort: entry or exit closer to the obstacle center than
            R * sin(theta). Caller must surface to operator.
        DeviationTooTall: h_clear exceeds 3 * turn_radius_m. Obstacle too tall
            for a reasonable detour at this radius.
    """
    R = float(turn_radius_m)
    E = (float(entry[0]), float(entry[1]))
    X = (float(exit_[0]), float(exit_[1]))
    P = (float(peak[0]), float(peak[1]))

    chord = _sub(X, E)
    chord_len = _norm(chord)
    if chord_len < 1e-9:
        raise DeviationTooShort("entry and exit points are coincident")

    OC = _scale(_add(E, X), 0.5)
    t_hat = _unit(chord)
    n_candidate = _perp_ccw(t_hat)
    # `is_ccw_side` tells us whether n_hat is the CCW or CW perpendicular of
    # t_hat in world coordinates. The local-coord geometry below is written
    # assuming n_hat is "up" (CCW of forward), so when n_hat is actually the
    # CW perpendicular we need to flip arc rotation directions.
    is_ccw_side = _dot(_sub(P, OC), n_candidate) >= 0.0
    n_hat = n_candidate if is_ccw_side else _scale(n_candidate, -1.0)
    _dir_outer = "ccw" if is_ccw_side else "cw"   # arcs 1 and 3 (turn toward peak)
    _dir_inner = "cw" if is_ccw_side else "ccw"   # arc 2 (turn back from peak)

    # Required clearance: max perpendicular extent of buffer on deviation side,
    # plus the user-specified safety margin.
    h_clear = float(clearance_m)
    buf_pts = [(float(v[0]), float(v[1])) for v in buffer_polygon_pts]
    if buf_pts:
        h_values = []
        for v in buf_pts:
            perp = _dot(_sub(v, OC), n_hat)
            if perp > 0.0:
                h_values.append(perp)
        if h_values:
            h_clear = max(h_values) + float(clearance_m)

    if h_clear < 1e-6:
        # No obstacle on the deviation side -- nothing to avoid. Return the
        # straight chord. Rare edge case since the caller only invokes this on
        # conflicted lines.
        return [point_ctor(E[0], E[1]), point_ctor(X[0], X[1])]

    if h_clear > _H_CLEAR_MAX_FRAC * R:
        raise DeviationTooTall(
            f"h_clear={h_clear:.0f}m exceeds 3*turn_radius_m={3.0*R:.0f}m; "
            f"obstacle too tall for practical detour at this radius."
        )

    # Solve for theta: peak height = 2R(1 - cos theta) = h_clear
    # -> cos theta = 1 - h_clear / (2R); clamp to valid acos domain.
    cos_theta = max(-1.0, min(1.0, 1.0 - h_clear / (2.0 * R)))
    theta = math.acos(cos_theta)
    sin_theta = math.sin(theta)

    # Detour endpoint positions along chord: E' and X' at +/- 2R sin(theta)
    # from OC. If upstream entry/exit are not yet out that far, the caller's
    # line is too short for this detour.
    half_span = 2.0 * R * sin_theta
    entry_chord_dist = -_dot(_sub(E, OC), t_hat)  # positive if E is before OC along +t_hat
    exit_chord_dist = _dot(_sub(X, OC), t_hat)
    if entry_chord_dist < half_span - 1e-6 or exit_chord_dist < half_span - 1e-6:
        raise DeviationTooShort(
            f"entry/exit only {min(entry_chord_dist, exit_chord_dist):.0f}m "
            f"from obstacle center along chord; need >= {half_span:.0f}m "
            f"(2*R*sin(theta) for theta={math.degrees(theta):.1f}deg)."
        )

    # Local->world helper: local coords have E' at (-half_span, 0), X' at
    # (+half_span, 0), obstacle side toward +y.
    def L2W(x_l: float, y_l: float) -> _XY:
        return (
            OC[0] + x_l * t_hat[0] + y_l * n_hat[0],
            OC[1] + x_l * t_hat[1] + y_l * n_hat[1],
        )

    # Three-arc construction key points.
    E_prime = L2W(-half_span, 0.0)
    arc1_center = L2W(-half_span, R)
    arc1_end = L2W(-half_span + R * sin_theta, R * (1.0 - cos_theta))
    arc2_center = L2W(0.0, R * (1.0 - 2.0 * cos_theta))
    arc2_end = L2W(half_span - R * sin_theta, R * (1.0 - cos_theta))
    arc3_center = L2W(half_span, R)
    X_prime = L2W(half_span, 0.0)

    pts: List[object] = [point_ctor(E[0], E[1])]

    # Prefix: straight from upstream entry to E' (empty if entry == E').
    if _norm(_sub(E_prime, E)) > 1e-6:
        pts.extend(_sample_straight(E, E_prime, 50.0, point_ctor))

    # Arc 1 (outer-side turn), sweep = theta
    pts.extend(_sample_arc(arc1_center, E_prime, arc1_end, R, _dir_outer, point_ctor))

    # Arc 2 (inner-side turn, opposite direction), sweep = 2*theta
    pts.extend(_sample_arc(arc2_center, arc1_end, arc2_end, R, _dir_inner, point_ctor))

    # Arc 3 (outer-side turn), sweep = theta
    pts.extend(_sample_arc(arc3_center, arc2_end, X_prime, R, _dir_outer, point_ctor))

    # Suffix: straight from X' to upstream exit.
    if _norm(_sub(X, X_prime)) > 1e-6:
        pts.extend(_sample_straight(X_prime, X, 50.0, point_ctor))

    # Guarantee endpoints are exactly entry and exit_ bit-for-bit.
    pts[0] = point_ctor(E[0], E[1])
    pts[-1] = point_ctor(X[0], X[1])
    return pts
