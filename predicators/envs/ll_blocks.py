"""Low-level Blocks domain. The goal is specified by continous states.

This environment IS downward refinable and DOESN'T require any
backtracking (as long as all the blocks can fit comfortably on the
table, which is true here because the block size and number of blocks
are much less than the table dimensions). The simplicity of this
environment makes it a good testbed for predicate invention.
"""

import json
import logging
from pathlib import Path
from typing import ClassVar, Collection, Dict, List, Optional, Sequence, Set, \
    Tuple

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
from gym.spaces import Box
from matplotlib import patches

from predicators import utils
from predicators.envs import BaseEnv
from predicators.settings import CFG
from predicators.structs import Action, Array, GroundAtom, \
    Object, Predicate, State, Type, LowLevelEnvironmentTask


class LowLevelBlocksEnv(BaseEnv):
    """Blocks domain."""
    # Parameters that aren't important enough to need to clog up settings.py
    table_height: ClassVar[float] = 0.2
    # The table x bounds are (1.1, 1.6), but the workspace is smaller.
    # Make it narrow enough that blocks can be only horizontally arranged.
    # Note that these boundaries are for the block positions, and that a
    # block's origin is its center, so the block itself may extend beyond
    # the boundaries while the origin remains in bounds.
    x_lb: ClassVar[float] = 1.325
    x_ub: ClassVar[float] = 1.375
    # The table y bounds are (0.3, 1.2), but the workspace is smaller.
    y_lb: ClassVar[float] = 0.4
    y_ub: ClassVar[float] = 1.1
    pick_z: ClassVar[float] = 0.7
    robot_init_x: ClassVar[float] = (x_lb + x_ub) / 2
    robot_init_y: ClassVar[float] = (y_lb + y_ub) / 2
    robot_init_z: ClassVar[float] = pick_z
    held_tol: ClassVar[float] = 0.5
    pick_tol: ClassVar[float] = 0.0001
    on_tol: ClassVar[float] = 0.01
    collision_padding: ClassVar[float] = 2.0

    def __init__(self, use_gui: bool = True) -> None:
        super().__init__(use_gui)

        # Types
        self._block_type = Type("block", [
            "pose_x", "pose_y", "pose_z", "held", "color_r", "color_g",
            "color_b"
        ])
        self._robot_type = Type("robot",
                                ["pose_x", "pose_y", "pose_z", "fingers"])
        # Predicates
        self._On = Predicate("On", [self._block_type, self._block_type],
                             self._On_holds)
        self._OnTable = Predicate("OnTable", [self._block_type],
                                  self._OnTable_holds)
        self._GripperOpen = Predicate("GripperOpen", [self._robot_type],
                                      self._GripperOpen_holds)
        self._Holding = Predicate("Holding", [self._block_type],
                                  self._Holding_holds)
        self._Clear = Predicate("Clear", [self._block_type], self._Clear_holds)
        # Static objects (always exist no matter the settings).
        self._robot = Object("robby", self._robot_type)
        # Hyperparameters from CFG.
        self._block_size = CFG.blocks_block_size
        self._num_blocks_train = CFG.blocks_num_blocks_train
        self._num_blocks_test = CFG.blocks_num_blocks_test

    @classmethod
    def get_name(cls) -> str:
        return "ll_blocks"

    def simulate(self, state: State, action: Action) -> State:
        assert self.action_space.contains(action.arr)
        x, y, z, fingers = action.arr
        # Infer which transition function to follow
        if fingers < 0.5:
            return self._transition_pick(state, x, y, z)
        if z < self.table_height + self._block_size:
            return self._transition_putontable(state, x, y, z)
        return self._transition_stack(state, x, y, z)

    def _transition_pick(self, state: State, x: float, y: float,
                         z: float) -> State:
        next_state = state.copy()
        # Can only pick if fingers are open
        if not self._GripperOpen_holds(state, [self._robot]):
            return next_state
        block = self._get_block_at_xyz(state, x, y, z)
        if block is None:  # no block at this pose
            return next_state
        # Can only pick if object is clear
        if not self._block_is_clear(block, state):
            return next_state
        # Execute pick
        next_state.set(block, "pose_x", x)
        next_state.set(block, "pose_y", y)
        next_state.set(block, "pose_z", self.pick_z)
        next_state.set(block, "held", 1.0)
        next_state.set(self._robot, "fingers", 0.0)  # close fingers
        if "clear" in self._block_type.feature_names:
            # See BlocksEnvClear
            next_state.set(block, "clear", 0)
            # If block was on top of other block, set other block to clear
            other_block = self._get_highest_block_below(state, x, y, z)
            if other_block is not None and other_block != block:
                next_state.set(other_block, "clear", 1)
        return next_state

    def _transition_putontable(self, state: State, x: float, y: float,
                               z: float) -> State:
        next_state = state.copy()
        # Can only putontable if fingers are closed
        if self._GripperOpen_holds(state, [self._robot]):
            return next_state
        block = self._get_held_block(state)
        assert block is not None
        # Check that table surface is clear at this pose
        poses = [[
            state.get(b, "pose_x"),
            state.get(b, "pose_y"),
            state.get(b, "pose_z")
        ] for b in state if b.is_instance(self._block_type)]
        existing_xys = {(float(p[0]), float(p[1])) for p in poses}
        if not self._table_xy_is_clear(x, y, existing_xys):
            return next_state
        # Execute putontable
        next_state.set(block, "pose_x", x)
        next_state.set(block, "pose_y", y)
        next_state.set(block, "pose_z", z)
        next_state.set(block, "held", 0.0)
        next_state.set(self._robot, "fingers", 1.0)  # open fingers
        if "clear" in self._block_type.feature_names:
            # See BlocksEnvClear
            next_state.set(block, "clear", 1)
        return next_state

    def _transition_stack(self, state: State, x: float, y: float,
                          z: float) -> State:
        next_state = state.copy()
        # Can only stack if fingers are closed
        if self._GripperOpen_holds(state, [self._robot]):
            return next_state
        # Check that both blocks exist
        block = self._get_held_block(state)
        assert block is not None
        other_block = self._get_highest_block_below(state, x, y, z)
        if other_block is None:  # no block to stack onto
            return next_state
        # Can't stack onto yourself!
        if block == other_block:
            return next_state
        # Need block we're stacking onto to be clear
        if not self._block_is_clear(other_block, state):
            return next_state
        # Execute stack by snapping into place
        cur_x = state.get(other_block, "pose_x")
        cur_y = state.get(other_block, "pose_y")
        cur_z = state.get(other_block, "pose_z")
        next_state.set(block, "pose_x", cur_x)
        next_state.set(block, "pose_y", cur_y)
        next_state.set(block, "pose_z", cur_z + self._block_size)
        next_state.set(block, "held", 0.0)
        next_state.set(self._robot, "fingers", 1.0)  # open fingers
        if "clear" in self._block_type.feature_names:
            # See BlocksEnvClear
            next_state.set(block, "clear", 1)
            next_state.set(other_block, "clear", 0)
        return next_state

    def _generate_train_tasks(self) -> List[LowLevelEnvironmentTask]:
        return self._get_tasks(num_tasks=CFG.num_train_tasks,
                               possible_num_blocks=self._num_blocks_train,
                               rng=self._train_rng)

    def _generate_test_tasks(self) -> List[LowLevelEnvironmentTask]:
        return self._get_tasks(num_tasks=CFG.num_test_tasks,
                               possible_num_blocks=self._num_blocks_test,
                               rng=self._test_rng)

    @property
    def predicates(self) -> Set[Predicate]:
        return {
            self._On, self._OnTable, self._GripperOpen, self._Holding,
            self._Clear
        }

    @property
    def goal_predicates(self) -> Set[Predicate]:
        if CFG.blocks_holding_goals:
            return {self._Holding}
        return {self._On, self._OnTable}

    @property
    def types(self) -> Set[Type]:
        return {self._block_type, self._robot_type}

    @property
    def action_space(self) -> Box:
        # dimensions: [x, y, z, fingers]
        lowers = np.array([self.x_lb, self.y_lb, 0.0, 0.0], dtype=np.float32)
        uppers = np.array([self.x_ub, self.y_ub, 10.0, 1.0], dtype=np.float32)
        return Box(lowers, uppers)

    def render_state_plt(
            self,
            state: State,
            task: LowLevelEnvironmentTask,
            action: Optional[Action] = None,
            caption: Optional[str] = None) -> matplotlib.figure.Figure:
        r = self._block_size * 0.5  # block radius

        width_ratio = max(
            1. / 5,
            min(
                5.,  # prevent from being too extreme
                (self.y_ub - self.y_lb) / (self.x_ub - self.x_lb)))
        fig, (xz_ax, yz_ax) = plt.subplots(
            1,
            2,
            figsize=(20, 8),
            gridspec_kw={'width_ratios': [1, width_ratio]})
        xz_ax.set_xlabel("x", fontsize=24)
        xz_ax.set_ylabel("z", fontsize=24)
        xz_ax.set_xlim((self.x_lb - 2 * r, self.x_ub + 2 * r))
        xz_ax.set_ylim((self.table_height, r * 16 + 0.1))
        yz_ax.set_xlabel("y", fontsize=24)
        yz_ax.set_ylabel("z", fontsize=24)
        yz_ax.set_xlim((self.y_lb - 2 * r, self.y_ub + 2 * r))
        yz_ax.set_ylim((self.table_height, r * 16 + 0.1))

        blocks = [o for o in state if o.is_instance(self._block_type)]
        held = "None"
        for block in sorted(blocks):
            x = state.get(block, "pose_x")
            y = state.get(block, "pose_y")
            z = state.get(block, "pose_z")
            # RGB values are between 0 and 1.
            color_r = state.get(block, "color_r")
            color_g = state.get(block, "color_g")
            color_b = state.get(block, "color_b")
            color = (color_r, color_g, color_b)
            if state.get(block, "held") > self.held_tol:
                assert held == "None"
                held = f"{block.name}"

            # xz axis
            xz_rect = patches.Rectangle((x - r, z - r),
                                        2 * r,
                                        2 * r,
                                        zorder=-y,
                                        linewidth=1,
                                        edgecolor='black',
                                        facecolor=color)
            xz_ax.add_patch(xz_rect)

            # yz axis
            yz_rect = patches.Rectangle((y - r, z - r),
                                        2 * r,
                                        2 * r,
                                        zorder=-x,
                                        linewidth=1,
                                        edgecolor='black',
                                        facecolor=color)
            yz_ax.add_patch(yz_rect)

        title = f"Held: {held}"
        if caption is not None:
            title += f"; {caption}"
        plt.suptitle(title, fontsize=24, wrap=True)
        plt.tight_layout()
        return fig

    def _get_tasks(self, num_tasks: int, possible_num_blocks: List[int],
                   rng: np.random.Generator) -> List[LowLevelEnvironmentTask]:
        tasks = []
        for _ in range(num_tasks):
            num_blocks = rng.choice(possible_num_blocks)
            piles = self._sample_initial_piles(num_blocks, rng)
            init_state = self._sample_state_from_piles(piles, rng)
            while True:  # repeat until goal is not satisfied
                goal_state, goal_atoms = self._sample_goal_from_piles(num_blocks, piles, rng)
                if not all(goal_atom.holds(init_state) for goal_atom in goal_atoms):
                    break
            tasks.append(LowLevelEnvironmentTask(init_state, goal_state))
        return tasks

    def _sample_initial_piles(self, num_blocks: int,
                              rng: np.random.Generator) -> List[List[Object]]:
        piles: List[List[Object]] = []
        for block_num in range(num_blocks):
            block = Object(f"block{block_num}", self._block_type)
            # If coin flip, start new pile
            if block_num == 0 or rng.uniform() < 0.2:
                piles.append([])
            # Add block to pile
            piles[-1].append(block)
        return piles

    def _sample_state_from_piles(self, piles: List[List[Object]],
                                 rng: np.random.Generator) -> State:
        data: Dict[Object, Array] = {}
        # Create objects
        block_to_pile_idx = {}
        for i, pile in enumerate(piles):
            for j, block in enumerate(pile):
                assert block not in block_to_pile_idx
                block_to_pile_idx[block] = (i, j)
        # Sample pile (x, y)s
        pile_to_xy: Dict[int, Tuple[float, float]] = {}
        for i in range(len(piles)):
            pile_to_xy[i] = self._sample_initial_pile_xy(
                rng, set(pile_to_xy.values()))
        # Create block states
        for block, pile_idx in block_to_pile_idx.items():
            pile_i, pile_j = pile_idx
            x, y = pile_to_xy[pile_i]
            z = self.table_height + self._block_size * (0.5 + pile_j)
            r, g, b = rng.uniform(size=3)
            if "clear" in self._block_type.feature_names:
                # [pose_x, pose_y, pose_z, held, color_r, color_g, color_b,
                # clear]
                # Block is clear iff it is at the top of a pile
                clear = pile_j == len(piles[pile_i]) - 1
                data[block] = np.array([x, y, z, 0.0, r, g, b, clear])
            else:
                # [pose_x, pose_y, pose_z, held, color_r, color_g, color_b]
                data[block] = np.array([x, y, z, 0.0, r, g, b])
        # [pose_x, pose_y, pose_z, fingers]
        # Note: the robot poses are not used in this environment (they are
        # constant), but they change and get used in the PyBullet subclass.
        rx, ry, rz = self.robot_init_x, self.robot_init_y, self.robot_init_z
        rf = 1.0  # fingers start out open
        data[self._robot] = np.array([rx, ry, rz, rf], dtype=np.float32)
        return State(data)

    def _sample_goal_from_piles(self, num_blocks: int,
                                piles: List[List[Object]],
                                rng: np.random.Generator) -> Set[GroundAtom]:
        # Sample a goal that involves holding a block that's on the top of
        # the pile. This is useful for isolating the learning of picking and
        # unstacking. (For just picking, use num_blocks 1).
        if CFG.blocks_holding_goals:
            pile_idx = rng.choice(len(piles))
            top_block = piles[pile_idx][-1]
            return {GroundAtom(self._Holding, [top_block])}
        # Sample goal pile that is different from initial
        while True:
            goal_piles = self._sample_initial_piles(num_blocks, rng)
            if goal_piles != piles:
                break
        # Create low-level goal from piles
        goal_state = self._sample_state_from_piles(goal_piles, rng)
        goal_atoms = set()
        for pile in goal_piles:
            goal_atoms.add(GroundAtom(self._OnTable, [pile[0]]))
            if len(pile) == 1:
                continue
            for block1, block2 in zip(pile[1:], pile[:-1]):
                goal_atoms.add(GroundAtom(self._On, [block1, block2]))
        return goal_state, goal_atoms

    def _sample_initial_pile_xy(
            self, rng: np.random.Generator,
            existing_xys: Set[Tuple[float, float]]) -> Tuple[float, float]:
        while True:
            x = rng.uniform(self.x_lb, self.x_ub)
            y = rng.uniform(self.y_lb, self.y_ub)
            if self._table_xy_is_clear(x, y, existing_xys):
                return (x, y)

    def _table_xy_is_clear(self, x: float, y: float,
                           existing_xys: Set[Tuple[float, float]]) -> bool:
        if all(
                abs(x - other_x) > self.collision_padding * self._block_size
                for other_x, _ in existing_xys):
            return True
        if all(
                abs(y - other_y) > self.collision_padding * self._block_size
                for _, other_y in existing_xys):
            return True
        return False

    def _block_is_clear(self, block: Object, state: State) -> bool:
        return self._Clear_holds(state, [block])

    def _On_holds(self, state: State, objects: Sequence[Object]) -> bool:
        block1, block2 = objects
        if state.get(block1, "held") >= self.held_tol or \
           state.get(block2, "held") >= self.held_tol:
            return False
        x1 = state.get(block1, "pose_x")
        y1 = state.get(block1, "pose_y")
        z1 = state.get(block1, "pose_z")
        x2 = state.get(block2, "pose_x")
        y2 = state.get(block2, "pose_y")
        z2 = state.get(block2, "pose_z")
        return np.allclose([x1, y1, z1], [x2, y2, z2 + self._block_size],
                           atol=self.on_tol)

    def _OnTable_holds(self, state: State, objects: Sequence[Object]) -> bool:
        block, = objects
        z = state.get(block, "pose_z")
        desired_z = self.table_height + self._block_size * 0.5
        return (state.get(block, "held") < self.held_tol) and \
            (desired_z-self.on_tol < z < desired_z+self.on_tol)

    @staticmethod
    def _GripperOpen_holds(state: State, objects: Sequence[Object]) -> bool:
        robot, = objects
        rf = state.get(robot, "fingers")
        assert rf in (0.0, 1.0)
        return rf == 1.0

    def _Holding_holds(self, state: State, objects: Sequence[Object]) -> bool:
        block, = objects
        return self._get_held_block(state) == block

    def _Clear_holds(self, state: State, objects: Sequence[Object]) -> bool:
        if self._Holding_holds(state, objects):
            return False
        block, = objects
        for other_block in state:
            if other_block.type != self._block_type:
                continue
            if self._On_holds(state, [other_block, block]):
                return False
        return True

    def _get_held_block(self, state: State) -> Optional[Object]:
        for block in state:
            if not block.is_instance(self._block_type):
                continue
            if state.get(block, "held") >= self.held_tol:
                return block
        return None

    def _get_block_at_xyz(self, state: State, x: float, y: float,
                          z: float) -> Optional[Object]:
        close_blocks = []
        for block in state:
            if not block.is_instance(self._block_type):
                continue
            block_pose = np.array([
                state.get(block, "pose_x"),
                state.get(block, "pose_y"),
                state.get(block, "pose_z")
            ])
            if np.allclose([x, y, z], block_pose, atol=self.pick_tol):
                dist = np.linalg.norm(np.array([x, y, z]) - block_pose)
                close_blocks.append((block, float(dist)))
        if not close_blocks:
            return None
        return min(close_blocks, key=lambda x: x[1])[0]  # min distance

    def _get_highest_block_below(self, state: State, x: float, y: float,
                                 z: float) -> Optional[Object]:
        blocks_here = []
        for block in state:
            if not block.is_instance(self._block_type):
                continue
            block_pose = np.array(
                [state.get(block, "pose_x"),
                 state.get(block, "pose_y")])
            block_z = state.get(block, "pose_z")
            if np.allclose([x, y], block_pose, atol=self.pick_tol) and \
               block_z < z - self.pick_tol:
                blocks_here.append((block, block_z))
        if not blocks_here:
            return None
        return max(blocks_here, key=lambda x: x[1])[0]  # highest z

    def _load_task_from_json(self, json_file: Path) -> LowLevelEnvironmentTask:
        with open(json_file, "r", encoding="utf-8") as f:
            task_spec = json.load(f)
        # Create the initial state from the task spec.
        # One day, we can make the block size a feature of the blocks, but
        # for now, we'll just make sure that the block size in the real env
        # matches what we expect in sim.
        assert np.isclose(task_spec["block_size"], self._block_size)
        state_dict: Dict[Object, Dict[str, float]] = {}
        id_to_obj: Dict[str, Object] = {}  # used in the goal construction
        for block_id, block_spec in task_spec["blocks"].items():
            block = Object(block_id, self._block_type)
            id_to_obj[block_id] = block
            x, y, z = block_spec["position"]
            # Make sure that the block is in bounds.
            if not (self.x_lb <= x <= self.x_ub and \
                    self.y_lb <= y <= self.y_ub and \
                    self.table_height <= z):
                logging.warning("Block out of bounds in initial state!")
            r, g, b = block_spec["color"]
            state_dict[block] = {
                "pose_x": x,
                "pose_y": y,
                "pose_z": z,
                "held": 0,
                "color_r": r,
                "color_b": b,
                "color_g": g,
            }
        # Add the robot at a constant initial position.
        rx, ry, rz = self.robot_init_x, self.robot_init_y, self.robot_init_z
        rf = 1.0  # fingers start out open
        state_dict[self._robot] = {
            "pose_x": rx,
            "pose_y": ry,
            "pose_z": rz,
            "fingers": rf,
        }
        init_state = utils.create_state_from_dict(state_dict)
        # Create the goal from the task spec.
        if "goal" in task_spec:
            goal = self._parse_goal_from_json(task_spec["goal"], id_to_obj)
        elif "language_goal" in task_spec:
            goal = self._parse_language_goal_from_json(
                task_spec["language_goal"], id_to_obj)
        else:
            raise ValueError("JSON task spec must include 'goal'.")
        env_task = LowLevelEnvironmentTask(init_state, goal)
        assert not env_task.task.goal_holds(init_state)
        return env_task

    def _get_language_goal_prompt_prefix(self,
                                         object_names: Collection[str]) -> str:
        # pylint:disable=line-too-long
        return """# Build a tower of block 1, block 2, and block 3, with block 1 on top
{"On": [["block1", "block2"], ["block2", "block3"]]}

# Put block 4 on block 3 and block 2 on block 1 and block 1 on table
{"On": [["block4", "block3"], ["block2", "block1"]], "OnTable": [["block1"]]}
"""
