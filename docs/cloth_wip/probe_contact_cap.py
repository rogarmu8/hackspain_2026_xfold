"""Is the 50-contact cap the cause of the jitter? Compare support surfaces."""
import sys, time, re
sys.path.insert(0, "src/sim/src")
import numpy as np, mujoco
from xfold.shirt import ShirtParams, flexcomp_xml, required_option, vertices

SCENE = """<mujoco>
  <option timestep="0.002" {opt}/>
  <size memory="200M"/>
  <worldbody>
    <geom name="floor" type="plane" size="2 2 .1" friction="1.0"/>
    {bed}
    {flex}
  </worldbody>
</mujoco>"""

def tiles(nx, ny, hx=0.45, hy=0.55, top=0.095, hz=0.06, overlap=0.0, stagger=0.0, gap=0.0, bodies=False):
    out = []; tx, ty = hx / nx, hy / ny
    for i in range(nx):
        for j in range(ny):
            k = (i + j) % 2
            z_top = top - stagger * k
            g = (f'<geom type="box" size="{tx + overlap - gap:.4f} {ty + overlap - gap:.4f} {hz}" '
                 f'pos="{-hx + tx*(2*i+1):.4f} {-hy + ty*(2*j+1):.4f} {z_top - hz:.4f}" friction="1.0"/>')
            out.append(f'<body name="tile_{i}_{j}">{g}</body>' if bodies else g)
    return "\n".join(out)

def run(label, bed, model_kind="constraint", z0=0.15):
    p = ShirtParams(shape="rect", model=model_kind)
    flex = flexcomp_xml(p, pos=(0, 0, z0), yaw=0.2)
    opt = " ".join(f'{k}="{v}"' for k, v in required_option(p).items())
    m = mujoco.MjModel.from_xml_string(SCENE.format(opt=opt, bed=bed, flex=flex)); d = mujoco.MjData(m)
    hist = []; nc = []
    for i in range(2000):
        mujoco.mj_step(m, d)
        if i % 250 == 0:
            hist.append(round(float(np.abs(d.qvel).max()), 3)); nc.append(d.ncon)
    v = vertices(m, d, "shirt")
    top = 0.095 if "plane" not in label else 0.0
    print(f"{label:34s} ncon {nc} | vmax {hist} | z-top: mean {v[:,2].mean()-top:+.4f} min {v[:,2].min()-top:+.4f} std {v[:,2].std():.4f}", flush=True)

run("single box", tiles(1, 1))
run("3x4 tiles, one body each", tiles(3, 4, bodies=True))
run("3x4 bodies, gap 2mm", tiles(3, 4, gap=0.001, bodies=True))
run("3x4 bodies overlap3cm stag1mm", tiles(3, 4, overlap=0.03, stagger=0.001, bodies=True))
run("6x8 tiles, one body each", tiles(6, 8, bodies=True))
run("hybrid 3x4 bodies", tiles(3, 4, bodies=True), model_kind="hybrid")
run("hybrid 6x8 bodies", tiles(6, 8, bodies=True), model_kind="hybrid")
