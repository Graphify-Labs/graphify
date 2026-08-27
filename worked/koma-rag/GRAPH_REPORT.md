# Graph Report - KoMA-RAG  (2026-08-27)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 996 nodes · 2076 edges · 65 communities (52 shown, 13 thin omitted)
- Extraction: 95% EXTRACTED · 5% INFERRED · 0% AMBIGUOUS · INFERRED: 109 edges (avg confidence: 0.95)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `0ad938e9`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Community 0
- Community 1
- Community 2
- Community 3
- Community 4
- Community 5
- Community 6
- Community 7
- Community 8
- Community 9
- Community 10
- Community 11
- Community 12
- Community 13
- Community 14
- Community 15
- Community 16
- Community 17
- Community 18
- Community 19
- Community 20
- Community 21
- Community 22
- Community 23
- Community 24
- Community 25
- Community 26
- Community 27
- Community 28
- Community 29
- Community 30
- Community 31
- Community 32
- Community 33
- Community 34
- Community 35
- Community 36
- Community 37
- Community 38
- Community 39
- Community 40
- Community 41
- Community 42
- Community 43
- Community 44
- Community 45
- Community 46
- Community 47
- Community 48
- Community 49
- Community 50
- Community 51
- Community 52
- Community 53
- Community 54
- Community 55
- Community 56
- Community 57
- Community 63
- Community 64

## God Nodes (most connected - your core abstractions)
1. `Road` - 58 edges
2. `Vehicle` - 56 edges
3. `AbstractEnv` - 52 edges
4. `RoadNetwork` - 51 edges
5. `IDMVehicle` - 50 edges
6. `AbstractLane` - 39 edges
7. `MDPVehicle` - 38 edges
8. `StraightLane` - 34 edges
9. `ControlledVehicle` - 33 edges
10. `EnvScenario` - 30 edges

## Surprising Connections (you probably didn't know these)
- `DriverAgent` --uses--> `EnvScenario`  [INFERRED]
  LLMDriver/driverAgent.py → scenario/envScenario.py
- `EnvScenario` --uses--> `AbstractEnv`  [INFERRED]
  scenario/envRoundaboutScenario.py → highway_env/envs/common/abstract.py
- `EnvScenario` --uses--> `AbstractEnv`  [INFERRED]
  scenario/envScenario.py → highway_env/envs/common/abstract.py
- `DrivingMemory` --uses--> `EnvScenario`  [INFERRED]
  LLMDriver/vectorStore.py → scenario/envScenario.py
- `EnvScenario` --uses--> `StraightLane`  [INFERRED]
  scenario/envScenario.py → highway_env/road/lane.py

## Import Cycles
- None detected.

## Communities (65 total, 13 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.05
Nodes (30): DataFrame, AttributesObservation, ExitObservation, GrayscaleObservation, KinematicObservation, KinematicsGoalObservation, LidarObservation, MultiAgentObservation (+22 more)

### Community 1 - "Community 1"
Cohesion: 0.05
Nodes (49): integrator_interval(), interval_absolute_to_local(), interval_local_to_absolute(), interval_negative_part(), intervals_diff(), intervals_product(), intervals_scaling(), is_metzler() (+41 more)

### Community 2 - "Community 2"
Cohesion: 0.06
Nodes (24): AbstractEnv, Action, ndarray, Text, Set the types and spaces of observation and action from config., Return the reward associated with performing a given action and ending up in…, Returns a multi-objective vector of rewards. If implemented, this reward vector…, Check whether the current state is a terminal state :return:is the state… (+16 more)

### Community 3 - "Community 3"
Cohesion: 0.06
Nodes (23): AggressiveVehicle, DefensiveVehicle, LinearVehicle, LaneIndex, ndarray, Route, Vector, Decide when to change lane. Based on: - frequency; - closeness of the target… (+15 more)

### Community 4 - "Community 4"
Cohesion: 0.08
Nodes (20): LaneIndex, ndarray, object, RandomState, Route, Breadth-first search of all routes from start to goal. :param start: starting…, Breadth-first search of shortest path from start to goal. :param start:…, :param lane_index: the index of a lane. :return: all lanes belonging to the… (+12 more)

### Community 5 - "Community 5"
Cohesion: 0.07
Nodes (16): KoMAMultiRoundAboutEnv, Text, Populate a road with several vehicles on the highway and on the merging lane,…, LaneIndex, Route, Vector, At the end of a lane, automatically switch to a next one., Steer the vehicle to follow the center of an given lane. 1. Lateral position is… (+8 more)

### Community 6 - "Community 6"
Cohesion: 0.08
Nodes (33): are_polygons_intersecting(), confidence_ellipsoid(), confidence_polytope(), constrain(), distance_to_rect(), has_corner_inside(), interval_distance(), is_consistent_dataset() (+25 more)

### Community 7 - "Community 7"
Cohesion: 0.28
Nodes (6): # TODO: check lane overflow (e.g. vehicle with higher lane id than current road…, distance_to_circle(), solve_trinom(), MDPVehicle, A controlled vehicle with a specified discrete range of allowed target speeds., # TODO: For now, we assume the front vehicle follows the models' front vehicle

### Community 8 - "Community 8"
Cohesion: 0.15
Nodes (6): IDMVehicle, A vehicle using both a longitudinal and a lateral decision policies. -…, If stopped on the wrong lane, try a reversing maneuver. :param acceleration:…, Create a new vehicle from an existing one. The vehicle dynamics and target…, EnvScenario, LaneIndex

### Community 9 - "Community 9"
Cohesion: 0.08
Nodes (13): PolyLaneFixedWidth, A fixed-width lane defined by a set of points and approximated with a 2D…, CurvePose, LinearSpline2D, Create samples of the curve that are CURVE_SAMPLE_DISTANCE apart. These samples…, Sample pose on a curve that is used for Frenet to Cartesian conversion, Compute the distance between the point [x, y] and the pose origin, Compute the longitudinal distance from pose origin to point by projecting the… (+5 more)

### Community 10 - "Community 10"
Cohesion: 0.14
Nodes (11): _cosine(), _extract_lane_count(), _extract_scenario_tag(), Any, Verification-Enhanced Retrieval (KoMA-RAG Module 4). Composite verification…, Non-LLM factual check: lane count / merge-vs-highway agreement., candidates: list of (metadata_dict, chroma_distance_or_None) Returns up to…, Mean V_factual across verify_one() calls since the last reset (NaN if none). (+3 more)

### Community 11 - "Community 11"
Cohesion: 0.16
Nodes (11): BicycleVehicle, ndarray, Vector, single-step fourth-order numerical integration (RK4) method func: system of…, State: [lateral speed v, yaw rate r] :return: lateral dynamics A0, phi, B such…, State: [lateral speed v, yaw rate r] :return: lateral dynamics A, B, State: [position y, yaw psi, lateral speed v, yaw rate r] The system is…, A dynamical bicycle model, with tire friction and slipping. See Chapter 2 of… (+3 more)

### Community 12 - "Community 12"
Cohesion: 0.11
Nodes (9): LaneIndex, ndarray, Compute the signed distance to another object along a lane. :param other: the…, Common interface for objects that appear on the road. For now we assume all…, Is the object on its current lane, or off-road?, :param road: the road instance where the object is placed in :param position:…, Create a vehicle on a given lane at a longitudinal position. :param road: a…, Check for collision with another vehicle. :param other: the other vehicle or… (+1 more)

### Community 13 - "Community 13"
Cohesion: 0.17
Nodes (8): lane_from_config(), A lane going in straight line., SineLane, StraightLane, _to_serializable(), class_from_path(), get_class_path(), wrap_to_pi()

### Community 14 - "Community 14"
Cohesion: 0.19
Nodes (15): _env(), _env_bool(), _env_float(), _env_int(), _is_deepseek(), LLMResponse, _message_role_content(), NvidiaChatLLM (+7 more)

### Community 15 - "Community 15"
Cohesion: 0.19
Nodes (10): AgentKinematics, CoordinationDirective, MasterAgent, Master Coordination Module (KoMA-RAG Module 3). Implements conflict detection,…, IDM vehicles get priority=inf (conservative yield policy)., Optional LLM enrichment when conflicts exist (prompt-based Master)., Broadcast msg_M→i = {g_assigned, π_assigned, constraints}. If enable=False,…, Build ego/IDM kinematics from highway-env + EnvScenario. (+2 more)

### Community 16 - "Community 16"
Cohesion: 0.20
Nodes (13): DriverAgent, EnvScenario, apply_config_to_env(), _as_bool(), _as_float(), _as_int(), get_framework_flags(), load_config() (+5 more)

### Community 17 - "Community 17"
Cohesion: 0.21
Nodes (10): LaneGraphics, A visualization of a lane., Display a lane on a surface. :param lane: the lane to be displayed :param…, Draw a striped line on one side of a lane, on a surface. :param lane: the lane…, Draw a continuous line on one side of a lane, on a surface. :param lane: the…, Draw a set of stripes along a lane. :param lane: the lane :param surface: the…, A pygame Surface implementing a local coordinate system so that we can move and…, Display the road lanes on a surface. :param road: the road to be displayed… (+2 more)

### Community 18 - "Community 18"
Cohesion: 0.12
Nodes (9): AbstractLane, object, A lane on the road, described by its central curve., Convert local lane coordinates to a world position. :param longitudinal:…, Convert a world position to local lane coordinates. :param position: a world…, Get the lane heading at a given longitudinal lane coordinate. :param…, Get the lane width at a given longitudinal lane coordinate. :param…, Create lane instance from config :param config: json dict with lane parameters (+1 more)

### Community 19 - "Community 19"
Cohesion: 0.14
Nodes (6): ndarray, Compute the L1 distance [m] from a position to the lane., Compute a weighted distance in position and heading to the lane., Compute non-normalised angle of heading to the lane., Whether a given world position is on the lane. :param position: a world…, Whether the lane is reachable from a given world position :param position: the…

### Community 20 - "Community 20"
Cohesion: 0.15
Nodes (6): ndarray, Vector, A moving vehicle on a road, and its kinematics. The vehicle is represented by a…, Predict the future trajectory of the vehicle given a sequence of actions.…, Create a random vehicle on the road. The lane and /or speed are chosen…, Vehicle

### Community 22 - "Community 22"
Cohesion: 0.15
Nodes (7): KoMAMergeGeneralizationEnv, Text, Populate a road with several vehicles on the highway and on the merging lane,…, A highway merge negotiation environment. The ego-vehicle is driving on a…, The vehicle is rewarded for driving with high speed on lanes to the right and…, The episode is over when a collision occurs or when the access ramp has been…, Make a road composed of a straight highway and a merging lane. :return: the road

### Community 23 - "Community 23"
Cohesion: 0.16
Nodes (8): EnvViewer, ndarray, The rendered image as a rgb array. Gymnasium's channel convention is H x W x C, the world position of the center of the displayed window., Close the pygame window., A viewer to render a highway driving environment., Set a display callback provided by an agent So that they can render their…, Set the sequence of actions chosen by the agent, so that it can be displayed…

### Community 24 - "Community 24"
Cohesion: 0.20
Nodes (7): Display the road and vehicles on a pygame window., Display the road vehicles on a surface. :param road: the road to be displayed…, object, Display the whole trajectory of a vehicle on a pygame surface. :param states:…, Display the whole trajectory of a vehicle on a pygame surface. :param vehicle:…, Display a vehicle on a pygame surface. The vehicle is represented as a colored…, VehicleGraphics

### Community 25 - "Community 25"
Cohesion: 0.16
Nodes (7): KoMAMergeOneLaneEnv, Text, Populate a road with several vehicles on the highway and on the merging lane,…, A highway merge negotiation environment. The ego-vehicle is driving on a…, The vehicle is rewarded for driving with high speed on lanes to the right and…, The episode is over when a collision occurs or when the access ramp has been…, Make a road composed of a straight highway and a merging lane. :return: the road

### Community 26 - "Community 26"
Cohesion: 0.16
Nodes (7): KoMAMergeThreeLaneEnv, Text, Populate a road with several vehicles on the highway and on the merging lane,…, A highway merge negotiation environment. The ego-vehicle is driving on a…, The vehicle is rewarded for driving with high speed on lanes to the right and…, The episode is over when a collision occurs or when the access ramp has been…, Make a road composed of a straight highway and a merging lane. :return: the road

### Community 27 - "Community 27"
Cohesion: 0.24
Nodes (6): SurfaceType, Vector, A visualization of objects on the road., Display a road objects on a pygame surface. The objects is represented as a…, Many thanks to https://stackoverflow.com/a/54714144., RoadObjectGraphics

### Community 28 - "Community 28"
Cohesion: 0.17
Nodes (7): get_embedding_function(), Return a langchain-compatible embedding function. For nvidia/ollama (no OpenAI…, DrivingMemory, Any, EnvScenario, Baseline similarity-only retrieval (KoMA)., Return (metadata, distance, page_content) for verification filtering. Distance…

### Community 30 - "Community 30"
Cohesion: 0.22
Nodes (8): LineType, PolyLane, Vector, A lane side line type., New straight lane. :param start: the lane starting position [m] :param end: the…, A lane defined by a set of points and approximated with a 2D Hermite polynomial., Calculate width by taking the minimum distance between centerline and each…, Pre-calculate sampled width values in about 1m distance to reduce computation…

### Community 31 - "Community 31"
Cohesion: 0.22
Nodes (5): Discrete, action_factory(), DiscreteAction, MultiAgentAction, Action

### Community 32 - "Community 32"
Cohesion: 0.15
Nodes (8): ActionType, object, setter, A type of action specifies its definition space, and how actions are executed…, The class of a vehicle able to execute the action. Must return a subclass of…, Execute the action on the ego-vehicle. Most of the action mechanics are…, For discrete action space, return the list of available actions., The vehicle acted upon. If not set, the first controlled vehicle is used by…

### Community 33 - "Community 33"
Cohesion: 0.20
Nodes (10): clip_position(), compute_ttc_grid(), finite_mdp(), ndarray, Deterministic transition from a position in the grid to the next. :param h:…, Clip a position in the TTC grid, so that it stays within bounds. :param h:…, Time-To-Collision (TTC) representation of the state. The state reward is…, Compute the grid of predicted time-to-collision to each vehicle within the lane… (+2 more)

### Community 34 - "Community 34"
Cohesion: 0.22
Nodes (5): Box, ContinuousAction, ndarray, An continuous action space for throttle and/or steering angle. If both throttle…, Create a continuous action space. :param env: the environment :param…

### Community 35 - "Community 35"
Cohesion: 0.18
Nodes (6): DiscreteMetaAction, Space, Vector, An discrete action space of meta-actions: lane changes, and cruise control set-…, Create a discrete action space of meta-actions. :param env: the environment…, Get the list of currently available actions. Lane changes are not available on…

### Community 36 - "Community 36"
Cohesion: 0.20
Nodes (6): Convert a distance [m] to pixels [px]. :param length: the input distance [m]…, Convert two world coordinates [m] into a position in the surface [px] :param x:…, Convert a world position [m] into a position in the surface [px]. :param vec: a…, Is a position visible in the surface? :param vec: a position :param margin:…, Set the origin of the displayed area to center on a given world position.…, PositionType

### Community 37 - "Community 37"
Cohesion: 0.22
Nodes (4): create_chat_llm(), Factory for role-specific chat models. Raises clearly on unknown API type or…, Reflection_Choose_Agent, ReflectionAgent

### Community 39 - "Community 39"
Cohesion: 0.31
Nodes (5): ABC, Landmark, Obstacle, Obstacles on the road., Landmarks of certain areas on the road that must be reached.

### Community 40 - "Community 40"
Cohesion: 0.31
Nodes (4): RandomState, Find conflicts and resolve them by assigning yielding vehicles and stopping…, Resolve a conflict between two vehicles by determining who should yield :param…, RegulatedRoad

### Community 41 - "Community 41"
Cohesion: 0.39
Nodes (8): aggregate_results(), log(), main(), Runs the KoMA-RAG ablation study (paper Table I) end to end: 1. Seeds the…, Run main.py as a subprocess for one config, streaming + logging output., Rewrite only the given KEY: value lines in config.yaml; preserves everything…, run_one(), set_config_flags()

### Community 42 - "Community 42"
Cohesion: 0.39
Nodes (4): EventHandler, EventType, Map the pygame keyboard events to control decisions :param action_type: the…, Handle pygame events by forwarding them to the display and environment vehicle.

### Community 43 - "Community 43"
Cohesion: 0.25
Nodes (4): A road is a set of lanes, and a set of vehicles driving on these lanes., Decide the actions of each entity on the road., Step the dynamics of each entity on the road. :param dt: timestep [s], Road

### Community 44 - "Community 44"
Cohesion: 0.46
Nodes (4): LangchainChatAdapter, Any, Thin adapter so azure/openai/ollama share the same call surface., MessageLike

### Community 48 - "Community 48"
Cohesion: 0.50
Nodes (3): setter, First (default) controlled vehicle., Set a unique controlled vehicle.

### Community 51 - "Community 51"
Cohesion: 0.50
Nodes (3): SurfaceType, Vector, Many thanks to https://stackoverflow.com/a/54714144.

### Community 55 - "Community 55"
Cohesion: 0.67
Nodes (3): lmap(), Interval, Linear map of value v with range x to desired range y.

### Community 63 - "Community 63"
Cohesion: 0.25
Nodes (5): ControlledVehicle, A vehicle piloted by two low-level controller, allowing high-level actions such…, Predict the future trajectory of the vehicle given a sequence of actions.…, Create a new vehicle from an existing one. The vehicle dynamics and target…, Plan a route to a destination in the road network :param destination: a node in…

### Community 64 - "Community 64"
Cohesion: 0.40
Nodes (4): object, A visualization of a road lanes and vehicles., Display the road objects on a surface. :param road: the road to be displayed…, RoadGraphics

## Knowledge Gaps
- **13 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Road` connect `Community 43` to `Community 1`, `Community 3`, `Community 4`, `Community 5`, `Community 7`, `Community 8`, `Community 11`, `Community 13`, `Community 17`, `Community 20`, `Community 21`, `Community 22`, `Community 24`, `Community 25`, `Community 26`, `Community 39`, `Community 40`, `Community 63`, `Community 64`?**
  _High betweenness centrality (0.158) - this node is a cross-community bridge._
- **Why does `AbstractEnv` connect `Community 2` to `Community 32`, `Community 33`, `Community 0`, `Community 5`, `Community 7`, `Community 8`, `Community 13`, `Community 46`, `Community 45`, `Community 48`, `Community 20`, `Community 21`, `Community 22`, `Community 23`, `Community 25`, `Community 26`?**
  _High betweenness centrality (0.153) - this node is a cross-community bridge._
- **Why does `Vehicle` connect `Community 20` to `Community 0`, `Community 33`, `Community 2`, `Community 34`, `Community 3`, `Community 5`, `Community 1`, `Community 7`, `Community 40`, `Community 8`, `Community 11`, `Community 43`, `Community 12`, `Community 47`, `Community 48`, `Community 50`, `Community 24`, `Community 63`?**
  _High betweenness centrality (0.140) - this node is a cross-community bridge._
- **Are the 16 inferred relationships involving `Road` (e.g. with `KoMAMergeGeneralizationEnv` and `KoMAMergeOneLaneEnv`) actually correct?**
  _`Road` has 16 INFERRED edges - model-reasoned connections that need verification._
- **Are the 12 inferred relationships involving `Vehicle` (e.g. with `AbstractEnv` and `ContinuousAction`) actually correct?**
  _`Vehicle` has 12 INFERRED edges - model-reasoned connections that need verification._
- **Are the 7 inferred relationships involving `AbstractEnv` (e.g. with `ActionType` and `EnvViewer`) actually correct?**
  _`AbstractEnv` has 7 INFERRED edges - model-reasoned connections that need verification._
- **Are the 12 inferred relationships involving `RoadNetwork` (e.g. with `KoMAMergeGeneralizationEnv` and `KoMAMergeOneLaneEnv`) actually correct?**
  _`RoadNetwork` has 12 INFERRED edges - model-reasoned connections that need verification._