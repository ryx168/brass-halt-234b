# Procedural cinematic train station - built entirely from Python in Blender 4.5.
# Usage: blender -b -P build_station.py -- [preview|final|anim [png]] [tag]
# Env overrides (used by the GitHub Actions pipeline):
#   STATION_ROOT      output root (default: the folder this script lives in)
#   STATION_RES       resolution percentage, e.g. 100
#   STATION_SAMPLES   Cycles samples
#   STATION_FRAMES    "a-b" frame sub-range for anim mode (disables resume)
import bpy, bmesh, math, random, sys, os
from mathutils import Vector

ROOT = (os.environ.get('STATION_ROOT') or os.path.dirname(os.path.abspath(__file__))).replace('\\', '/')
ARGS = sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
MODE = "final" if "final" in ARGS else "preview"
TAG = ARGS[-1] if ARGS and ARGS[-1] not in ('preview', 'final', 'anim', 'png') else '01'
random.seed(42)

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
coll = bpy.context.collection

# ----------------------------------------------------------------- helpers
def mat_new(name):
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree; nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    return m, nt, out

def node(nt, t, **props):
    n = nt.nodes.new(t)
    for k, v in props.items(): setattr(n, k, v)
    return n

def mesh_obj(name, bm, mat=None, loc=(0,0,0)):
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me); ob.location = loc
    coll.objects.link(ob)
    if mat: me.materials.append(mat)
    return ob

def smooth(ob):
    for p in ob.data.polygons: p.use_smooth = True

def box(name, center, dims, mat, rot=(0,0,0)):
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts: v.co = Vector((v.co.x*dims[0], v.co.y*dims[1], v.co.z*dims[2]))
    ob = mesh_obj(name, bm, mat, center); ob.rotation_euler = rot
    return ob

def cyl(name, center, r, h, mat, segs=32, rot=(0,0,0), r2=None, caps=True):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=caps, segments=segs, radius1=r, radius2=(r if r2 is None else r2), depth=h)
    ob = mesh_obj(name, bm, mat, center); ob.rotation_euler = rot
    smooth(ob); return ob

def sphere(name, center, r, mat):
    bm = bmesh.new(); bmesh.ops.create_uvsphere(bm, u_segments=24, v_segments=16, radius=r)
    ob = mesh_obj(name, bm, mat, center); smooth(ob); return ob

def torus(name, center, R, r, mat, rot=(0,0,0)):
    bpy.ops.mesh.primitive_torus_add(major_radius=R, minor_radius=r, major_segments=48, minor_segments=12, location=center, rotation=rot)
    ob = bpy.context.active_object; ob.name = name; ob.data.materials.append(mat); smooth(ob); return ob

def bevel(ob, width, segs=4):
    m = ob.modifiers.new('bevel', 'BEVEL'); m.width = width; m.segments = segs; m.limit_method = 'ANGLE'
    return m

def array(ob, count, offset):
    m = ob.modifiers.new('arr', 'ARRAY'); m.count = count
    m.use_relative_offset = False; m.use_constant_offset = True; m.constant_offset_displace = offset

def rect_profile(name, w, h):
    cu = bpy.data.curves.new(name, 'CURVE'); cu.dimensions = '2D'
    sp = cu.splines.new('POLY'); sp.points.add(3)
    for p, (x, y) in zip(sp.points, [(-w/2,-h/2),(w/2,-h/2),(w/2,h/2),(-w/2,h/2)]): p.co = (x, y, 0, 1)
    sp.use_cyclic_u = True
    ob = bpy.data.objects.new(name, cu); coll.objects.link(ob); ob.hide_render = True; ob.hide_viewport = True
    return ob

def sweep(name, points, profile, mat):
    cu = bpy.data.curves.new(name, 'CURVE'); cu.dimensions = '3D'
    cu.bevel_mode = 'OBJECT'; cu.bevel_object = profile; cu.use_fill_caps = True; cu.twist_mode = 'Z_UP'
    sp = cu.splines.new('POLY'); sp.points.add(len(points)-1)
    for p, c in zip(sp.points, points): p.co = (c[0], c[1], c[2], 1)
    ob = bpy.data.objects.new(name, cu); coll.objects.link(ob); cu.materials.append(mat)
    return ob

FONT = None
# Bahnschrift is a variable font and Blender mangles its glyphs; use static bold faces.
for fp in ["C:/Windows/Fonts/arialbd.ttf",
           "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
           "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"]:
    if os.path.exists(fp):
        FONT = bpy.data.fonts.load(fp); break

def text_obj(name, body, loc, rot, size, mat, extrude=0.01, align='CENTER'):
    cu = bpy.data.curves.new(name, 'FONT'); cu.body = body; cu.size = size; cu.extrude = extrude
    cu.align_x = align; cu.align_y = 'CENTER'
    if FONT: cu.font = FONT
    ob = bpy.data.objects.new(name, cu); ob.location = loc; ob.rotation_euler = rot
    coll.objects.link(ob); cu.materials.append(mat); return ob

def point_light(name, loc, energy, color, size=0.12):
    lt = bpy.data.lights.new(name, 'POINT'); lt.energy = energy; lt.color = color; lt.shadow_soft_size = size
    lo = bpy.data.objects.new(name, lt); lo.location = loc; coll.objects.link(lo); return lo

# ----------------------------------------------------------------- shaders (all code)
def principled(nt, out, **kw):
    p = node(nt, 'ShaderNodeBsdfPrincipled')
    for k, v in kw.items(): p.inputs[k].default_value = v
    nt.links.new(p.outputs[0], out.inputs['Surface']); return p

def coords(nt, which='Object'):
    tc = node(nt, 'ShaderNodeTexCoord'); return tc.outputs[which]

def mixcol(nt, fac, a, b, blend='MIX'):
    m = node(nt, 'ShaderNodeMix', data_type='RGBA', blend_type=blend)
    if hasattr(fac, 'links'): nt.links.new(fac, m.inputs[0])
    else: m.inputs[0].default_value = fac
    for sock, val in ((6, a), (7, b)):
        if hasattr(val, 'links'): nt.links.new(val, m.inputs[sock])
        else: m.inputs[sock].default_value = val
    return m.outputs[2]

def ramp(nt, fac, stops):
    r = node(nt, 'ShaderNodeValToRGB')
    el = r.color_ramp.elements
    while len(el) > 1: el.remove(el[-1])
    el[0].position = stops[0][0]; el[0].color = stops[0][1]
    for pos, col in stops[1:]:
        e = el.new(pos); e.color = col
    nt.links.new(fac, r.inputs['Fac']); return r

def noise(nt, vec, scale, detail=2.0, rough=0.5, dist=0.0):
    n = node(nt, 'ShaderNodeTexNoise'); n.inputs['Scale'].default_value = scale
    n.inputs['Detail'].default_value = detail; n.inputs['Roughness'].default_value = rough
    n.inputs['Distortion'].default_value = dist
    nt.links.new(vec, n.inputs['Vector']); return n

def bump(nt, height, strength, p, dist=0.02):
    b = node(nt, 'ShaderNodeBump'); b.inputs['Strength'].default_value = strength; b.inputs['Distance'].default_value = dist
    nt.links.new(height, b.inputs['Height']); nt.links.new(b.outputs[0], p.inputs['Normal']); return b

def math_node(nt, op, a, b=None):
    m = node(nt, 'ShaderNodeMath', operation=op)
    for i, v in enumerate((a, b)):
        if v is None: continue
        if hasattr(v, 'links'): nt.links.new(v, m.inputs[i])
        else: m.inputs[i].default_value = v
    return m.outputs[0]

def map_range(nt, val, tmin, tmax):
    r = node(nt, 'ShaderNodeMapRange'); r.inputs['To Min'].default_value = tmin; r.inputs['To Max'].default_value = tmax
    nt.links.new(val, r.inputs['Value']); return r.outputs[0]

# -- wet concrete platform with tile grooves and puddles
def mat_platform():
    m, nt, out = mat_new('platform_concrete')
    p = principled(nt, out)
    co = coords(nt)
    br = node(nt, 'ShaderNodeTexBrick', offset=0.5)
    br.inputs['Scale'].default_value = 1.0; br.inputs['Brick Width'].default_value = 0.9
    br.inputs['Row Height'].default_value = 0.6; br.inputs['Mortar Size'].default_value = 0.012
    br.inputs['Mortar Smooth'].default_value = 0.4
    br.inputs['Color1'].default_value = (0.52, 0.51, 0.48, 1); br.inputs['Color2'].default_value = (0.45, 0.44, 0.42, 1)
    br.inputs['Mortar'].default_value = (0.14, 0.14, 0.14, 1)
    nt.links.new(co, br.inputs['Vector'])
    grime = noise(nt, co, 0.35, 4, 0.6)
    gr = ramp(nt, grime.outputs['Fac'], [(0.3, (0.65,0.65,0.65,1)), (0.7, (1,1,1,1))])
    fine = noise(nt, co, 60, 3, 0.7)
    col = mixcol(nt, 1.0, br.outputs['Color'], gr.outputs['Color'], 'MULTIPLY')
    pud = noise(nt, co, 0.45, 3, 0.55)
    pm = ramp(nt, pud.outputs['Fac'], [(0.595, (0,0,0,1)), (0.635, (1,1,1,1))])
    wetcol = mixcol(nt, pm.outputs['Color'], col, (0.10, 0.10, 0.11, 1))
    nt.links.new(wetcol, p.inputs['Base Color'])
    nt.links.new(map_range(nt, pm.outputs['Color'], 0.55, 0.04), p.inputs['Roughness'])
    h = math_node(nt, 'ADD', br.outputs['Fac'], math_node(nt, 'MULTIPLY', fine.outputs['Fac'], 0.08))
    h = math_node(nt, 'MULTIPLY', h, -1)
    dry = math_node(nt, 'SUBTRACT', 1.0, pm.outputs['Color'])
    bump(nt, math_node(nt, 'MULTIPLY', h, dry), 0.5, p, 0.01)
    p.inputs['Specular IOR Level'].default_value = 0.6
    return m

def mat_ballast():
    m, nt, out = mat_new('ballast'); p = principled(nt, out, Roughness=0.95)
    co = coords(nt)
    vo = node(nt, 'ShaderNodeTexVoronoi', feature='DISTANCE_TO_EDGE'); vo.inputs['Scale'].default_value = 28
    nt.links.new(co, vo.inputs['Vector'])
    vc = node(nt, 'ShaderNodeTexVoronoi', feature='F1'); vc.inputs['Scale'].default_value = 28; nt.links.new(co, vc.inputs['Vector'])
    cr = ramp(nt, vc.outputs['Color'], [(0.0, (0.10,0.09,0.08,1)), (0.5, (0.22,0.20,0.18,1)), (1.0, (0.33,0.31,0.28,1))])
    dirt = noise(nt, co, 0.5, 3)
    dr = ramp(nt, dirt.outputs['Fac'], [(0.3, (0.35,0.3,0.25,1)), (0.7, (1,1,1,1))])
    nt.links.new(mixcol(nt, 1.0, cr.outputs['Color'], dr.outputs['Color'], 'MULTIPLY'), p.inputs['Base Color'])
    er = ramp(nt, vo.outputs['Distance'], [(0.0, (0,0,0,1)), (0.12, (1,1,1,1))])
    bump(nt, er.outputs['Color'], 0.9, p, 0.05)
    return m

def mat_paint_iron(name, base, rust_amt=0.35):
    m, nt, out = mat_new(name); p = principled(nt, out, Metallic=0.25, Roughness=0.45)
    co = coords(nt)
    n1 = noise(nt, co, 3.0, 5, 0.65)
    rr = ramp(nt, n1.outputs['Fac'], [(0.55 - rust_amt*0.25, (0,0,0,1)), (0.75, (1,1,1,1))])
    nt.links.new(mixcol(nt, rr.outputs['Color'], base, (0.20, 0.09, 0.04, 1)), p.inputs['Base Color'])
    nt.links.new(map_range(nt, rr.outputs['Color'], 0.38, 0.85), p.inputs['Roughness'])
    n2 = noise(nt, co, 40, 3, 0.6); bump(nt, n2.outputs['Fac'], 0.15, p, 0.01)
    return m

def mat_steel():
    m, nt, out = mat_new('rail_steel'); p = principled(nt, out, Metallic=1.0, Roughness=0.22, **{'Base Color': (0.62,0.62,0.6,1)})
    co = coords(nt); n = noise(nt, co, 8, 3)
    nt.links.new(map_range(nt, n.outputs['Fac'], 0.15, 0.45), p.inputs['Roughness'])
    return m

def mat_brick():
    m, nt, out = mat_new('brick_wall'); p = principled(nt, out, Roughness=0.85)
    co = coords(nt)
    br = node(nt, 'ShaderNodeTexBrick'); br.inputs['Scale'].default_value = 1
    br.inputs['Brick Width'].default_value = 0.24; br.inputs['Row Height'].default_value = 0.075
    br.inputs['Mortar Size'].default_value = 0.008; br.inputs['Mortar Smooth'].default_value = 0.3
    br.inputs['Color1'].default_value = (0.30, 0.12, 0.08, 1); br.inputs['Color2'].default_value = (0.20, 0.09, 0.07, 1)
    br.inputs['Mortar'].default_value = (0.25, 0.23, 0.2, 1)
    mp = node(nt, 'ShaderNodeMapping'); mp.inputs['Rotation'].default_value = (0, 0, math.radians(90))
    nt.links.new(co, mp.inputs['Vector']); nt.links.new(mp.outputs[0], br.inputs['Vector'])
    soot = noise(nt, co, 0.25, 4, 0.7)
    sr = ramp(nt, soot.outputs['Fac'], [(0.35, (0.25,0.22,0.2,1)), (0.75, (1,1,1,1))])
    nt.links.new(mixcol(nt, 1.0, br.outputs['Color'], sr.outputs['Color'], 'MULTIPLY'), p.inputs['Base Color'])
    bump(nt, math_node(nt, 'SUBTRACT', 1.0, br.outputs['Fac']), 0.6, p, 0.02)
    return m

def mat_roof_glass():
    m, nt, out = mat_new('roof_glass')
    uv = coords(nt, 'UV')
    br = node(nt, 'ShaderNodeTexBrick', offset=0.0); br.inputs['Scale'].default_value = 1
    br.inputs['Brick Width'].default_value = 1.6; br.inputs['Row Height'].default_value = 2.5
    br.inputs['Mortar Size'].default_value = 0.05; br.inputs['Mortar Smooth'].default_value = 0.0
    nt.links.new(uv, br.inputs['Vector'])
    glass = node(nt, 'ShaderNodeBsdfGlass'); glass.inputs['Roughness'].default_value = 0.12
    glass.inputs['Color'].default_value = (0.78, 0.86, 0.82, 1)
    frame = node(nt, 'ShaderNodeBsdfPrincipled'); frame.inputs['Base Color'].default_value = (0.05,0.06,0.05,1)
    frame.inputs['Metallic'].default_value = 0.4; frame.inputs['Roughness'].default_value = 0.5
    grime = noise(nt, uv, 2.0, 4, 0.7)
    gr = ramp(nt, grime.outputs['Fac'], [(0.45, (0,0,0,1)), (0.8, (1,1,1,1))])
    dif = node(nt, 'ShaderNodeBsdfTranslucent'); dif.inputs['Color'].default_value = (0.5,0.5,0.45,1)
    mix1 = node(nt, 'ShaderNodeMixShader'); nt.links.new(gr.outputs['Color'], mix1.inputs[0])
    nt.links.new(glass.outputs[0], mix1.inputs[1]); nt.links.new(dif.outputs[0], mix1.inputs[2])
    mix2 = node(nt, 'ShaderNodeMixShader'); nt.links.new(br.outputs['Fac'], mix2.inputs[0])
    nt.links.new(mix1.outputs[0], mix2.inputs[1]); nt.links.new(frame.outputs[0], mix2.inputs[2])
    nt.links.new(mix2.outputs[0], out.inputs['Surface'])
    return m

def mat_wood():
    m, nt, out = mat_new('bench_wood'); p = principled(nt, out, Roughness=0.4)
    co = coords(nt)
    mp = node(nt, 'ShaderNodeMapping'); mp.inputs['Scale'].default_value = (1, 12, 1); nt.links.new(co, mp.inputs['Vector'])
    w = node(nt, 'ShaderNodeTexWave', wave_type='BANDS', bands_direction='Y'); w.inputs['Scale'].default_value = 1.5
    w.inputs['Distortion'].default_value = 3; w.inputs['Detail'].default_value = 3
    nt.links.new(mp.outputs[0], w.inputs['Vector'])
    r = ramp(nt, w.outputs['Fac'], [(0.0, (0.16,0.08,0.04,1)), (0.5, (0.30,0.16,0.07,1)), (1.0, (0.22,0.11,0.05,1))])
    nt.links.new(r.outputs['Color'], p.inputs['Base Color'])
    bump(nt, w.outputs['Fac'], 0.25, p, 0.005)
    p.inputs['Coat Weight'].default_value = 0.4
    return m

def mat_simple(name, color, rough=0.5, metal=0.0, coat=0.0):
    m, nt, out = mat_new(name)
    p = principled(nt, out, Roughness=rough, Metallic=metal, **{'Base Color': color})
    p.inputs['Coat Weight'].default_value = coat
    return m

def mat_emission(name, color, strength):
    m, nt, out = mat_new(name); e = node(nt, 'ShaderNodeEmission')
    e.inputs['Color'].default_value = color; e.inputs['Strength'].default_value = strength
    nt.links.new(e.outputs[0], out.inputs['Surface']); return m

def mat_train_window():
    m, nt, out = mat_new('train_window')
    lf = node(nt, 'ShaderNodeLayerWeight'); lf.inputs['Blend'].default_value = 0.35
    gl = node(nt, 'ShaderNodeBsdfGlossy'); gl.inputs['Roughness'].default_value = 0.05
    em = node(nt, 'ShaderNodeEmission'); em.inputs['Color'].default_value = (1.0, 0.72, 0.42, 1); em.inputs['Strength'].default_value = 2.5
    mx = node(nt, 'ShaderNodeMixShader'); nt.links.new(lf.outputs['Fresnel'], mx.inputs[0])
    nt.links.new(em.outputs[0], mx.inputs[1]); nt.links.new(gl.outputs[0], mx.inputs[2])
    nt.links.new(mx.outputs[0], out.inputs['Surface']); return m

def mat_train_paint():
    m, nt, out = mat_new('train_paint')
    p = principled(nt, out, Roughness=0.35, Metallic=0.1)
    p.inputs['Coat Weight'].default_value = 1.0; p.inputs['Coat Roughness'].default_value = 0.08
    co = coords(nt); n = noise(nt, co, 2, 4, 0.7)
    r = ramp(nt, n.outputs['Fac'], [(0.4, (0.6,0.6,0.6,1)), (0.7, (1,1,1,1))])
    nt.links.new(mixcol(nt, 1.0, (0.32,0.03,0.03,1), r.outputs['Color'], 'MULTIPLY'), p.inputs['Base Color'])
    return m

M = dict(
    platform=mat_platform(), ballast=mat_ballast(), steel=mat_steel(), brick=mat_brick(), glass=mat_roof_glass(),
    wood=mat_wood(), iron=mat_paint_iron('iron_green', (0.04, 0.10, 0.07, 1)), iron_dark=mat_paint_iron('iron_dark', (0.03,0.03,0.035,1), 0.2),
    sleeper=mat_simple('sleeper', (0.08,0.06,0.045,1), 0.9), tactile=mat_simple('tactile', (0.45,0.42,0.3,1), 0.7),
    yellow=mat_simple('yellow_line', (0.9,0.7,0.08,1), 0.45), navy=mat_simple('sign_navy', (0.02,0.06,0.18,1), 0.4),
    white_emit=mat_emission('sign_text', (1,1,1,1), 3.0), bulb=mat_emission('bulb', (1.0,0.72,0.42,1), 40),
    lamp_shade=mat_simple('lamp_shade', (0.05,0.12,0.09,1), 0.35, 0.3), shade_in=mat_simple('shade_in', (0.95,0.93,0.85,1), 0.5),
    train=mat_train_paint(), window=mat_train_window(), gold=mat_simple('gold', (0.85,0.6,0.2,1), 0.3, 1.0),
    black=mat_simple('black_rubber', (0.02,0.02,0.02,1), 0.8), clock=mat_emission('clock_face', (1,0.97,0.9,1), 1.5),
    headlight=mat_emission('headlight', (1,0.95,0.85,1), 60), lantern=mat_emission('lantern', (1,0.75,0.45,1), 12),
    concrete=mat_simple('concrete_plain', (0.35,0.34,0.32,1), 0.8),
    cream=mat_simple('cream_paint', (0.85,0.78,0.6,1), 0.5),
)

# ----------------------------------------------------------------- geometry
Y0, Y1 = -30.0, 90.0      # shed extent
PY0, PY1 = -20.0, 80.0    # platform extent
PLAT_Z = 1.5
WALL_X = 10.0

# ground + ballast + track
box('ground', (0, (Y0+Y1)/2, -0.1), (30, Y1-Y0+20, 0.2), M['ballast'])
for tx in (-6.0, 6.0):
    box(f'ballast_{tx}', (tx, (Y0+Y1)/2, 0.15), (4.2, Y1-Y0, 0.3), M['ballast'])
    slp = box(f'sleeper_{tx}', (tx, Y0, 0.375), (2.5, 0.24, 0.15), M['sleeper']); array(slp, int((Y1-Y0)/0.62)+1, (0, 0.62, 0))
    for rx in (-0.7175, 0.7175):
        box(f'railfoot_{tx}_{rx}', (tx+rx, (Y0+Y1)/2, 0.465), (0.15, Y1-Y0, 0.03), M['steel'])
        r = box(f'rail_{tx}_{rx}', (tx+rx, (Y0+Y1)/2, 0.54), (0.07, Y1-Y0, 0.14), M['steel']); bevel(r, 0.015, 2)

# platform
box('platform', (0, (PY0+PY1)/2, PLAT_Z/2), (8.0, PY1-PY0, PLAT_Z), M['platform'])
box('platform_face_A', (-4.0, (PY0+PY1)/2, PLAT_Z/2-0.05), (0.12, PY1-PY0, PLAT_Z-0.1), M['brick'])
box('platform_face_B', (4.0, (PY0+PY1)/2, PLAT_Z/2-0.05), (0.12, PY1-PY0, PLAT_Z-0.1), M['brick'])
for sx in (-1, 1):
    # edge coping strips: 5 mm proud of the slab so no face is coplanar with the platform top
    cop = box(f'coping_{sx}', (sx*3.85, (PY0+PY1)/2, PLAT_Z-0.035), (0.5, PY1-PY0, 0.08), M['concrete']); bevel(cop, 0.02, 2)
    box(f'tactile_{sx}', (sx*3.35, (PY0+PY1)/2, PLAT_Z+0.006), (0.5, PY1-PY0, 0.012), M['tactile'])
    box(f'yellow_{sx}', (sx*3.0, (PY0+PY1)/2, PLAT_Z+0.002), (0.1, PY1-PY0, 0.004), M['yellow'])
box('platform_end', (0, PY0-0.5, PLAT_Z/2), (8.0, 1.0, PLAT_Z), M['brick'])

# walls with pilasters, cornice and wall lanterns
for sx in (-1, 1):
    box(f'wall_{sx}', (sx*(WALL_X+0.4), (Y0+Y1)/2, 4.0), (0.8, Y1-Y0, 8.0), M['brick'])
    box(f'cornice_{sx}', (sx*(WALL_X+0.3), (Y0+Y1)/2, 7.9), (1.1, Y1-Y0, 0.3), M['concrete'])
    y = Y0 + 4
    while y < Y1:
        box(f'pilaster_{sx}_{y:.0f}', (sx*(WALL_X-0.15), y, 3.8), (0.5, 0.9, 7.6), M['brick'])
        box(f'lantern_{sx}_{y:.0f}', (sx*(WALL_X-0.45), y, 4.2), (0.2, 0.3, 0.45), M['lantern'])
        box(f'lantern_cap_{sx}_{y:.0f}', (sx*(WALL_X-0.45), y, 4.48), (0.3, 0.4, 0.06), M['iron_dark'])
        point_light(f'lantern_lt_{sx}_{y:.0f}', (sx*(WALL_X-0.7), y, 4.2), 120, (1.0, 0.72, 0.45), 0.15)
        y += 8

# arch roof: ribs, lattice, purlins, glazed shell
A, B, Z0 = WALL_X, 6.0, 8.0
def arch(t, a=A, b=B):
    th = math.pi * (1 - t)
    return (a*math.cos(th), Z0 + b*math.sin(th))

rib_prof = rect_profile('rib_prof', 0.28, 0.55)
lat_prof = rect_profile('lat_prof', 0.08, 0.08)
N = 48
y = Y0 + 4
while y <= Y1:
    pts = [(arch(i/N)[0], y, arch(i/N)[1]) for i in range(N+1)]
    sweep(f'rib_{y:.0f}', pts, rib_prof, M['iron'])
    inner = [(arch(i/N, A-0.9, B-0.9)[0], y, arch(i/N, A-0.9, B-0.9)[1]) for i in range(N+1)]
    sweep(f'rib_in_{y:.0f}', inner[3:-3], lat_prof, M['iron'])
    zig = [pts[i] if i % 2 == 0 else inner[i] for i in range(3, N-2)]
    sweep(f'rib_zig_{y:.0f}', zig, lat_prof, M['iron'])
    y += 8

for k in range(1, 12):
    t = k/12; x, z = arch(t, A+0.1, B+0.1)
    x2, z2 = arch(t+0.001, A+0.1, B+0.1)
    ang = -math.atan2(z2-z, x2-x)
    box(f'purlin_{k}', (x, (Y0+Y1)/2, z), (0.3, Y1-Y0, 0.14), M['iron'], rot=(0, ang, 0))

# glazed shell with UVs (u = arc length in m, v = y in m)
bm = bmesh.new(); uvl = bm.loops.layers.uv.new()
NS, NY = 64, 16
arcpts = [arch(i/NS, A+0.4, B+0.4) for i in range(NS+1)]
arclen = [0.0]
for i in range(1, NS+1):
    arclen.append(arclen[-1] + math.dist(arcpts[i], arcpts[i-1]))
verts = []
for j in range(NY+1):
    yy = Y0 + (Y1-Y0)*j/NY
    verts.append([bm.verts.new((arcpts[i][0], yy, arcpts[i][1])) for i in range(NS+1)])
index_of = {}
for j in range(NY+1):
    for i in range(NS+1):
        index_of[verts[j][i]] = (i, j)
for j in range(NY):
    for i in range(NS):
        f = bm.faces.new((verts[j][i], verts[j][i+1], verts[j+1][i+1], verts[j+1][i]))
        for lp in f.loops:
            ii, jj = index_of[lp.vert]
            lp[uvl].uv = (arclen[ii], Y0 + (Y1-Y0)*jj/NY)
shell = mesh_obj('roof_glass', bm, M['glass']); smooth(shell)

# portal frames on the platform: column pairs + cross beams + longitudinal beams
COL_X = 2.9
for sx in (-1, 1):
    box(f'longbeam_{sx}', (sx*COL_X, (PY0+PY1)/2, 6.5), (0.25, PY1-PY0, 0.35), M['iron'])
y = PY0 + 4
lamp_ys = []
while y < PY1:
    for sx in (-1, 1):
        x = sx*COL_X
        cyl(f'col_{sx}_{y:.0f}', (x, y, PLAT_Z + 2.5), 0.16, 5.0, M['iron'])
        cyl(f'colbase_{sx}_{y:.0f}', (x, y, PLAT_Z + 0.3), 0.28, 0.6, M['iron'], r2=0.2)
        box(f'colplinth_{sx}_{y:.0f}', (x, y, PLAT_Z + 0.06), (0.7, 0.7, 0.12), M['iron'])
        cyl(f'colcap_{sx}_{y:.0f}', (x, y, PLAT_Z + 4.95), 0.2, 0.3, M['iron'], r2=0.32)
        torus(f'colring_{sx}_{y:.0f}', (x, y, PLAT_Z + 3.4), 0.17, 0.03, M['gold'])
        box(f'brace_{sx}_{y:.0f}', (x - sx*0.5, y, 6.0), (1.1, 0.08, 0.08), M['iron'], rot=(0, sx*math.radians(45), 0))
    box(f'crossbeam_{y:.0f}', (0, y, 6.5), (2*COL_X+0.25, 0.25, 0.35), M['iron'])
    lamp_ys.append(y)
    y += 8

# pendant lamps
for y in lamp_ys:
    cyl(f'lamp_rod_{y:.0f}', (0, y, 5.95), 0.02, 0.8, M['iron_dark'])
    sh = cyl(f'lamp_shade_{y:.0f}', (0, y, 5.35), 0.48, 0.4, M['lamp_shade'], r2=0.07, caps=False)
    sm = sh.modifiers.new('sol', 'SOLIDIFY'); sm.thickness = 0.01; sm.use_rim = True
    sh.data.materials.append(M['shade_in']); sm.material_offset = 1
    sphere(f'bulb_{y:.0f}', (0, y, 5.12), 0.09, M['bulb'])
    point_light(f'lamp_lt_{y:.0f}', (0, y, 5.05), 1800, (1.0, 0.70, 0.42))

# hanging signs and the clock
def hang_sign(y, text, size, w):
    for sx in (-1, 1):
        cyl(f'sign_rod_{y:.0f}_{sx}', (sx*(w/2-0.2), y, 5.7), 0.015, 1.3, M['iron_dark'])
    b = box(f'sign_{y:.0f}', (0, y, 4.75), (w, 0.08, 0.6), M['navy']); bevel(b, 0.02, 2)
    box(f'sign_frame_{y:.0f}', (0, y, 4.75), (w+0.06, 0.06, 0.66), M['gold'])
    for sy, rz in ((-0.05, 0), (0.05, math.pi)):
        text_obj(f'sign_text_{y:.0f}_{sy}', text, (0, y+sy, 4.75), (math.radians(90), 0, rz), size, M['white_emit'], 0.004)

hang_sign(lamp_ys[1], "KINGSBRIDGE", 0.36, 3.6)
hang_sign(lamp_ys[3], "PLATFORM 3   -   WAY OUT", 0.26, 4.0)
hang_sign(lamp_ys[5], "KINGSBRIDGE", 0.36, 3.6)
hang_sign(lamp_ys[7], "TICKETS   -   TAXIS", 0.26, 3.4)
cy = lamp_ys[2]
cyl('clock_rod', (0, cy, 5.85), 0.02, 1.0, M['iron_dark'])
cyl('clock_body', (0, cy, 4.8), 0.55, 0.16, M['iron_dark'], rot=(math.radians(90), 0, 0))
for sy in (-0.085, 0.085):
    cyl(f'clock_face_{sy}', (0, cy+sy, 4.8), 0.48, 0.01, M['clock'], rot=(math.radians(90), 0, 0))
    box(f'clock_h_{sy}', (0, cy+sy*1.2, 4.8+0.1), (0.04, 0.01, 0.28), M['black'], rot=(0, math.radians(30), 0))
    box(f'clock_m_{sy}', (0, cy+sy*1.2, 4.8+0.15), (0.03, 0.01, 0.42), M['black'], rot=(0, math.radians(-100), 0))
torus('clock_rim', (0, cy, 4.8), 0.52, 0.035, M['gold'], rot=(math.radians(90), 0, 0))

# benches, bins
def bench(y, x, face):
    for dy in (-0.8, 0.8):
        box(f'bench_end_{y:.0f}_{dy}', (x, y+dy, PLAT_Z+0.25), (0.5, 0.06, 0.5), M['iron_dark'])
        box(f'bench_back_{y:.0f}_{dy}', (x - face*0.22, y+dy, PLAT_Z+0.75), (0.06, 0.06, 0.55), M['iron_dark'], rot=(0, -face*math.radians(12), 0))
    for i in range(4):
        box(f'bench_seat_{y:.0f}_{i}', (x - face*0.18 + face*i*0.12, y, PLAT_Z+0.52), (0.1, 1.8, 0.04), M['wood'])
    for i in range(3):
        box(f'bench_bk_{y:.0f}_{i}', (x - face*(0.24+i*0.03), y, PLAT_Z+0.62+i*0.14), (0.04, 1.8, 0.1), M['wood'], rot=(0, -face*math.radians(12), 0))
for i, y in enumerate([PY0+11, PY0+28, PY0+46, PY0+64, PY0+82]):
    sx = 1 if i % 2 == 0 else -1
    bench(y, sx*2.2, -sx)
    cyl(f'bin_{y:.0f}', (-sx*1.9, y+2.2, PLAT_Z+0.45), 0.25, 0.9, M['iron'])
    cyl(f'bin_lid_{y:.0f}', (-sx*1.9, y+2.2, PLAT_Z+0.92), 0.28, 0.06, M['iron_dark'])

# luggage trolley in the mid-ground, by the right-hand platform edge
TRX, TRY = 2.35, -3.0
box('trolley_bed', (TRX, TRY, PLAT_Z+0.35), (0.9, 1.6, 0.05), M['iron_dark'])
box('trolley_bar', (TRX, TRY+0.75, PLAT_Z+0.75), (0.9, 0.04, 0.9), M['iron_dark'])
for dx, dy in ((-0.4,-0.6),(0.4,-0.6),(-0.4,0.6),(0.4,0.6)):
    cyl(f'trolley_wheel_{dx}_{dy}', (TRX+dx, TRY+dy, PLAT_Z+0.17), 0.17, 0.08, M['black'], rot=(0, math.radians(90), 0))
case_cols = [(0.35,0.2,0.1,1),(0.1,0.12,0.2,1),(0.3,0.28,0.22,1)]
for i, (dx, dy, dz, w, l, h) in enumerate([(0,-0.2,0.6,0.7,0.5,0.45),(0,0.35,0.55,0.6,0.4,0.35),(0.05,0.0,1.0,0.5,0.9,0.3)]):
    c = box(f'suitcase_{i}', (TRX+dx, TRY+dy, PLAT_Z+dz), (w, l, h), mat_simple(f'case_{i}', case_cols[i], 0.5)); bevel(c, 0.03, 3)

# station name on the walls
text_obj('wall_name', "KINGSBRIDGE  CENTRAL", (WALL_X-0.45, 30, 5.6), (math.radians(90), 0, math.radians(-90)), 1.1, M['cream'], 0.03)
text_obj('wall_name2', "KINGSBRIDGE  CENTRAL", (-(WALL_X-0.45), 50, 5.6), (math.radians(90), 0, math.radians(90)), 1.1, M['cream'], 0.03)

# ----------------------------------------------------------------- the train (track A, x=-6)
TX = -6.0
RAIL_TOP = 0.61
def carriage(yc, name, front=False):
    body = box(f'{name}_body', (TX, yc, 3.05), (2.9, 22.0, 3.1), M['train']); bevel(body, 0.42, 6)
    roof = box(f'{name}_roof', (TX, yc, 4.65), (2.6, 21.6, 0.3), M['iron_dark']); bevel(roof, 0.14, 4)
    box(f'{name}_skirt', (TX, yc, 1.45), (2.7, 21.6, 0.3), M['iron_dark'])
    for sx in (-1, 1):
        box(f'{name}_stripe_{sx}', (TX+sx*1.46, yc, 2.25), (0.02, 21.8, 0.12), M['gold'])
        box(f'{name}_stripe2_{sx}', (TX+sx*1.46, yc, 3.95), (0.02, 21.8, 0.06), M['gold'])
        for i in range(-4, 5):
            if i in (-4, 4):
                box(f'{name}_door_{sx}_{i}', (TX+sx*1.44, yc+i*2.2, 2.75), (0.06, 1.3, 2.3), M['iron_dark'])
                box(f'{name}_doorwin_{sx}_{i}', (TX+sx*1.47, yc+i*2.2, 3.2), (0.02, 0.8, 0.8), M['window'])
            else:
                box(f'{name}_win_{sx}_{i}', (TX+sx*1.47, yc+i*2.2, 3.15), (0.02, 1.4, 1.1), M['window'])
                box(f'{name}_winframe_{sx}_{i}', (TX+sx*1.465, yc+i*2.2, 3.15), (0.02, 1.52, 1.22), M['gold'])
    for by in (-7.0, 7.0):
        box(f'{name}_bogie_{by}', (TX, yc+by, 1.0), (2.2, 3.0, 0.5), M['iron_dark'])
        for wy in (-1.0, 1.0):
            for sx in (-1, 1):
                cyl(f'{name}_wheel_{by}_{wy}_{sx}', (TX+sx*0.75, yc+by+wy, RAIL_TOP+0.46), 0.46, 0.12, M['steel'], rot=(0, math.radians(90), 0))
            cyl(f'{name}_axle_{by}_{wy}', (TX, yc+by+wy, RAIL_TOP+0.46), 0.07, 1.6, M['steel'], rot=(0, math.radians(90), 0))
    if front:
        yf = yc - 11.0
        for sx in (-0.9, 0.9):
            cyl(f'{name}_headlamp_{sx}', (TX+sx, yf-0.02, 2.0), 0.18, 0.08, M['headlight'], rot=(math.radians(90), 0, 0))
            lt = bpy.data.lights.new(f'{name}_spot_{sx}', 'SPOT'); lt.energy = 2500; lt.color = (1, 0.95, 0.85)
            lt.spot_size = math.radians(40); lt.spot_blend = 0.6; lt.shadow_soft_size = 0.2
            lo = bpy.data.objects.new(lt.name, lt); lo.location = (TX+sx, yf-0.1, 2.0); lo.rotation_euler = (math.radians(90), 0, 0); coll.objects.link(lo)
        cyl(f'{name}_toplamp', (TX, yf-0.02, 4.2), 0.14, 0.08, M['headlight'], rot=(math.radians(90), 0, 0))
        box(f'{name}_buffer_beam', (TX, yf-0.1, 1.3), (2.6, 0.2, 0.4), M['iron_dark'])
        for sx in (-0.9, 0.9):
            cyl(f'{name}_buffer_{sx}', (TX+sx, yf-0.4, 1.3), 0.12, 0.5, M['steel'], rot=(math.radians(90), 0, 0))
        text_obj(f'{name}_num', "4 4 7", (TX, yf-0.03, 3.4), (math.radians(90), 0, 0), 0.32, M['gold'], 0.01)
carriage(16.0, 'car1', front=True)
carriage(39.0, 'car2')
carriage(62.0, 'car3')
train_root = bpy.data.objects.new('train_root', None); coll.objects.link(train_root)
for ob in list(bpy.data.objects):
    if ob.name.startswith('car') and ob is not train_root: ob.parent = train_root

# ----------------------------------------------------------------- lighting / world / camera
world = bpy.data.worlds.new('World'); scene.world = world; world.use_nodes = True
wn = world.node_tree; wn.nodes.clear()
wout = wn.nodes.new('ShaderNodeOutputWorld')
sky = wn.nodes.new('ShaderNodeTexSky'); sky.sky_type = 'NISHITA'; sky.sun_disc = False
sky.sun_elevation = math.radians(3.0); sky.sun_rotation = math.radians(180); sky.dust_density = 3.0; sky.air_density = 1.2; sky.ozone_density = 1.5
bg = wn.nodes.new('ShaderNodeBackground'); bg.inputs['Strength'].default_value = 0.3
wn.links.new(sky.outputs[0], bg.inputs['Color']); wn.links.new(bg.outputs[0], wout.inputs['Surface'])
vol = wn.nodes.new('ShaderNodeVolumeScatter'); vol.inputs['Density'].default_value = 0.009
vol.inputs['Anisotropy'].default_value = 0.45; vol.inputs['Color'].default_value = (0.8, 0.88, 1.0, 1)
wn.links.new(vol.outputs[0], wout.inputs['Volume'])

sun = bpy.data.lights.new('sun', 'SUN'); sun.energy = 6.0; sun.color = (1.0, 0.55, 0.28); sun.angle = math.radians(1.2)
so = bpy.data.objects.new('sun', sun); so.rotation_euler = (math.radians(-(90-4)), 0, 0); coll.objects.link(so)

cam_d = bpy.data.cameras.new('cam'); cam_d.lens = 30; cam_d.sensor_width = 36
cam_d.dof.use_dof = True; cam_d.dof.focus_distance = 16; cam_d.dof.aperture_fstop = 2.8
cam = bpy.data.objects.new('cam', cam_d); cam.location = (0.7, -13.5, 2.3); cam.rotation_euler = (math.radians(88), 0, math.radians(1.5))
coll.objects.link(cam); scene.camera = cam

# ----------------------------------------------------------------- render settings
scene.render.engine = 'CYCLES'
scene.cycles.device = 'CPU'
scene.render.resolution_x, scene.render.resolution_y = 1920, 1080
if MODE == 'final':
    scene.render.resolution_percentage = 100; scene.cycles.samples = 320
else:
    scene.render.resolution_percentage = 50; scene.cycles.samples = 64
scene.cycles.use_adaptive_sampling = True; scene.cycles.adaptive_threshold = 0.02
scene.cycles.use_denoising = True; scene.cycles.denoiser = 'OPENIMAGEDENOISE'
scene.cycles.max_bounces = 8; scene.cycles.diffuse_bounces = 3; scene.cycles.glossy_bounces = 4
scene.cycles.transmission_bounces = 6; scene.cycles.volume_bounces = 0; scene.cycles.transparent_max_bounces = 8
scene.cycles.caustics_reflective = False; scene.cycles.caustics_refractive = False
scene.cycles.sample_clamp_indirect = 8.0; scene.cycles.blur_glossy = 1.0
scene.cycles.volume_step_rate = 1.0; scene.cycles.volume_max_steps = 256
scene.view_settings.view_transform = 'AgX'; scene.view_settings.look = 'AgX - Medium High Contrast'
scene.view_settings.exposure = 0.6
scene.render.image_settings.file_format = 'PNG'; scene.render.image_settings.color_depth = '16'

# compositor: bloom, subtle chromatic aberration, colour grade, vignette
scene.use_nodes = True; ct = scene.node_tree; ct.nodes.clear()
rl = ct.nodes.new('CompositorNodeRLayers'); comp = ct.nodes.new('CompositorNodeComposite')
glare = ct.nodes.new('CompositorNodeGlare')
try: glare.glare_type = 'BLOOM'
except Exception: glare.glare_type = 'FOG_GLOW'
for attr, val in (('threshold', 1.2), ('mix', -0.55), ('size', 8), ('quality', 'HIGH')):
    try: setattr(glare, attr, val)
    except Exception: pass
for sock, val in (('Threshold', 1.2), ('Strength', 0.18), ('Size', 0.6)):
    if sock in glare.inputs:
        try: glare.inputs[sock].default_value = val
        except Exception: pass
cb = ct.nodes.new('CompositorNodeColorBalance'); cb.correction_method = 'LIFT_GAMMA_GAIN'
cb.lift = (0.97, 0.985, 1.03); cb.gamma = (1.0, 1.0, 1.0); cb.gain = (1.06, 1.0, 0.94)
ld = ct.nodes.new('CompositorNodeLensdist'); ld.inputs['Dispersion'].default_value = 0.012
em = ct.nodes.new('CompositorNodeEllipseMask'); em.width = 1.5; em.height = 1.3
bl = ct.nodes.new('CompositorNodeBlur'); bl.filter_type = 'FAST_GAUSS'; bl.size_x = 400; bl.size_y = 400; bl.use_relative = False
mr = ct.nodes.new('CompositorNodeMapRange'); mr.inputs['From Min'].default_value = 0; mr.inputs['From Max'].default_value = 1
mr.inputs['To Min'].default_value = 0.55; mr.inputs['To Max'].default_value = 1.0
mul = ct.nodes.new('CompositorNodeMixRGB'); mul.blend_type = 'MULTIPLY'
ct.links.new(rl.outputs['Image'], glare.inputs['Image'])
ct.links.new(glare.outputs['Image'], cb.inputs['Image'])
ct.links.new(cb.outputs['Image'], ld.inputs['Image'])
ct.links.new(em.outputs['Mask'], bl.inputs['Image']); ct.links.new(bl.outputs['Image'], mr.inputs['Value'])
ct.links.new(ld.outputs['Image'], mul.inputs[1]); ct.links.new(mr.outputs['Value'], mul.inputs[2])
ct.links.new(mul.outputs['Image'], comp.inputs['Image'])

# ----------------------------------------------------------------- save + render
os.makedirs(ROOT + '/renders', exist_ok=True)
if "anim" in ARGS:
    # 4 s dolly down the platform while the train pulls out
    F0, F1 = 1, 96
    scene.frame_start, scene.frame_end = F0, F1; scene.render.fps = 24
    cam.location = (0.9, -17.0, 2.35); cam.rotation_euler = (math.radians(88), 0, math.radians(2.5)); cam.keyframe_insert('location', frame=F0); cam.keyframe_insert('rotation_euler', frame=F0)
    cam.location = (0.5, -9.5, 2.2); cam.rotation_euler = (math.radians(88.5), 0, math.radians(0.5)); cam.keyframe_insert('location', frame=F1); cam.keyframe_insert('rotation_euler', frame=F1)
    train_root.location = (0, 0, 0); train_root.keyframe_insert('location', frame=F0)
    train_root.location = (0, 7.0, 0); train_root.keyframe_insert('location', frame=F1)
    for ob in (cam, train_root):
        for fc in ob.animation_data.action.fcurves:
            for kp in fc.keyframe_points: kp.interpolation = 'LINEAR'
    scene.render.resolution_percentage = 50; scene.cycles.samples = 40
    if 'png' in ARGS:
        # PNG frame sequence: survives a killed run; assemble with ffmpeg afterwards
        scene.render.image_settings.file_format = 'PNG'; scene.render.image_settings.color_depth = '8'
        os.makedirs(f'{ROOT}/renders/fly_{TAG}', exist_ok=True)
        scene.render.filepath = f'{ROOT}/renders/fly_{TAG}/f_'
        if os.environ.get('STATION_FRAMES'):
            a, b = os.environ['STATION_FRAMES'].split('-'); scene.frame_start, scene.frame_end = int(a), int(b)
            print('FRAME RANGE', scene.frame_start, scene.frame_end)
        else:
            done = sorted(int(f[2:6]) for f in os.listdir(f'{ROOT}/renders/fly_{TAG}') if f.startswith('f_') and f.endswith('.png'))
            if done:
                scene.frame_start = max(F0, max(done) + 1); print('RESUME from frame', scene.frame_start)
    else:
        scene.render.image_settings.file_format = 'FFMPEG'; scene.render.image_settings.color_depth = '8'
        scene.render.ffmpeg.format = 'MPEG4'; scene.render.ffmpeg.codec = 'H264'; scene.render.ffmpeg.constant_rate_factor = 'HIGH'
        scene.render.filepath = f'{ROOT}/renders/flythrough_{TAG}_'
    if os.environ.get('STATION_RES'): scene.render.resolution_percentage = int(os.environ['STATION_RES'])
    if os.environ.get('STATION_SAMPLES'): scene.cycles.samples = int(os.environ['STATION_SAMPLES'])
    bpy.ops.wm.save_as_mainfile(filepath=ROOT + '/station_anim.blend')
    bpy.ops.render.render(animation=True)
    print('RENDERED ANIMATION', scene.render.filepath)
else:
    if os.environ.get('STATION_RES'): scene.render.resolution_percentage = int(os.environ['STATION_RES'])
    if os.environ.get('STATION_SAMPLES'): scene.cycles.samples = int(os.environ['STATION_SAMPLES'])
    bpy.ops.wm.save_as_mainfile(filepath=ROOT + '/station.blend')
    scene.render.filepath = f'{ROOT}/renders/{MODE}_{TAG}.png'
    bpy.ops.render.render(write_still=True)
    print('RENDERED', scene.render.filepath, 'objects:', len(bpy.data.objects))
