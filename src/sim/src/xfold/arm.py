"""Arm control: differential IK for the hand's pinch point, plus the fingers.

Targets are given as a pinch-point position and a yaw, because in this cell the
hand always looks straight down; yaw is the direction the jaws close along. IK
is solved on the arm-only model from :mod:`xfold.scene` and the solution is
streamed to the arm's position actuators, so the physical arm follows with a
small, deliberate lag.

The fingers are one tendon actuator. Ramping it rather than stepping it matters:
a snapped-shut 2F-85 bats the garment away before the pads reach it.
"""

from __future__ import annotations

import math

import numpy as np

from .scene import (
    EMPTY_CLOSE_MARGIN,
    HAND_OPEN,
    HAND_SHUT,
    ArmKit,
    Cell,
)
from .shirt import PinchHold
from .sim_loop import smoothstep

IK_SOLVER = "daqp"
IK_DAMPING = 1e-3
POSITION_COST = 1.0
ORIENTATION_COST = 0.5
POSTURE_COST = 1e-3

# Offline solve step: larger than the sim timestep, purely to converge fast.
SETTLE_DT = 0.01
SETTLE_ITERATIONS = 400
IK_ITERS = 1

WAYPOINT_SKIP = 0.03


def tool_rotation(yaw: float) -> np.ndarray:
    """Hand looking down, jaws closing along yaw.

    Columns are the pinch site's own axes: x across the mouth, y along the
    closing direction, z down the tool axis towards the fingertips.
    """
    cos, sin = math.cos(yaw), math.sin(yaw)
    return np.array([[-sin, cos, 0.0], [cos, sin, 0.0], [0.0, 0.0, -1.0]])


def shortest_turn(start: float, end: float) -> float:
    """End angle rewritten so interpolating from start never takes the long way."""
    return start + (end - start + math.pi) % (2.0 * math.pi) - math.pi


def _polar(offset: np.ndarray) -> tuple[float, float]:
    return float(np.linalg.norm(offset)), float(math.atan2(offset[1], offset[0]))


class Arm:
    def __init__(self, cell: Cell, data, kit: ArmKit | None = None) -> None:
        import mink

        self._mink = mink
        self.cell = cell
        self.data = data
        self.kit = kit or cell.picker
        self.configuration = mink.Configuration(self.kit.ik_model)
        self.frame_task = mink.FrameTask(
            self.kit.pinch_site_name,
            "site",
            position_cost=POSITION_COST,
            orientation_cost=ORIENTATION_COST,
            lm_damping=1e-2,
        )
        self.posture_task = mink.PostureTask(self.kit.ik_model, cost=POSTURE_COST)
        self.posture_task.set_target(self.kit.seed_q)
        self.configuration.update(self.kit.seed_q)
        self.target_pos = self.solved_pinch_position()
        self.target_yaw = 0.0
        self.cloth = PinchHold(cell.model, data)

    # --- state --------------------------------------------------------------

    def solved_pinch_position(self) -> np.ndarray:
        """Where IK thinks the pinch point is."""
        transform = self.configuration.get_transform_frame_to_world(
            self.kit.pinch_site_name, "site"
        )
        return np.asarray(transform.translation(), dtype=float)

    def pinch_position(self) -> np.ndarray:
        """Where the pinch point actually is in the simulation."""
        return self.data.site_xpos[self.kit.pinch_site].copy()

    @property
    def grip_command(self) -> float:
        return float(self.data.ctrl[self.kit.hand_actuator])

    @property
    def holding(self) -> bool:
        """True when the fingers stopped short of an empty close.

        The same check a real cell makes: the gripper reports finger position, so
        jaws that never reached the end of their travel have something in them.
        """
        if self.cloth.active:
            return True
        driver = float(self.data.qpos[self.kit.hand_qposadr])
        return (
            self.grip_command > 0.7 * HAND_SHUT
            and driver < self.kit.empty_close - EMPTY_CLOSE_MARGIN
        )

    # --- fingers ------------------------------------------------------------

    def set_grip(self, value: float) -> None:
        self.data.ctrl[self.kit.hand_actuator] = value

    def grip(
        self,
        loop,
        value: float,
        seconds: float = 0.7,
        settle: float = 0.3,
        hold=(),
    ) -> bool:
        """Ease the fingers to a command and give them time to seat."""
        start = self.grip_command
        steps = loop.steps_for(seconds)
        for index in range(steps):
            self.set_grip(start + (value - start) * smoothstep((index + 1) / steps))
            self._solve(self.target_pos, self.target_yaw, loop.model.opt.timestep)
            self.write_ctrl(hold)
            if not loop.step():
                return False
        return self.track(loop, settle, hold) if settle > 0 else loop.running

    def close_hand(self, loop, seconds: float = 0.8, hold=()) -> bool:
        self.cloth.grab(self.pinch_position())
        return self.grip(loop, HAND_SHUT, seconds, settle=0.4, hold=hold)

    def open_hand(self, loop, seconds: float = 0.5, hold=()) -> bool:
        self.cloth.release()
        return self.grip(loop, HAND_OPEN, seconds, settle=0.2, hold=hold)

    # --- motion -------------------------------------------------------------

    def sync(self) -> None:
        """Copy the simulated arm into the IK model so the next move starts here.

        Without this, a stale solution commands a joint leap and the stiff
        UR5e actuators whip the arm through whatever is in the way.
        """
        self.configuration.update(self.data.qpos[self.kit.qposadr])
        self.target_pos = self.solved_pinch_position()

    def park(self, position, yaw: float = 0.0, grip: float = HAND_OPEN) -> None:
        """Solve for a pose and place the arm there without simulating."""
        self.configuration.update(self.kit.seed_q)
        position = np.asarray(position, dtype=float)
        for _ in range(SETTLE_ITERATIONS):
            self._solve(position, yaw, SETTLE_DT)
        self.data.qpos[self.kit.qposadr] = self.configuration.q
        self.data.qvel[self.kit.qposadr] = 0.0
        self.set_grip(grip)
        self.write_ctrl()

    def move(
        self,
        loop,
        position,
        yaw: float,
        seconds: float,
        settle: float = 0.25,
        hold=(),
    ) -> bool:
        """Sweep the pinch point to a pose along an eased straight line."""
        self.sync()
        start_pos = self.target_pos.copy()
        start_yaw = self.target_yaw
        end_pos = np.asarray(position, dtype=float)
        end_yaw = shortest_turn(start_yaw, yaw)

        steps = loop.steps_for(seconds)
        for index in range(steps):
            blend = smoothstep((index + 1) / steps)
            pose = start_pos + (end_pos - start_pos) * blend
            heading = start_yaw + (end_yaw - start_yaw) * blend
            for _ in range(IK_ITERS):
                self._solve(pose, heading, SETTLE_DT)
            self.write_ctrl(hold)
            if not loop.step():
                return False
        return self.track(loop, settle, hold) if settle > 0 else loop.running

    def follow_waypoints(
        self,
        loop,
        points,
        yaw: float,
        seconds: float,
        settle: float = 0.25,
        hold=(),
    ) -> bool:
        """Walk a Cartesian polyline from the live configuration.

        Each segment is an incremental ``move``. Nothing here reseeds IK, so the
        arm stays in the basin it is already in instead of leaping to a seed
        posture on the far side of the press.
        """
        self.sync()
        remaining = []
        here = self.target_pos.copy()
        for point in points:
            point = np.asarray(point, dtype=float)
            if float(np.linalg.norm(point - here)) > WAYPOINT_SKIP:
                remaining.append(point)
                here = point
        if not remaining:
            return self.track(loop, settle, hold) if settle > 0 else loop.running

        lengths = []
        prev = self.target_pos
        for point in remaining:
            lengths.append(max(float(np.linalg.norm(point - prev)), 0.08))
            prev = point
        total = sum(lengths)
        for point, length in zip(remaining, lengths):
            if not self.move(
                loop,
                point,
                yaw,
                max(seconds * length / total, 0.5),
                settle=0.0,
                hold=hold,
            ):
                return False
        return self.track(loop, settle, hold) if settle > 0 else loop.running

    def swing(
        self,
        loop,
        position,
        yaw: float,
        seconds: float,
        settle: float = 0.25,
        hold=(),
    ) -> bool:
        """Transfer between stations along an arc about the arm's own base.

        A straight line from the crate to the press folds the arm over its own
        payload. An arc of roughly constant radius keeps the arm extended.
        Callers that would otherwise cut through the press go via a front
        waypoint first; this method itself always takes the short turn.
        """
        self.sync()
        base = self.kit.base
        start = self.target_pos.copy()
        finish = np.asarray(position, dtype=float)
        start_radius, start_angle = _polar(start[:2] - base)
        end_radius, end_angle = _polar(finish[:2] - base)
        end_angle = shortest_turn(start_angle, end_angle)
        start_yaw, end_yaw = self.target_yaw, shortest_turn(self.target_yaw, yaw)

        steps = loop.steps_for(seconds)
        for index in range(steps):
            blend = smoothstep((index + 1) / steps)
            radius = start_radius + (end_radius - start_radius) * blend
            angle = start_angle + (end_angle - start_angle) * blend
            pose = [
                base[0] + radius * math.cos(angle),
                base[1] + radius * math.sin(angle),
                start[2] + (finish[2] - start[2]) * blend,
            ]
            heading = start_yaw + (end_yaw - start_yaw) * blend
            for _ in range(IK_ITERS):
                self._solve(pose, heading, SETTLE_DT)
            self.write_ctrl(hold)
            if not loop.step():
                return False
        return self.track(loop, settle, hold) if settle > 0 else loop.running

    def track(self, loop, seconds: float, hold=()) -> bool:
        """Hold the current target so the arm can catch up with the solution."""
        for _ in range(loop.steps_for(seconds)):
            for _ in range(IK_ITERS):
                self._solve(self.target_pos, self.target_yaw, SETTLE_DT)
            self.write_ctrl(hold)
            if not loop.step():
                return False
        return loop.running

    def write_ctrl(self, hold=()) -> None:
        self.data.ctrl[self.kit.actuators] = self.configuration.q
        if self.cloth.active:
            self.cloth.pull(self.pinch_position())
        for other in hold:
            other.write_ctrl()

    def _solve(self, position, yaw: float, dt: float) -> None:
        target = self._mink.SE3.from_rotation_and_translation(
            self._mink.SO3.from_matrix(tool_rotation(yaw)),
            np.asarray(position, dtype=float),
        )
        self.frame_task.set_target(target)
        velocity = self._mink.solve_ik(
            self.configuration,
            [self.frame_task, self.posture_task],
            dt,
            IK_SOLVER,
            IK_DAMPING,
        )
        self.configuration.integrate_inplace(velocity, dt)
        self.target_pos = np.asarray(position, dtype=float)
        self.target_yaw = yaw


def hold_together(loop, *arms, seconds: float) -> bool:
    """Keep every pinch spring alive while the cloth hangs or settles."""
    for _ in range(loop.steps_for(seconds)):
        for arm in arms:
            arm.write_ctrl()
        if not loop.step():
            return False
    return loop.running


def move_together(
    loop,
    first: Arm,
    first_pos,
    first_yaw: float,
    second: Arm,
    second_pos,
    second_yaw: float,
    seconds: float,
    settle: float = 0.25,
) -> bool:
    """Walk both pinch points at the same time so a two-handed hold stays taut."""
    first.sync()
    second.sync()
    start_a, start_b = first.target_pos.copy(), second.target_pos.copy()
    end_a = np.asarray(first_pos, dtype=float)
    end_b = np.asarray(second_pos, dtype=float)
    yaw_a0, yaw_b0 = first.target_yaw, second.target_yaw
    yaw_a1 = shortest_turn(yaw_a0, first_yaw)
    yaw_b1 = shortest_turn(yaw_b0, second_yaw)
    steps = loop.steps_for(seconds)
    for index in range(steps):
        blend = smoothstep((index + 1) / steps)
        for _ in range(IK_ITERS):
            first._solve(start_a + (end_a - start_a) * blend, yaw_a0 + (yaw_a1 - yaw_a0) * blend, SETTLE_DT)
            second._solve(start_b + (end_b - start_b) * blend, yaw_b0 + (yaw_b1 - yaw_b0) * blend, SETTLE_DT)
        first.write_ctrl()
        second.write_ctrl()
        if not loop.step():
            return False
    if settle <= 0:
        return loop.running
    return hold_together(loop, first, second, seconds=settle)
