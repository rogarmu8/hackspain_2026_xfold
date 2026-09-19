"""Probe which flex/cloth configurations load and stay stable in the installed MuJoCo."""
import time, sys, textwrap
import numpy as np
import mujoco

print("mujoco", mujoco.__version__)

BASE = """
<mujoco>
  {option}
  <size memory="100M"/>
  <worldbody>
    <light pos="0 0 2" dir="0 0 -1"/>
    <geom name="floor" type="plane" size="2 2 .1" friction="0.8"/>
    <geom name="bed" type="box" size="0.28 0.32 0.015" pos="0 0 0.08" friction="0.9"/>
    <flexcomp name="shirt" type="grid" dim="2" count="{nx} {ny} 1" spacing="{sp} {sp} {sp}"
              radius="{radius}" mass="0.2" pos="0 0 0.45" euler="0.35 0.2 0.4" rgba=".15 .25 .55 1">
      {inner}
    </flexcomp>
  </worldbody>
</mujoco>
"""

CASES = {
  "A_shell_plugin(SOLUTION.md)": dict(
     option='<option timestep="0.002" integrator="implicitfast"/>',
     inner='<contact internal="false" selfcollide="none" solref="0.004"/>'
           '<edge equality="true" damping="1"/>'
           '<plugin plugin="mujoco.elasticity.shell"><config key="young" value="5e3"/></plugin>',
     ext='<extension><plugin plugin="mujoco.elasticity.shell"/></extension>'),
  "B_edge_eq_only_implicitfast": dict(
     option='<option timestep="0.002" integrator="implicitfast" solver="CG" tolerance="1e-6"/>',
     inner='<contact internal="false" selfcollide="none" solref="0.005 1"/>'
           '<edge equality="true" damping="1"/>'),
  "C_native_elastic_implicitfast": dict(
     option='<option timestep="0.002" integrator="implicitfast" solver="CG" tolerance="1e-6"/>',
     inner='<contact internal="false" selfcollide="none" solref="0.005 1"/>'
           '<edge equality="true" damping="0.5"/>'
           '<elasticity young="2e4" poisson="0.2" thickness="1e-3" elastic2d="both" damping="1e-2"/>'),
  "D_native_elastic_discrete_CG": dict(
     option='<option timestep="0.002" integrator="discrete" solver="CG" tolerance="1e-6" iterations="200"/>',
     inner='<contact internal="false" selfcollide="auto" solref="0.01 1" solimp=".95 .99 .0001"/>'
           '<elasticity young="2e4" poisson="0.2" thickness="1e-3" elastic2d="both" damping="1e-2"/>'),
  "E_discrete_bend_only+edge_eq": dict(
     option='<option timestep="0.002" integrator="discrete" solver="CG" tolerance="1e-6" iterations="200"/>',
     inner='<contact internal="false" selfcollide="auto" solref="0.01 1" solimp=".95 .99 .0001"/>'
           '<edge equality="true" damping="0.1"/>'
           '<elasticity young="3e5" poisson="0" thickness="8e-3" elastic2d="bend" damping="0.02"/>'),
  "F_discrete_vert_eq(poncho style)": dict(
     option='<option timestep="0.002" integrator="discrete" solver="CG" tolerance="1e-6" iterations="200"/>',
     inner='<contact internal="false" selfcollide="auto" solref="0.005 1"/>'
           '<edge equality="vert" damping="0.1"/>'
           '<elasticity young="3e5" poisson="0" thickness="8e-3" elastic2d="bend" damping="0.02"/>'),
  "G_discrete_native_passive_contact": dict(
     option='<option timestep="0.002" integrator="discrete" solver="CG" tolerance="1e-6" iterations="400"/>',
     inner='<contact internal="false" selfcollide="auto" passive="true" solref="0.01 1" solimp=".95 .99 .0001"/>'
           '<elasticity young="2e4" poisson="0.2" thickness="1e-3" elastic2d="both" damping="1e-2"/>'),
  "H_ipc_flag_exists": dict(
     option='<option timestep="0.005" integrator="discrete" solver="CG" tolerance="1e-5" iterations="150"><flag ipc="enable"/></option>',
     inner='<contact internal="false" selfcollide="auto"/>'
           '<elasticity young="2e4" poisson="0.2" thickness="1e-3" elastic2d="both" damping="1e-2"/>'),
}

nx, ny, sp, radius = 12, 16, 0.035, 0.004
sim_s = 4.0
for name, c in CASES.items():
    xml = BASE.format(option=c["option"], inner=c["inner"], nx=nx, ny=ny, sp=sp, radius=radius)
    xml = xml.replace("<mujoco>", "<mujoco>" + c.get("ext", ""), 1)
    try:
        m = mujoco.MjModel.from_xml_string(xml)
        d = mujoco.MjData(m)
    except Exception as e:
        print(f"[{name}] LOAD FAIL: {str(e).splitlines()[0][:200]}")
        continue
    n = int(sim_s / m.opt.timestep)
    t0 = time.perf_counter(); status = "ok"
    try:
        for i in range(n):
            mujoco.mj_step(m, d)
            if d.warning.number.sum() or not np.isfinite(d.qpos).all():
                status = f"DIVERGED at t={d.time:.2f} warnings={d.warning.number.tolist()}"
                break
    except Exception as e:
        status = f"STEP FAIL: {str(e).splitlines()[0][:200]}"
    wall = time.perf_counter() - t0
    v = d.flexvert_xpos[:m.flex_vertnum[0]]
    print(f"[{name}] {status} | nv={m.nv} | {n/wall/1000 if wall else 0:.1f}k steps/s ({d.time/wall if wall else 0:.1f}x RT)"
          f" | z mean={v[:,2].mean():.3f} std={v[:,2].std():.4f} | |vel|max={np.abs(d.qvel).max():.3f} | ncon={d.ncon}")
