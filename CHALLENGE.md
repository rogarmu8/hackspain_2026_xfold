# THEKER Robotics · HackSpain '26

**Automatiza una tarea que hoy hace una persona**

> «Automatizar el 100 % del trabajo manual y crear la empresa más grande del mundo.»

THEKER’s mission, and the brief: pick a real, ambitious, technically hard manual task and build something that shows a person no longer has to do it.

---

## 01 · The challenge

Europe has a structural shortage of industrial labour. Factory shifts are harder to fill, and many manual tasks stay unautomated because they need a kind of variability that classical robotics still handles badly: mixed objects, unpredictable poses, deformation, overlap, and surprises.

**Goal:** choose a task that a person still does in an industrial setting and build a system that can complete it autonomously, end to end.

Each team defines its own technical scope:

- Which manual task to automate.
- Which variability the system must handle: object types, sizes, poses, orientations, deformations, occlusions, scene changes.
- What the system must perceive, decide, and execute so a human is not in the loop.
- How far the same solution can extend to new variants of the task without being reprogrammed from scratch.

The stack is free: manipulation, mobile robotics, computer vision, planning, machine learning, or any mix.

Solving one variable task autonomously is already hard. Making the same system adapt to new objects, formats, or variants with minimal change is the next level. Generalization is not required, but it is especially valued.

The jury should be able to answer three questions:

1. Does the system solve the task end to end, and repeatably?
2. Is the chosen task a real problem that still needs a human today?
3. How far does the solution hold when variability increases?

---

## 02 · Evaluation

Scored on two axes.

### Axis A — Vision, judgement, execution

- **Ambition of the problem and originality of the approach.** The task must be real and demanding enough, and the solution must have a technical idea of its own — ingenious and well thought through. An original way to solve a relevant problem scores higher than a flashy but trivial task.
- **Problem-solving during development.** Which obstacles appeared, how you handled them, and how the design changed from what you learned.

### Axis B — Technical depth and results

- **Technical difficulty taken on.** What real complexity you actually solved, how much variability you accepted, and how far you pushed the system.
- **Autonomy and engineering quality.** The system completes the task end to end, without human intervention, and in a reproducible way.
- **Iteration and measured improvement.** Your own metrics, measured, and data that show how much the solution improved during development.
- **Generalization.** How far the solution extends to new objects, conditions, or task variants with minimal change.

### Extra points — Hardware and physical realism

A scene that credibly represents the real process and, when it applies, a terminal or physical system whose design matches the task.

---

## 03 · Example tasks

Tasks that are still done by hand on the shop floor. Inspiration only, not a menu. Finding a task with enough difficulty and carrying it to a solid solution is part of the challenge.

- **Object induction** — placing loose parcels, one by one and correctly oriented, onto a sorting line.
- **Palletizing** — stacking parcels of different size and weight onto a pallet that will survive transport.

Starting from one of these is valid. Originality and ambition of the **technical approach** matter more than picking a spectacular task: how much variability you take on, how you pose the solution, and how robust and generalizable you make it. Combining these cases with mobile robotics, navigation, or other components is also allowed.

---

## 04 · Deliverables

Any format the team prefers.

- **Code**, with the minimum needed to understand what it contains and how to run it.
- **Short video of the system running** (optional). The demo is meant to be live; the video is a backup for what you cannot run in time or what might fail on the day.
- **One slide** (optional) that makes the problem and the solution obvious at a glance. Content is free: metrics, diagrams, architecture, process data, or anything that can be understood without a spoken explanation. One slide only.

---

## 05 · Starting resources

None of these tools is mandatory. The list is a starting point. Finding the right tool for the problem is part of the challenge.

### Simulators

- **MuJoCo** — fast, accurate physics. `pip install mujoco`. [mujoco.readthedocs.io](https://mujoco.readthedocs.io)
- **Gazebo** — standard in the ROS ecosystem. [gazebosim.org](https://gazebosim.org)
- **NVIDIA Isaac Sim / Isaac Lab** — photorealism and reinforcement learning; needs a GPU. [developer.nvidia.com/isaac/sim](https://developer.nvidia.com/isaac/sim)

### Robots, grippers, objects

- **MELFA ROS 2 Driver** — URDF, meshes, and MoveIt config for Mitsubishi Electric arms. [github.com/Mitsubishi-Electric-Asia/melfa_ros2_driver](https://github.com/Mitsubishi-Electric-Asia/melfa_ros2_driver)
- **MuJoCo Menagerie** — dozens of robots ready to simulate: arms, grippers, mobiles, humanoids. [github.com/google-deepmind/mujoco_menagerie](https://github.com/google-deepmind/mujoco_menagerie)

### Middleware and control

- **ROS 2** — industrial standard for talking between nodes, sensors, and actuators. [docs.ros.org/en/jazzy](https://docs.ros.org/en/jazzy)
- **MoveIt 2** — collision-aware motion planning for arms, inside ROS. [moveit.ai](https://moveit.ai)
- **mink** — MuJoCo-native differential IK, with joint limits and collision avoidance. [github.com/kevinzakka/mink](https://github.com/kevinzakka/mink)
- **Pinocchio** — fast kinematics and dynamics, no ROS. [github.com/stack-of-tasks/pinocchio](https://github.com/stack-of-tasks/pinocchio)

THEKER will be at their table for the whole hackathon to validate ideas, sanity-check whether a plan makes sense on a real plant, or help quantify a task.

---

## Our take for this hackathon

We automate **pressing and folding shirts** — a deformable, high-variability task that fulfilment lines still load by hand.

See [SOLUTION.md](SOLUTION.md) for the four-station cell, the MuJoCo approach, and the open-source inventory.
