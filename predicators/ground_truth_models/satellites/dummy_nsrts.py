"""Dummy NSRTs for the satellites environment.
It only has pre-condition predicates and no effects.
It is used by our baselines if we assume GT sampler is provided.
"""

from typing import Dict, Sequence, Set

import numpy as np

from predicators.envs.satellites import SatellitesEnv
from predicators.ground_truth_models import DummyNSRTFactory
from predicators.structs import NSRT, Array, GroundAtom, LiftedAtom, Object, \
    ParameterizedOption, Predicate, State, Type, Variable
from predicators.utils import null_sampler, Circle


class SatellitesDummyNSRTFactory(DummyNSRTFactory):
    """Ground-truth NSRTs for the satellites environment."""

    @classmethod
    def get_env_names(cls) -> Set[str]:
        return {"satellites", "satellites_simple", "satellites_medium", "satellites_hard"}

    @staticmethod
    def get_nsrts(env_name: str, types: Dict[str, Type],
                  predicates: Dict[str, Predicate],
                  options: Dict[str, ParameterizedOption]) -> Set[NSRT]:
        # Types
        sat_type = types["satellite"]
        obj_type = types["object"]

        # Predicates
        CalibrationTarget = predicates["CalibrationTarget"]
        HasCamera = predicates["HasCamera"]
        HasInfrared = predicates["HasInfrared"]
        HasGeiger = predicates["HasGeiger"]
        ShootsChemX = predicates["ShootsChemX"]
        ShootsChemY = predicates["ShootsChemY"]
        CameraReadingTaken = predicates["CameraReadingTaken"]
        InfraredReadingTaken = predicates["InfraredReadingTaken"]
        GeigerReadingTaken = predicates["GeigerReadingTaken"]

        # Options
        MoveTo = options["MoveTo"]
        MoveAway = options["MoveAway"]
        Calibrate = options["Calibrate"]
        ShootChemX = options["ShootChemX"]
        ShootChemY = options["ShootChemY"]
        UseCamera = options["UseCamera"]
        UseInfraRed = options["UseInfraRed"]
        UseGeiger = options["UseGeiger"]

        nsrts = set()

        # MoveTo
        sat = Variable("?sat", sat_type)
        obj = Variable("?obj", obj_type)
        parameters = [sat, obj]
        option_vars = [sat, obj]
        option = MoveTo
        preconditions = set()
        add_effects = set()
        delete_effects = set()
        ignore_effects = set()

        def moveto_sampler(state: State, goal: Set[GroundAtom],
                           rng: np.random.Generator,
                           objs: Sequence[Object]) -> Array:
            del goal  # unused
            sat, obj = objs
            obj_x = state.get(obj, "x")
            obj_y = state.get(obj, "y")
            sat_x = state.get(sat, "x")
            sat_y = state.get(sat, "y")
            # dist
            min_dist = SatellitesEnv.radius * 4
            max_dist = SatellitesEnv.fov_dist - SatellitesEnv.radius * 2
            dist = rng.uniform(min_dist, max_dist)
            # angle
            angle = rng.uniform(-np.pi, np.pi)
            x = obj_x + dist * np.cos(angle)
            y = obj_y + dist * np.sin(angle)
            return np.array([x, y], dtype=np.float32)

        moveto_nsrt = NSRT("MoveTo", parameters, preconditions, add_effects,
                           delete_effects, ignore_effects, option, option_vars,
                           moveto_sampler)
        nsrts.add(moveto_nsrt)

        # MoveAway
        sat = Variable("?sat", sat_type)
        obj = Variable("?obj", obj_type)
        parameters = [sat, obj]
        option_vars = [sat, obj]
        option = MoveAway
        preconditions = set()
        add_effects = set()
        delete_effects = set()
        ignore_effects = set()

        def moveaway_sampler(state: State, goal: Set[GroundAtom],
                           rng: np.random.Generator,
                           objs: Sequence[Object]) -> Array:
            del goal  # unused
            # Needs to fly to a random collision-free 
            # location, away from any object
            dummy_env = SatellitesEnv()
            radius = max(dummy_env.radius + dummy_env.init_padding, \
                         dummy_env.fov_dist + dummy_env.init_padding)
            collision_geoms: Set[Circle] = set()
            for sat in state.get_objects(sat_type):
                x = state.get(sat, "x")
                y = state.get(sat, "y")
                collision_geoms.add(Circle(x, y, dummy_env.radius))
            for obj in state.get_objects(obj_type):
                x = state.get(obj, "x")
                y = state.get(obj, "y")
                collision_geoms.add(Circle(x, y, radius))
            while True:
                x = rng.uniform()
                y = rng.uniform()
                geom = Circle(x, y, dummy_env.radius)
                # Keep only if no intersections with existing objects.
                if not any(geom.intersects(g) for g in collision_geoms):
                    break
            return np.array([x, y], dtype=np.float32)

        moveaway_nsrt = NSRT("MoveAway", parameters, preconditions, add_effects,
                           delete_effects, ignore_effects, option, option_vars,
                           moveaway_sampler)
        nsrts.add(moveaway_nsrt)

        # Calibrate
        sat = Variable("?sat", sat_type)
        obj = Variable("?obj", obj_type)
        parameters = [sat, obj]
        option_vars = [sat, obj]
        option = Calibrate
        preconditions = {
            LiftedAtom(CalibrationTarget, [sat, obj]),
        }
        add_effects = set()
        delete_effects = set()
        ignore_effects = set()
        calibrate_nsrt = NSRT("Calibrate", parameters, preconditions,
                              add_effects, delete_effects, ignore_effects,
                              option, option_vars, null_sampler)
        nsrts.add(calibrate_nsrt)

        # ShootChemX
        sat = Variable("?sat", sat_type)
        obj = Variable("?obj", obj_type)
        parameters = [sat, obj]
        option_vars = [sat, obj]
        option = ShootChemX
        preconditions = {
            LiftedAtom(ShootsChemX, [sat]),
        }
        add_effects = set()
        delete_effects = set()
        ignore_effects = set()
        shoot_chem_x_nsrt = NSRT("ShootChemX", parameters, preconditions,
                                 add_effects, delete_effects, ignore_effects,
                                 option, option_vars, null_sampler)
        nsrts.add(shoot_chem_x_nsrt)

        # ShootChemY
        sat = Variable("?sat", sat_type)
        obj = Variable("?obj", obj_type)
        parameters = [sat, obj]
        option_vars = [sat, obj]
        option = ShootChemY
        preconditions = {
            LiftedAtom(ShootsChemY, [sat]),
        }
        add_effects = set()
        delete_effects = set()
        ignore_effects = set()
        shoot_chem_y_nsrt = NSRT("ShootChemY", parameters, preconditions,
                                 add_effects, delete_effects, ignore_effects,
                                 option, option_vars, null_sampler)
        nsrts.add(shoot_chem_y_nsrt)

        # TakeCameraReading
        sat = Variable("?sat", sat_type)
        obj = Variable("?obj", obj_type)
        parameters = [sat, obj]
        option_vars = [sat, obj]
        option = UseCamera
        preconditions = {
            LiftedAtom(HasCamera, [sat]),
        }
        add_effects = {
            LiftedAtom(CameraReadingTaken, [sat, obj]),
        }
        delete_effects = set()
        ignore_effects = set()
        take_camera_reading_nsrt = NSRT("TakeCameraReading", parameters,
                                        preconditions, add_effects,
                                        delete_effects, ignore_effects, option,
                                        option_vars, null_sampler)
        nsrts.add(take_camera_reading_nsrt)

        # TakeInfraredReading
        sat = Variable("?sat", sat_type)
        obj = Variable("?obj", obj_type)
        parameters = [sat, obj]
        option_vars = [sat, obj]
        option = UseInfraRed
        preconditions = {
            LiftedAtom(HasInfrared, [sat]),
            # taking an infrared reading requires Chemical Y
        }
        add_effects = {
            LiftedAtom(InfraredReadingTaken, [sat, obj]),
        }
        delete_effects = set()
        ignore_effects = set()
        take_infrared_reading_nsrt = NSRT("TakeInfraredReading", parameters,
                                          preconditions, add_effects,
                                          delete_effects, ignore_effects,
                                          option, option_vars, null_sampler)
        nsrts.add(take_infrared_reading_nsrt)

        # TakeGeigerReading
        sat = Variable("?sat", sat_type)
        obj = Variable("?obj", obj_type)
        parameters = [sat, obj]
        option_vars = [sat, obj]
        option = UseGeiger
        preconditions = {
            LiftedAtom(HasGeiger, [sat]),
            # taking a Geiger reading doesn't require any chemical
        }
        add_effects = {
            LiftedAtom(GeigerReadingTaken, [sat, obj]),
        }
        delete_effects = set()
        ignore_effects = set()
        take_geiger_reading_nsrt = NSRT("TakeGeigerReading", parameters,
                                        preconditions, add_effects,
                                        delete_effects, ignore_effects, option,
                                        option_vars, null_sampler)
        nsrts.add(take_geiger_reading_nsrt)

        return nsrts
