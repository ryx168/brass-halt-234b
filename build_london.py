# London terminus at dusk - a Barlow-style single-span Gothic trainshed (after St Pancras),
# built entirely from Python in Blender 4.5: geometry, shaders, lights, camera, grade.
# Usage: blender -b -P build_london.py -- [preview|final|anim [png]] [tag]
# Env overrides (same as build_station.py): STATION_ROOT, STATION_RES, STATION_SAMPLES, STATION_FRAMES
import bpy, bmesh, math, random, sys, os
from mathutils import Vector

ROOT = (os.environ.get('STATION_ROOT') or os.path.dirname(os.path.abspath(__file__))).replace('\\', '/')
ARGS = sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
MODE = "final" if "final" in ARGS else "preview"
TAG = ARGS[-1] if ARGS and ARGS[-1] not in ('preview', 'final', 'anim', 'png') else '01'
random.seed(7)
R = math.radians

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
coll = bpy.context.collection

# ================================================================= helpers
def mat_new(name):
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree; nt.nodes.clear()
    return m, nt, nt.nodes.new('ShaderNodeOutputMaterial')

def node(nt, t, **props):
    n = nt.nodes.new(t)
    for k, v in props.items(): setattr(n, k, v)
    return n

def mesh_obj(name, bm, mat=None, loc=(0, 0, 0)):
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me); ob.location = loc
    coll.objects.link(ob)
    if mat: me.materials.append(mat)
    return ob

def smooth(ob):
    for p in ob.data.polygons: p.use_smooth = True

def box(name, center, dims, mat, rot=(0, 0, 0)):
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts: v.co = Vector((v.co.x*dims[0], v.co.y*dims[1], v.co.z*dims[2]))
    ob = mesh_obj(name, bm, mat, center); ob.rotation_euler = rot
    return ob

def box_span(name, x0, x1, y0, y1, z0, z1, mat):
    return box(name, ((x0+x1)/2, (y0+y1)/2, (z0+z1)/2), (x1-x0, y1-y0, z1-z0), mat)

def cyl(name, center, r, h, mat, segs=32, rot=(0, 0, 0), r2=None, caps=True):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=caps, segments=segs, radius1=r, radius2=(r if r2 is None else r2), depth=h)
    ob = mesh_obj(name, bm, mat, center); ob.rotation_euler = rot
    smooth(ob); return ob

def sphere(name, center, r, mat, scale=(1, 1, 1)):
    bm = bmesh.new(); bmesh.ops.create_uvsphere(bm, u_segments=24, v_segments=16, radius=r)
    ob = mesh_obj(name, bm, mat, center); ob.scale = scale; smooth(ob); return ob

def torus(name, center, Rr, r, mat, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_torus_add(major_radius=Rr, minor_radius=r, major_segments=64, minor_segments=12, location=center, rotation=rot)
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
    for p, (x, y) in zip(sp.points, [(-w/2, -h/2), (w/2, -h/2), (w/2, h/2), (-w/2, h/2)]): p.co = (x, y, 0, 1)
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
for fp in ["C:/Windows/Fonts/arialbd.ttf",
           "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
           "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"]:
    if os.path.exists(fp):
        FONT = bpy.data.fonts.load(fp); break
SERIF = None
for fp in ["C:/Windows/Fonts/timesbd.ttf",
           "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
           "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf"]:
    if os.path.exists(fp):
        SERIF = bpy.data.fonts.load(fp); break

def text_obj(name, body, loc, rot, size, mat, extrude=0.01, align='CENTER', font=None):
    cu = bpy.data.curves.new(name, 'FONT'); cu.body = body; cu.size = size; cu.extrude = extrude
    cu.align_x = align; cu.align_y = 'CENTER'
    if font or FONT: cu.font = font or FONT
    ob = bpy.data.objects.new(name, cu); ob.location = loc; ob.rotation_euler = rot
    coll.objects.link(ob); cu.materials.append(mat); return ob

def point_light(name, loc, energy, color, size=0.15):
    lt = bpy.data.lights.new(name, 'POINT'); lt.energy = energy; lt.color = color; lt.shadow_soft_size = size
    lo = bpy.data.objects.new(name, lt); lo.location = loc; coll.objects.link(lo); return lo

FACE_CAM = (R(90), 0, 0)   # text/planes standing upright, readable from the -y side

# ================================================================= shader building blocks
def principled(nt, out, **kw):
    p = node(nt, 'ShaderNodeBsdfPrincipled')
    for k, v in kw.items(): p.inputs[k].default_value = v
    nt.links.new(p.outputs[0], out.inputs['Surface']); return p

def coords(nt, which='Object'):
    return node(nt, 'ShaderNodeTexCoord').outputs[which]

def mixcol(nt, fac, a, b, blend='MIX'):
    m = node(nt, 'ShaderNodeMix', data_type='RGBA', blend_type=blend)
    if hasattr(fac, 'links'): nt.links.new(fac, m.inputs[0])
    else: m.inputs[0].default_value = fac
    for sock, val in ((6, a), (7, b)):
        if hasattr(val, 'links'): nt.links.new(val, m.inputs[sock])
        else: m.inputs[sock].default_value = val
    return m.outputs[2]

def ramp(nt, fac, stops):
    r = node(nt, 'ShaderNodeValToRGB'); el = r.color_ramp.elements
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

def brick_tex(nt, vec, w, h, mortar, offset=0.5, c1=(1,1,1,1), c2=(1,1,1,1), cm=(0,0,0,1), smooth_=0.0):
    br = node(nt, 'ShaderNodeTexBrick', offset=offset)
    br.inputs['Scale'].default_value = 1; br.inputs['Brick Width'].default_value = w
    br.inputs['Row Height'].default_value = h; br.inputs['Mortar Size'].default_value = mortar
    br.inputs['Mortar Smooth'].default_value = smooth_
    br.inputs['Color1'].default_value = c1; br.inputs['Color2'].default_value = c2; br.inputs['Mortar'].default_value = cm
    nt.links.new(vec, br.inputs['Vector']); return br

def xz_coords(nt):
    """object coords with z fed into the y slot, so 2D textures lie flat on an upright XZ plane"""
    sep = node(nt, 'ShaderNodeSeparateXYZ'); nt.links.new(coords(nt), sep.inputs[0])
    com = node(nt, 'ShaderNodeCombineXYZ')
    nt.links.new(sep.outputs['X'], com.inputs['X']); nt.links.new(sep.outputs['Z'], com.inputs['Y'])
    return com.outputs[0]

def shadow_clear(nt, surface, tint=(0.95, 0.95, 0.9, 1)):
    """glass that lets shadow rays through: Cycles with caustics off would otherwise block the sun"""
    lp = node(nt, 'ShaderNodeLightPath')
    tr = node(nt, 'ShaderNodeBsdfTransparent'); tr.inputs['Color'].default_value = tint
    mx = node(nt, 'ShaderNodeMixShader'); nt.links.new(lp.outputs['Is Shadow Ray'], mx.inputs[0])
    nt.links.new(surface, mx.inputs[1]); nt.links.new(tr.outputs[0], mx.inputs[2])
    return mx.outputs[0]

# ================================================================= materials
def mat_platform():
    m, nt, out = mat_new('platform_slabs'); p = principled(nt, out)
    co = coords(nt)
    br = brick_tex(nt, co, 0.6, 0.6, 0.01, 0.0, (0.50, 0.49, 0.46, 1), (0.44, 0.43, 0.41, 1), (0.13, 0.13, 0.13, 1), 0.4)
    gr = ramp(nt, noise(nt, co, 0.3, 4, 0.6).outputs['Fac'], [(0.3, (0.62, 0.62, 0.62, 1)), (0.7, (1, 1, 1, 1))])
    col = mixcol(nt, 1.0, br.outputs['Color'], gr.outputs['Color'], 'MULTIPLY')
    pm = ramp(nt, noise(nt, co, 0.4, 3, 0.55).outputs['Fac'], [(0.645, (0, 0, 0, 1)), (0.675, (1, 1, 1, 1))])
    nt.links.new(mixcol(nt, pm.outputs['Color'], col, (0.09, 0.09, 0.1, 1)), p.inputs['Base Color'])
    nt.links.new(map_range(nt, pm.outputs['Color'], 0.55, 0.04), p.inputs['Roughness'])
    fine = noise(nt, co, 60, 3, 0.7)
    h = math_node(nt, 'MULTIPLY', math_node(nt, 'ADD', br.outputs['Fac'], math_node(nt, 'MULTIPLY', fine.outputs['Fac'], 0.08)), -1)
    bump(nt, math_node(nt, 'MULTIPLY', h, math_node(nt, 'SUBTRACT', 1.0, pm.outputs['Color'])), 0.5, p, 0.01)
    return m

def mat_ballast():
    m, nt, out = mat_new('ballast'); p = principled(nt, out, Roughness=0.95)
    co = coords(nt)
    vo = node(nt, 'ShaderNodeTexVoronoi', feature='DISTANCE_TO_EDGE'); vo.inputs['Scale'].default_value = 28; nt.links.new(co, vo.inputs['Vector'])
    vc = node(nt, 'ShaderNodeTexVoronoi', feature='F1'); vc.inputs['Scale'].default_value = 28; nt.links.new(co, vc.inputs['Vector'])
    cr = ramp(nt, vc.outputs['Color'], [(0.0, (0.10, 0.09, 0.08, 1)), (0.5, (0.22, 0.20, 0.18, 1)), (1.0, (0.33, 0.31, 0.28, 1))])
    dr = ramp(nt, noise(nt, co, 0.5, 3).outputs['Fac'], [(0.3, (0.35, 0.3, 0.25, 1)), (0.7, (1, 1, 1, 1))])
    nt.links.new(mixcol(nt, 1.0, cr.outputs['Color'], dr.outputs['Color'], 'MULTIPLY'), p.inputs['Base Color'])
    bump(nt, ramp(nt, vo.outputs['Distance'], [(0.0, (0, 0, 0, 1)), (0.12, (1, 1, 1, 1))]).outputs['Color'], 0.9, p, 0.05)
    return m

def mat_paint(name, base, rust=0.15, rough=0.42, metal=0.2):
    m, nt, out = mat_new(name); p = principled(nt, out, Metallic=metal, Roughness=rough)
    co = coords(nt)
    rr = ramp(nt, noise(nt, co, 3.0, 5, 0.65).outputs['Fac'], [(0.75 - rust*0.4, (0, 0, 0, 1)), (0.8, (1, 1, 1, 1))])
    nt.links.new(mixcol(nt, rr.outputs['Color'], base, (0.22, 0.12, 0.07, 1)), p.inputs['Base Color'])
    nt.links.new(map_range(nt, rr.outputs['Color'], rough, 0.85), p.inputs['Roughness'])
    bump(nt, noise(nt, co, 40, 3, 0.6).outputs['Fac'], 0.12, p, 0.01)
    return m

def mat_steel():
    m, nt, out = mat_new('rail_steel'); p = principled(nt, out, Metallic=1.0, Roughness=0.22, **{'Base Color': (0.62, 0.62, 0.6, 1)})
    nt.links.new(map_range(nt, noise(nt, coords(nt), 8, 3).outputs['Fac'], 0.15, 0.45), p.inputs['Roughness'])
    return m

def mat_brick(name='brick', c1=(0.36, 0.11, 0.07, 1), c2=(0.26, 0.08, 0.06, 1), upright_x=True):
    m, nt, out = mat_new(name); p = principled(nt, out, Roughness=0.85)
    co = coords(nt)
    vec = co
    if upright_x:   # walls running along y: rotate so courses run horizontally
        mp = node(nt, 'ShaderNodeMapping'); mp.inputs['Rotation'].default_value = (0, 0, R(90))
        nt.links.new(co, mp.inputs['Vector']); vec = mp.outputs[0]
    else:
        vec = xz_coords(nt)
    br = brick_tex(nt, vec, 0.23, 0.075, 0.008, 0.5, c1, c2, (0.28, 0.26, 0.22, 1), 0.3)
    sr = ramp(nt, noise(nt, co, 0.25, 4, 0.7).outputs['Fac'], [(0.35, (0.3, 0.27, 0.25, 1)), (0.75, (1, 1, 1, 1))])
    nt.links.new(mixcol(nt, 1.0, br.outputs['Color'], sr.outputs['Color'], 'MULTIPLY'), p.inputs['Base Color'])
    bump(nt, math_node(nt, 'SUBTRACT', 1.0, br.outputs['Fac']), 0.6, p, 0.02)
    return m

def mat_roof_glass():
    m, nt, out = mat_new('roof_glass')
    uv = coords(nt, 'UV')
    bars = brick_tex(nt, uv, 1.2, 3.0, 0.045, 0.0)
    glass = node(nt, 'ShaderNodeBsdfGlass'); glass.inputs['Roughness'].default_value = 0.15
    glass.inputs['Color'].default_value = (0.82, 0.88, 0.86, 1)
    grime = ramp(nt, noise(nt, uv, 1.5, 4, 0.7).outputs['Fac'], [(0.45, (0, 0, 0, 1)), (0.85, (1, 1, 1, 1))])
    tl = node(nt, 'ShaderNodeBsdfTranslucent'); tl.inputs['Color'].default_value = (0.5, 0.48, 0.42, 1)
    g1 = node(nt, 'ShaderNodeMixShader'); nt.links.new(grime.outputs['Color'], g1.inputs[0])
    nt.links.new(glass.outputs[0], g1.inputs[1]); nt.links.new(tl.outputs[0], g1.inputs[2])
    pane = shadow_clear(nt, g1.outputs[0], (0.85, 0.85, 0.8, 1))
    frame = node(nt, 'ShaderNodeBsdfPrincipled'); frame.inputs['Base Color'].default_value = (0.2, 0.32, 0.42, 1)
    frame.inputs['Metallic'].default_value = 0.3; frame.inputs['Roughness'].default_value = 0.5
    mx = node(nt, 'ShaderNodeMixShader'); nt.links.new(bars.outputs['Fac'], mx.inputs[0])
    nt.links.new(pane, mx.inputs[1]); nt.links.new(frame.outputs[0], mx.inputs[2])
    nt.links.new(mx.outputs[0], out.inputs['Surface'])
    return m

def mat_roof_boards():
    m, nt, out = mat_new('roof_boards'); p = principled(nt, out, Roughness=0.8)
    uv = coords(nt, 'UV')
    br = brick_tex(nt, uv, 6.0, 0.18, 0.006, 0.37, (0.055, 0.036, 0.025, 1), (0.042, 0.028, 0.02, 1), (0.012, 0.009, 0.007, 1))
    sr = ramp(nt, noise(nt, uv, 0.4, 3).outputs['Fac'], [(0.3, (0.6, 0.6, 0.6, 1)), (0.7, (1, 1, 1, 1))])
    nt.links.new(mixcol(nt, 1.0, br.outputs['Color'], sr.outputs['Color'], 'MULTIPLY'), p.inputs['Base Color'])
    bump(nt, br.outputs['Fac'], 0.4, p, 0.01)
    return m

def mat_screen_glass():
    m, nt, out = mat_new('screen_glass')
    vec = xz_coords(nt)
    bars = brick_tex(nt, vec, 1.5, 2.0, 0.05, 0.0)
    glass = node(nt, 'ShaderNodeBsdfGlass'); glass.inputs['Roughness'].default_value = 0.06
    glass.inputs['Color'].default_value = (0.9, 0.93, 0.92, 1)
    tr = node(nt, 'ShaderNodeBsdfTransparent'); tr.inputs['Color'].default_value = (0.9, 0.9, 0.88, 1)
    g = node(nt, 'ShaderNodeMixShader'); g.inputs[0].default_value = 0.65       # mostly see-through: the sky shows
    nt.links.new(glass.outputs[0], g.inputs[1]); nt.links.new(tr.outputs[0], g.inputs[2])
    pane = shadow_clear(nt, g.outputs[0])
    frame = node(nt, 'ShaderNodeBsdfPrincipled'); frame.inputs['Base Color'].default_value = (0.2, 0.32, 0.42, 1)
    frame.inputs['Roughness'].default_value = 0.5
    mx = node(nt, 'ShaderNodeMixShader'); nt.links.new(bars.outputs['Fac'], mx.inputs[0])
    nt.links.new(pane, mx.inputs[1]); nt.links.new(frame.outputs[0], mx.inputs[2])
    nt.links.new(mx.outputs[0], out.inputs['Surface'])
    return m

def mat_wood():
    m, nt, out = mat_new('bench_wood'); p = principled(nt, out, Roughness=0.4)
    mp = node(nt, 'ShaderNodeMapping'); mp.inputs['Scale'].default_value = (1, 12, 1); nt.links.new(coords(nt), mp.inputs['Vector'])
    w = node(nt, 'ShaderNodeTexWave', wave_type='BANDS', bands_direction='Y'); w.inputs['Scale'].default_value = 1.5
    w.inputs['Distortion'].default_value = 3; w.inputs['Detail'].default_value = 3
    nt.links.new(mp.outputs[0], w.inputs['Vector'])
    nt.links.new(ramp(nt, w.outputs['Fac'], [(0.0, (0.16, 0.08, 0.04, 1)), (0.5, (0.30, 0.16, 0.07, 1)), (1.0, (0.22, 0.11, 0.05, 1))]).outputs['Color'], p.inputs['Base Color'])
    bump(nt, w.outputs['Fac'], 0.25, p, 0.005); p.inputs['Coat Weight'].default_value = 0.4
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

def mat_lit_window(name='train_window', color=(1.0, 0.74, 0.46, 1), strength=1.5):
    m, nt, out = mat_new(name)
    lf = node(nt, 'ShaderNodeLayerWeight'); lf.inputs['Blend'].default_value = 0.35
    gl = node(nt, 'ShaderNodeBsdfGlossy'); gl.inputs['Roughness'].default_value = 0.05
    em = node(nt, 'ShaderNodeEmission'); em.inputs['Color'].default_value = color; em.inputs['Strength'].default_value = strength
    mx = node(nt, 'ShaderNodeMixShader'); nt.links.new(lf.outputs['Fresnel'], mx.inputs[0])
    nt.links.new(em.outputs[0], mx.inputs[1]); nt.links.new(gl.outputs[0], mx.inputs[2])
    nt.links.new(mx.outputs[0], out.inputs['Surface']); return m

def mat_kiosk_glass():
    """K6-style glazing: many small lit panes in a red frame"""
    m, nt, out = mat_new('kiosk_glass')
    bars = brick_tex(nt, xz_coords(nt), 0.17, 0.16, 0.025, 0.0)
    em = node(nt, 'ShaderNodeEmission'); em.inputs['Color'].default_value = (1.0, 0.82, 0.55, 1); em.inputs['Strength'].default_value = 1.6
    fr = node(nt, 'ShaderNodeBsdfPrincipled'); fr.inputs['Base Color'].default_value = (0.5, 0.02, 0.02, 1); fr.inputs['Roughness'].default_value = 0.3
    mx = node(nt, 'ShaderNodeMixShader'); nt.links.new(bars.outputs['Fac'], mx.inputs[0])
    nt.links.new(em.outputs[0], mx.inputs[1]); nt.links.new(fr.outputs[0], mx.inputs[2])
    nt.links.new(mx.outputs[0], out.inputs['Surface']); return m

def mat_train_paint(name, base):
    m, nt, out = mat_new(name)
    p = principled(nt, out, Roughness=0.32, Metallic=0.1)
    p.inputs['Coat Weight'].default_value = 1.0; p.inputs['Coat Roughness'].default_value = 0.08
    r = ramp(nt, noise(nt, coords(nt), 2, 4, 0.7).outputs['Fac'], [(0.4, (0.7, 0.7, 0.7, 1)), (0.7, (1, 1, 1, 1))])
    nt.links.new(mixcol(nt, 1.0, base, r.outputs['Color'], 'MULTIPLY'), p.inputs['Base Color'])
    return m

M = dict(
    platform=mat_platform(), ballast=mat_ballast(), steel=mat_steel(),
    brick=mat_brick('brick_long'), brick_end=mat_brick('brick_end', upright_x=False),
    rib=mat_paint('rib_blue', (0.26, 0.45, 0.6, 1), 0.12), iron_dark=mat_paint('iron_dark', (0.03, 0.03, 0.035, 1), 0.2),
    glass=mat_roof_glass(), boards=mat_roof_boards(), screen=mat_screen_glass(), wood=mat_wood(),
    sleeper=mat_simple('sleeper', (0.08, 0.06, 0.045, 1), 0.9), concrete=mat_simple('concrete', (0.36, 0.35, 0.33, 1), 0.8),
    stone=mat_simple('portland_stone', (0.62, 0.58, 0.5, 1), 0.75), yellow=mat_simple('yellow_line', (0.9, 0.7, 0.08, 1), 0.45),
    white_emit=mat_emission('sign_text', (1, 1, 1, 1), 3.0), navy=mat_simple('sign_navy', (0.02, 0.05, 0.16, 1), 0.4),
    bulb=mat_emission('globe', (1.0, 0.78, 0.5, 1), 22), shade=mat_simple('lamp_shade', (0.04, 0.06, 0.08, 1), 0.35, 0.4),
    gold=mat_simple('gold', (0.85, 0.6, 0.2, 1), 0.3, 1.0), black=mat_simple('black', (0.02, 0.02, 0.02, 1), 0.8),
    clock=mat_emission('clock_face', (1.0, 0.95, 0.82, 1), 2.4), doorway=mat_emission('doorway', (1.0, 0.7, 0.4, 1), 3.5),
    window=mat_lit_window(), cab_glass=mat_simple('cab_glass', (0.01, 0.012, 0.015, 1), 0.05, 0.0, 1.0),
    headlight=mat_emission('headlight', (1, 0.95, 0.85, 1), 60), tail=mat_emission('tail_lamp', (1, 0.08, 0.04, 1), 12),
    hst_yellow=mat_train_paint('hst_yellow', (0.85, 0.62, 0.02, 1)), navy_paint=mat_train_paint('coach_navy', (0.02, 0.035, 0.1, 1)),
    grey_band=mat_train_paint('band_grey', (0.6, 0.62, 0.64, 1)), emu_white=mat_train_paint('emu_white', (0.75, 0.76, 0.78, 1)),
    emu_teal=mat_train_paint('emu_teal', (0.02, 0.32, 0.36, 1)), red=mat_train_paint('pillar_red', (0.55, 0.015, 0.012, 1)),
    kiosk_glass=mat_kiosk_glass(), skin=mat_simple('skin', (0.45, 0.3, 0.22, 1), 0.6),
    amber=mat_emission('board_amber', (1.0, 0.62, 0.16, 1), 5.0), red_led=mat_emission('board_red', (1.0, 0.12, 0.06, 1), 5.0),
    board=mat_simple('board_black', (0.01, 0.01, 0.012, 1), 0.35), cream=mat_simple('cream', (0.85, 0.78, 0.6, 1), 0.5),
    buffer_red=mat_simple('buffer_red', (0.5, 0.03, 0.02, 1), 0.4),
)

# ================================================================= the Gothic arch
# Two-centred pointed arch: each side is a circular arc whose centre sits below the springing line,
# so the roof rises steeply from the platforms and meets at a gentle point 30 m up (73 m span).
A, H, Z0, XC = 36.0, 28.0, 2.0, 12.0
U = (A*A + 2*A*XC - H*H) / (2*H)
ZC = Z0 - U
RAD = math.hypot(A + XC, U)
TH_S = math.atan2(Z0 - ZC, -A - XC)
TH_A = math.atan2(Z0 + H - ZC, -XC)

def gothic(t, off=0.0):
    """(x, z) on the arch for t in [0,1] (left springing, apex at 0.5, right springing); off > 0 is outward"""
    left = t <= 0.5
    s = (t/0.5) if left else ((1-t)/0.5)
    th = TH_S + (TH_A - TH_S)*s
    x = XC + (RAD+off)*math.cos(th); z = ZC + (RAD+off)*math.sin(th)
    return (x, z) if left else (-x, z)

def arch_z(x, off=0.0):
    """height of the arch above a given x (bisection on the left half)"""
    x = -abs(x); lo, hi = 0.0, 0.5
    for _ in range(50):
        mid = (lo+hi)/2
        if gothic(mid, off)[0] < x: lo = mid
        else: hi = mid
    return gothic((lo+hi)/2, off)[1]

def arch_x(z, off=0.0):
    """half-width of the arch at height z"""
    lo, hi = 0.0, 0.5
    for _ in range(50):
        mid = (lo+hi)/2
        if gothic(mid, off)[1] < z: lo = mid
        else: hi = mid
    return abs(gothic((lo+hi)/2, off)[0])

# ================================================================= layout
Y0, Y1 = -34.0, 72.0           # shed: open at Y0 (behind the camera), end screen at Y1
PLAT_Z = 1.0
PY0, PY1 = -30.0, Y1 - 14.0    # platforms run up to the concourse
ISLANDS = (-20.0, 0.0, 20.0)
TRACKS = (-25.6, -14.4, -5.6, 5.6, 14.4, 25.6)
BUFFER_Y = PY1 - 2.5
RAIL_TOP = 0.61

# ground, ballast, track
box_span('ground', -40, 40, Y0-40, Y1+10, -0.2, 0.0, M['ballast'])
for tx in TRACKS:
    L = BUFFER_Y - (Y0 - 30)
    box_span(f'ballast_{tx}', tx-2.0, tx+2.0, Y0-30, BUFFER_Y+1, 0.0, 0.3, M['ballast'])
    slp = box(f'sleeper_{tx}', (tx, Y0-30, 0.375), (2.5, 0.24, 0.15), M['sleeper']); array(slp, int(L/0.62)+1, (0, 0.62, 0))
    for rx in (-0.7175, 0.7175):
        box_span(f'railfoot_{tx}_{rx}', tx+rx-0.075, tx+rx+0.075, Y0-30, BUFFER_Y, 0.45, 0.48, M['steel'])
        r = box_span(f'rail_{tx}_{rx}', tx+rx-0.035, tx+rx+0.035, Y0-30, BUFFER_Y, 0.47, RAIL_TOP, M['steel']); bevel(r, 0.012, 2)
    # buffer stop: red beam on two posts, red lamp
    by = BUFFER_Y + 0.3
    for sx in (-0.72, 0.72):
        box(f'bstop_post_{tx}_{sx}', (tx+sx, by+0.3, 0.75), (0.25, 0.6, 1.0), M['iron_dark'])
        cyl(f'bstop_ram_{tx}_{sx}', (tx+sx, by-0.15, 1.0), 0.13, 0.5, M['steel'], rot=(R(90), 0, 0))
    box(f'bstop_beam_{tx}', (tx, by, 1.0), (2.4, 0.3, 0.5), M['buffer_red'])
    cyl(f'bstop_lamp_{tx}', (tx, by-0.16, 1.45), 0.08, 0.04, M['tail'], rot=(R(90), 0, 0))

def platform(name, x0, x1, edges=(True, True)):
    box_span(name, x0, x1, PY0, PY1, 0.0, PLAT_Z, M['platform'])
    for i, (xe, sgn) in enumerate(((x0, 1), (x1, -1))):
        if not edges[i]: continue
        box_span(f'{name}_face{i}', xe-0.06 if sgn > 0 else xe-0.06, xe+0.06, PY0, PY1, 0.05, PLAT_Z-0.08, M['brick'])
        xa, xb = (xe, xe+0.45) if sgn > 0 else (xe-0.45, xe)
        c = box_span(f'{name}_coping{i}', xa, xb, PY0, PY1, PLAT_Z-0.075, PLAT_Z+0.005, M['concrete']); bevel(c, 0.02, 2)
        yx = xe + sgn*0.75
        box_span(f'{name}_yellow{i}', yx-0.05, yx+0.05, PY0, PY1, PLAT_Z, PLAT_Z+0.004, M['yellow'])

for P in ISLANDS:
    platform(f'island_{P:.0f}', P-4, P+4)
platform('side_L', -35.6, -27.2, (False, True))
platform('side_R', 27.2, 35.6, (True, False))
# concourse across the full width at the buffer end
box_span('concourse', -35.6, 35.6, PY1, Y1, 0.0, PLAT_Z, M['platform'])
box_span('concourse_face', -35.6, 35.6, PY1-0.12, PY1, 0.05, PLAT_Z-0.02, M['brick'])

# low side walls under the springing, with stone plinths for every rib
for sx in (-1, 1):
    box_span(f'sidewall_{sx}', sx*36.0 - 0.6 if sx > 0 else -37.2, sx*36.0 + 1.2 if sx > 0 else -36.0 + 0.6, Y0, Y1, 0.0, Z0+1.4, M['brick'])

# ================================================================= roof: ribs, purlins, glazing, boarding
RIB_DY = 9.0
rib_ys = [Y0 + 4 + i*RIB_DY for i in range(int((Y1 - Y0 - 4)//RIB_DY) + 1)]
rib_prof = rect_profile('rib_prof', 0.42, 0.42)
lat_prof = rect_profile('lat_prof', 0.13, 0.13)
N = 80
for y in rib_ys:
    outer = [(gothic(i/N)[0], y, gothic(i/N)[1]) for i in range(N+1)]
    inner = [(gothic(i/N, -1.5)[0], y, gothic(i/N, -1.5)[1]) for i in range(N+1)]
    sweep(f'rib_{y:.0f}', outer, rib_prof, M['rib'])
    sweep(f'rib_in_{y:.0f}', inner, rib_prof, M['rib'])
    sweep(f'rib_lat_{y:.0f}', [outer[i] if i % 2 == 0 else inner[i] for i in range(N+1)], lat_prof, M['rib'])
    for sx in (-1, 1):
        box(f'plinth_{sx}_{y:.0f}', (sx*35.6, y, (Z0+0.6)/2), (1.4, 1.4, Z0+0.6), M['stone'])

for k in range(1, 24):
    t = k/24
    if abs(t - 0.5) < 1e-6: continue
    x, z = gothic(t, 0.3); x2, z2 = gothic(t + (0.001 if t < 0.5 else -0.001), 0.3)
    ang = -math.atan2(z2 - z, x2 - x) if t < 0.5 else -math.atan2(z - z2, x - x2)
    box(f'purlin_{k}', (x, (Y0+Y1)/2, z), (0.3, Y1-Y0, 0.2), M['rib'], rot=(0, ang, 0))
box('ridge', (0, (Y0+Y1)/2, Z0+H+0.25), (0.5, Y1-Y0, 0.5), M['rib'])

def shell(name, t0, t1, mat, off=0.5, ns=48, ny=12):
    bm = bmesh.new(); uvl = bm.loops.layers.uv.new()
    ts = [t0 + (t1-t0)*i/ns for i in range(ns+1)]
    pts = [gothic(t, off) for t in ts]
    arcl = [0.0]
    for i in range(1, ns+1): arcl.append(arcl[-1] + math.dist(pts[i], pts[i-1]))
    grid, idx = [], {}
    for j in range(ny+1):
        yy = Y0 + (Y1-Y0)*j/ny
        row = [bm.verts.new((pts[i][0], yy, pts[i][1])) for i in range(ns+1)]
        for i, v in enumerate(row): idx[v] = (i, j)
        grid.append(row)
    for j in range(ny):
        for i in range(ns):
            f = bm.faces.new((grid[j][i], grid[j][i+1], grid[j+1][i+1], grid[j+1][i]))
            for lp in f.loops:
                ii, jj = idx[lp.vert]; lp[uvl].uv = (arcl[ii], Y0 + (Y1-Y0)*jj/ny)
    ob = mesh_obj(name, bm, mat); smooth(ob); return ob

shell('roof_boards_L', 0.0, 0.17, M['boards'])
shell('roof_glass', 0.17, 0.83, M['glass'], ns=96)
shell('roof_boards_R', 0.83, 1.0, M['boards'])

# ================================================================= the end: brick range, glazed screen, the great clock
Z_SCREEN = 9.0
box_span('end_range', -37.2, 37.2, Y1, Y1+8, 0.0, Z_SCREEN, M['brick_end'])
box_span('end_cornice', -37.2, 37.2, Y1-0.35, Y1+0.2, Z_SCREEN-0.2, Z_SCREEN+0.35, M['stone'])
box_span('end_stringcourse', -37.2, 37.2, Y1-0.2, Y1+0.1, 5.9, 6.2, M['stone'])
for i, x in enumerate((-24, -16, -8, 0, 8, 16, 24)):
    w = 4.0 if x == 0 else 3.0
    box(f'door_{i}', (x, Y1-0.03, PLAT_Z + 1.9), (w, 0.06, 3.8), M['doorway'])
    cyl(f'door_arch_{i}', (x, Y1-0.03, PLAT_Z + 3.8), w/2, 0.06, M['doorway'], rot=(R(90), 0, 0))
    cyl(f'door_surround_{i}', (x, Y1-0.01, PLAT_Z + 3.8), w/2 + 0.3, 0.04, M['stone'], rot=(R(90), 0, 0))
text_obj('station_name', "ST PANCRAS", (0, Y1-0.08, 7.3), FACE_CAM, 1.25, M['cream'], 0.05, font=SERIF)

# glazed screen filling the arch above the brick range
xs = arch_x(Z_SCREEN, -0.3)
bm = bmesh.new()
outline = [(-xs, Z_SCREEN)]
for i in range(1, 160):
    x, z = gothic(i/160, -0.3)
    if z > Z_SCREEN: outline.append((x, z))
outline.append((xs, Z_SCREEN))
bm.faces.new([bm.verts.new((x, Y1 - 0.4, z)) for x, z in outline])
mesh_obj('end_screen', bm, M['screen'])
for x in range(-30, 31, 6):
    if x == 0: continue
    zt = arch_z(x, -0.4)
    box_span(f'mullion_{x}', x-0.18, x+0.18, Y1-0.65, Y1-0.25, Z_SCREEN, zt, M['rib'])
for z in (14.0, 24.0):
    hx = arch_x(z, -0.4)
    box_span(f'transom_{z:.0f}', -hx, hx, Y1-0.65, Y1-0.25, z-0.15, z+0.15, M['rib'])

# the clock
CK = Vector((0, Y1 - 0.75, 19.0)); CKR = 3.1
torus('clock_ring', (CK.x, CK.y + 0.1, CK.z), CKR + 0.55, 0.32, M['rib'], rot=(R(90), 0, 0))
cyl('clock_back', (CK.x, CK.y + 0.15, CK.z), CKR + 0.5, 0.2, M['rib'], rot=(R(90), 0, 0))
cyl('clock_face', (CK.x, CK.y, CK.z), CKR, 0.08, M['clock'], segs=64, rot=(R(90), 0, 0))
torus('clock_rim', (CK.x, CK.y - 0.05, CK.z), CKR + 0.05, 0.1, M['gold'], rot=(R(90), 0, 0))
for k in range(1, 13):
    a = R(k*30); d = Vector((math.sin(a), 0, math.cos(a)))
    p = CK + d*2.45 + Vector((0, -0.07, 0))
    text_obj(f'clock_num_{k}', ["I","II","III","IIII","V","VI","VII","VIII","IX","X","XI","XII"][k-1],
             tuple(p), FACE_CAM, 0.42, M['black'], 0.01, font=SERIF)
    for mnt in range(5):
        am = R(k*30 + mnt*6); dm = Vector((math.sin(am), 0, math.cos(am)))
        q = CK + dm*2.88 + Vector((0, -0.06, 0))
        box(f'clock_tick_{k}_{mnt}', tuple(q), (0.05 if mnt else 0.09, 0.02, 0.22 if mnt == 0 else 0.1), M['black'], rot=(0, am, 0))
def hand(name, angle_deg, length, width):
    a = R(angle_deg); d = Vector((math.sin(a), 0, math.cos(a)))
    box(name, tuple(CK + d*(length/2 - 0.3) + Vector((0, -0.12, 0))), (width, 0.03, length), M['black'], rot=(0, a, 0))
hand('clock_hour', (6 + 50/60) * 30, 1.9, 0.16)    # ten to seven
hand('clock_minute', 50 * 6, 2.75, 0.1)
sphere('clock_boss', (CK.x, CK.y - 0.15, CK.z), 0.14, M['gold'])

# ================================================================= lamps hanging from the roof
lamp_x = list(ISLANDS) + [-31.4, 31.4]
for y in [Y0 + 8.5 + i*RIB_DY for i in range(int((PY1 - Y0 - 8.5)//RIB_DY) + 1)]:
    for x in lamp_x:
        top = arch_z(x, 0.0)
        z = 7.0 if abs(x) < 25 else 5.8
        cyl(f'lamp_rod_{x:.0f}_{y:.0f}', (x, y, (top + z)/2 + 0.5), 0.025, top - z - 1.0, M['iron_dark'], segs=8)
        cyl(f'lamp_shade_{x:.0f}_{y:.0f}', (x, y, z + 0.55), 0.55, 0.35, M['shade'], r2=0.12, caps=False)
        sphere(f'lamp_globe_{x:.0f}_{y:.0f}', (x, y, z + 0.2), 0.28, M['bulb'])
        point_light(f'lamp_lt_{x:.0f}_{y:.0f}', (x, y, z), 2200, (1.0, 0.72, 0.45), 0.25)

for x in (-24.0, -12.0, 0.0, 12.0, 24.0):   # concourse lamps
    cyl(f'clamp_rod_{x:.0f}', (x, PY1 + 7.0, (arch_z(x) + 7.5)/2 + 0.5), 0.025, arch_z(x) - 7.5 - 1.0, M['iron_dark'], segs=8)
    cyl(f'clamp_shade_{x:.0f}', (x, PY1 + 7.0, 8.05), 0.55, 0.35, M['shade'], r2=0.12, caps=False)
    sphere(f'clamp_globe_{x:.0f}', (x, PY1 + 7.0, 7.7), 0.28, M['bulb'])
    point_light(f'clamp_lt_{x:.0f}', (x, PY1 + 7.0, 7.5), 2200, (1.0, 0.72, 0.45), 0.25)

# ================================================================= trains
def bogies(name, x, y_front, length):
    for by in (y_front + 3.2, y_front + length - 3.2):
        box(f'{name}_bogie_{by:.0f}', (x, by, 0.95), (2.1, 2.8, 0.45), M['iron_dark'])
        for wy in (-0.9, 0.9):
            for sx in (-1, 1):
                cyl(f'{name}_wheel_{by:.0f}_{wy}_{sx}', (x + sx*0.75, by + wy, RAIL_TOP + 0.42), 0.42, 0.12, M['steel'], rot=(0, R(90), 0))

def coach(name, x, y_front, length, body, band, windows=True, door_every=None):
    """a carriage body from y_front to y_front+length (the end toward the camera is y_front)"""
    yc = y_front + length/2
    b = box(f'{name}_body', (x, yc, 2.55), (2.8, length, 2.85), body); bevel(b, 0.3, 5)
    rf = box(f'{name}_roof', (x, yc, 4.0), (2.5, length - 0.4, 0.22), M['iron_dark']); bevel(rf, 0.1, 3)
    box(f'{name}_skirt', (x, yc, 1.2), (2.6, length - 0.4, 0.3), M['iron_dark'])
    for sx in (-1, 1):
        box(f'{name}_band_{sx}', (x + sx*1.405, yc, 2.05), (0.02, length - 0.6, 0.2), band)
        if windows:
            n = int((length - 2.5) // 2.3)
            for i in range(n):
                wy = y_front + 1.6 + 1.15 + i*2.3
                box(f'{name}_win_{sx}_{i}', (x + sx*1.41, wy, 2.85), (0.02, 1.5, 0.85), M['window'])
    bogies(name, x, y_front, length)

def hst_power_car(name, x, y_front, body, length=17.0):
    """wedge-nosed diesel power car, yellow nose, cab windscreen, headlights; nose points to -y"""
    NL = 3.4
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co = Vector((v.co.x*2.8, v.co.y*NL, v.co.z*2.85))
        if v.co.y < 0 and v.co.z > 0: v.co.y += NL*0.55          # rake the top of the nose back
        if v.co.y < 0 and v.co.z < 0: v.co.x *= 0.96
    nose = mesh_obj(f'{name}_nose', bm, M['hst_yellow'], (x, y_front + NL/2, 2.55)); bevel(nose, 0.35, 6)
    rake = math.atan2(NL*0.55, 2.85)                              # angle of the raked face from vertical
    def on_face(zl, out=0.04):                                    # point on the raked face at local height zl
        yl = -NL/2 + NL*0.55*(zl + 1.425)/2.85
        n = Vector((0, -math.cos(rake), math.sin(rake)))
        return Vector((x, y_front + NL/2 + yl, 2.55 + zl)) + n*out
    box(f'{name}_screen', tuple(on_face(0.75)), (2.3, 0.03, 0.85), M['cab_glass'], rot=(-rake, 0, 0))
    for sx in (-0.85, 0.85):
        p = on_face(-0.85, 0.05)
        cyl(f'{name}_head_{sx}', (x + sx, p.y, p.z), 0.16, 0.06, M['headlight'], rot=(R(90) - rake, 0, 0))
        lt = bpy.data.lights.new(f'{name}_spot_{sx}', 'SPOT'); lt.energy = 1800; lt.color = (1, 0.95, 0.85)
        lt.spot_size = R(45); lt.spot_blend = 0.6; lt.shadow_soft_size = 0.15
        lo = bpy.data.objects.new(lt.name, lt); lo.location = (x + sx, p.y - 0.1, p.z); lo.rotation_euler = (R(-90), 0, 0)   # -Z of the lamp -> -y; coll.objects.link(lo)
    body_len = length - NL
    b = box(f'{name}_body', (x, y_front + NL + body_len/2, 2.55), (2.8, body_len, 2.85), body); bevel(b, 0.3, 5)
    rf = box(f'{name}_roof', (x, y_front + NL + body_len/2, 4.0), (2.5, body_len - 0.4, 0.22), M['iron_dark'])
    for sx in (-1, 1):
        box(f'{name}_band_{sx}', (x + sx*1.405, y_front + NL + body_len/2, 2.05), (0.02, body_len - 0.6, 0.2), M['grey_band'])
        box(f'{name}_grille_{sx}', (x + sx*1.41, y_front + NL + body_len*0.6, 3.1), (0.02, 4.5, 0.7), M['iron_dark'])
    box(f'{name}_skirt', (x, y_front + length/2, 1.2), (2.6, length - 0.6, 0.3), M['iron_dark'])
    bogies(name, x, y_front, length)

def emu_cab(name, x, y_front, body, nose_mat, length=21.0):
    """rounded electric multiple unit cab, dark wraparound windscreen, yellow lower panel"""
    NL = 2.2
    c = box(f'{name}_cab', (x, y_front + NL/2, 2.55), (2.8, NL, 2.85), nose_mat); bevel(c, 0.85, 10)
    box(f'{name}_screen', (x, y_front + 0.02, 3.05), (2.2, 0.05, 0.95), M['cab_glass'])
    box(f'{name}_warn', (x, y_front + 0.03, 1.75), (1.9, 0.05, 0.75), M['hst_yellow'])
    for sx in (-0.8, 0.8):
        cyl(f'{name}_head_{sx}', (x + sx, y_front - 0.01, 2.2), 0.12, 0.05, M['headlight'], rot=(R(90), 0, 0))
        cyl(f'{name}_tail_{sx}', (x + sx*1.15, y_front - 0.01, 2.2), 0.07, 0.05, M['tail'], rot=(R(90), 0, 0))
    coach(name, x, y_front + NL - 0.2, length - NL + 0.2, body, M['emu_teal'])

# platform 3 (left of the camera): an HST set, power car leading
hst_power_car('hstA_pc', -5.6, -4.0, M['navy_paint'])
yy = -4.0 + 17.2
while yy + 23 <= BUFFER_Y + 0.5:
    coach(f'hstA_c{yy:.0f}', -5.6, yy, 23.0, M['navy_paint'], M['grey_band']); yy += 23.2
if BUFFER_Y - 0.3 - yy > 8:
    coach(f'hstA_c{yy:.0f}', -5.6, yy, BUFFER_Y - 0.3 - yy, M['navy_paint'], M['grey_band'])
# platform 4 (right): a two-car electric unit, set further back
emu_cab('emuB', 5.6, 13.0, M['emu_white'], M['emu_white'], 21.0)
coach('emuB_c2', 5.6, 34.2, BUFFER_Y - 34.5, M['emu_white'], M['emu_teal'])
# platform 2 (far left): another HST, deeper in the shed
hst_power_car('hstC_pc', -14.4, 18.0, M['navy_paint'])
coach('hstC_c1', -14.4, 35.2, BUFFER_Y - 35.5, M['navy_paint'], M['grey_band'])
# platform 6 (far right): coaches only, an empty stock train
coach('stockD', 25.6, 24.0, BUFFER_Y - 24.3, M['navy_paint'], M['grey_band'])

# ================================================================= platform furniture, people, London details
def bench(y, x, face):
    for dy in (-0.8, 0.8):
        box(f'bench_end_{y:.0f}_{x:.0f}_{dy}', (x, y+dy, PLAT_Z+0.25), (0.5, 0.06, 0.5), M['iron_dark'])
        box(f'bench_back_{y:.0f}_{x:.0f}_{dy}', (x - face*0.22, y+dy, PLAT_Z+0.75), (0.06, 0.06, 0.55), M['iron_dark'], rot=(0, -face*R(12), 0))
    for i in range(4):
        box(f'bench_seat_{y:.0f}_{x:.0f}_{i}', (x - face*0.18 + face*i*0.12, y, PLAT_Z+0.52), (0.1, 1.8, 0.04), M['wood'])
    for i in range(3):
        box(f'bench_bk_{y:.0f}_{x:.0f}_{i}', (x - face*(0.24+i*0.03), y, PLAT_Z+0.62+i*0.14), (0.04, 1.8, 0.1), M['wood'], rot=(0, -face*R(12), 0))

def figure(name, x, y, h=1.75, coat=(0.05, 0.05, 0.07, 1), hat=True):
    s = h/1.75; mc = mat_simple(f'{name}_coat', coat, 0.75)
    for sx in (-1, 1):
        cyl(f'{name}_leg{sx}', (x + sx*0.1*s, y, PLAT_Z + 0.38*s), 0.09*s, 0.76*s, M['black'])
    cyl(f'{name}_torso', (x, y, PLAT_Z + 1.12*s), 0.26*s, 0.9*s, mc, r2=0.22*s)
    sphere(f'{name}_head', (x, y, PLAT_Z + 1.66*s), 0.11*s, M['skin'])
    if hat:
        cyl(f'{name}_hat', (x, y, PLAT_Z + 1.78*s), 0.13*s, 0.09*s, mc)
        cyl(f'{name}_brim', (x, y, PLAT_Z + 1.74*s), 0.2*s, 0.015*s, mc)

for i, y in enumerate((-12.0, 6.0, 24.0, 42.0)):
    sx = 1 if i % 2 == 0 else -1
    bench(y, sx*2.3, -sx)
    cyl(f'bin_{y:.0f}', (-sx*2.4, y + 2.4, PLAT_Z + 0.45), 0.25, 0.9, M['iron_dark'])
people = [(-1.4, -10.5, 1.8, (0.08, 0.06, 0.05, 1), True), (1.1, -6.0, 1.66, (0.04, 0.06, 0.12, 1), False),
          (-0.3, 3.0, 1.72, (0.06, 0.06, 0.07, 1), True), (1.6, 15.0, 1.7, (0.1, 0.08, 0.06, 1), False),
          (-1.8, 29.0, 1.78, (0.05, 0.05, 0.07, 1), True), (0.6, 47.0, 1.6, (0.12, 0.05, 0.05, 1), False),
          (-20.5, 8.0, 1.75, (0.05, 0.06, 0.05, 1), True), (19.4, 20.0, 1.7, (0.07, 0.05, 0.04, 1), False),
          (-6.0, 62.0, 1.72, (0.06, 0.05, 0.08, 1), True), (3.5, 63.5, 1.65, (0.1, 0.07, 0.05, 1), False),
          (9.0, 61.0, 1.8, (0.04, 0.04, 0.05, 1), True), (-12.0, 64.0, 1.7, (0.09, 0.06, 0.05, 1), False)]
for i, (x, y, h, c, hat) in enumerate(people):
    figure(f'fig{i}', x, y, h, c, hat)

# hanging platform numbers above each island
for P, (a, b) in zip(ISLANDS, ((1, 2), (3, 4), (5, 6))):
    for side, num in ((-1, a), (1, b)):
        sx = P + side*2.2
        sg = box(f'pnum_{num}', (sx, PY0 + 9.0, 5.2), (1.6, 0.08, 1.1), M['navy']); bevel(sg, 0.02, 2)
        for dz in (0.55, 1.6):
            cyl(f'pnum_rod_{num}_{dz}', (sx, PY0 + 9.0, 5.75 + dz/2), 0.015, dz, M['iron_dark'], segs=8)
        text_obj(f'pnum_txt_{num}', str(num), (sx, PY0 + 8.95, 5.2), FACE_CAM, 0.8, M['white_emit'], 0.004)

# departures board on the concourse
DB_Y, DB_Z, DB_W, DB_H = PY1 + 5.0, 6.0, 12.0, 3.2
for sx in (-1, 1):
    box(f'db_leg_{sx}', (sx*(DB_W/2 - 0.8), DB_Y + 0.2, (DB_Z - DB_H/2 + PLAT_Z)/2), (0.3, 0.3, DB_Z - DB_H/2 - PLAT_Z), M['iron_dark'])
b = box('db', (0, DB_Y, DB_Z), (DB_W, 0.25, DB_H), M['board']); bevel(b, 0.03, 2)
box('db_frame', (0, DB_Y + 0.05, DB_Z), (DB_W + 0.16, 0.2, DB_H + 0.16), M['iron_dark'])
text_obj('db_hdr', "DEPARTURES", (0, DB_Y - 0.14, DB_Z + DB_H/2 - 0.32), FACE_CAM, 0.34, M['white_emit'], 0.004)
rows = [("17:42", "SHEFFIELD", "3", "ON TIME"), ("17:55", "NOTTINGHAM", "4", "ON TIME"),
        ("18:04", "PARIS NORD", "INT", "BOARDING"), ("18:12", "LEICESTER", "2", "DELAYED"),
        ("18:25", "CANTERBURY WEST", "12", "ON TIME"), ("18:31", "BRUSSELS MIDI", "INT", "CHECK IN")]
for i, (t, dest, plat, st) in enumerate(rows):
    z = DB_Z + DB_H/2 - 0.78 - i*0.4
    text_obj(f'db_t_{i}', t, (-DB_W/2 + 0.35, DB_Y - 0.14, z), FACE_CAM, 0.28, M['amber'], 0.003, 'LEFT')
    text_obj(f'db_d_{i}', dest, (-DB_W/2 + 1.9, DB_Y - 0.14, z), FACE_CAM, 0.28, M['amber'], 0.003, 'LEFT')
    text_obj(f'db_p_{i}', plat, (DB_W/2 - 2.9, DB_Y - 0.14, z), FACE_CAM, 0.28, M['amber'], 0.003)
    text_obj(f'db_s_{i}', st, (DB_W/2 - 0.35, DB_Y - 0.14, z), FACE_CAM, 0.26, M['red_led'] if st == 'DELAYED' else M['amber'], 0.003, 'RIGHT')

# red telephone kiosk (K6 proportions) and a pillar box on the concourse
def kiosk(x, y):
    W, Hk = 0.92, 2.42
    base = PLAT_Z
    box('kiosk_plinth', (x, y, base + 0.05), (W + 0.12, W + 0.12, 0.1), M['concrete'])
    k = box('kiosk_body', (x, y, base + 0.1 + (Hk - 0.45)/2), (W, W, Hk - 0.45), M['red']); bevel(k, 0.03, 2)
    for i, (dx, dy, rz) in enumerate(((0, -1, 0), (1, 0, R(90)), (0, 1, R(180)), (-1, 0, R(-90)))):
        cx, cy = x + dx*(W/2 + 0.006), y + dy*(W/2 + 0.006)
        box(f'kiosk_glass_{i}', (cx, cy, base + 1.15), (0.6, 0.012, 1.55), M['kiosk_glass'], rot=(0, 0, rz))
        box(f'kiosk_sign_{i}', (cx, cy, base + Hk - 0.5), (0.68, 0.014, 0.16), M['white_emit'], rot=(0, 0, rz))
        tx, ty = x + dx*(W/2 + 0.016), y + dy*(W/2 + 0.016)
        text_obj(f'kiosk_txt_{i}', "TELEPHONE", (tx, ty, base + Hk - 0.5), (R(90), 0, rz), 0.11, M['black'], 0.002)
    box('kiosk_crown', (x, y, base + Hk - 0.28), (W + 0.06, W + 0.06, 0.12), M['red'])
    for rz in (0, R(90)):
        # a cylinder along x (then y), squashed vertically: two crossing vaults make the K6 roof
        c = cyl(f'kiosk_dome_{rz:.1f}', (x, y, base + Hk - 0.22), W/2 + 0.03, W + 0.06, M['red'], segs=24, rot=(0, R(90), rz))
        c.scale = (0.5, 1, 1)
kiosk(-3.2, PY1 + 3.0)        # in the open middle of the concourse, under the board's left end

def pillar_box(x, y):
    cyl('pbox_base', (x, y, PLAT_Z + 0.08), 0.36, 0.16, M['black'])
    cyl('pbox_body', (x, y, PLAT_Z + 0.75), 0.31, 1.2, M['red'])
    sphere('pbox_cap', (x, y, PLAT_Z + 1.36), 0.36, M['red'], scale=(1, 1, 0.38))
    box('pbox_slot', (x, y - 0.3, PLAT_Z + 1.12), (0.28, 0.04, 0.05), M['black'])
    box('pbox_plate', (x, y - 0.305, PLAT_Z + 0.82), (0.18, 0.01, 0.12), M['gold'])
pillar_box(3.0, PY1 + 2.4)

# ================================================================= world, sun, camera
world = bpy.data.worlds.new('World'); scene.world = world; world.use_nodes = True
wn = world.node_tree; wn.nodes.clear()
wout = wn.nodes.new('ShaderNodeOutputWorld')
sky = wn.nodes.new('ShaderNodeTexSky'); sky.sky_type = 'NISHITA'; sky.sun_disc = False
sky.sun_elevation = R(3.5); sky.sun_rotation = R(180); sky.dust_density = 3.5; sky.air_density = 1.3; sky.ozone_density = 1.5
bg = wn.nodes.new('ShaderNodeBackground'); bg.inputs['Strength'].default_value = 0.4
wn.links.new(sky.outputs[0], bg.inputs['Color']); wn.links.new(bg.outputs[0], wout.inputs['Surface'])
vol = wn.nodes.new('ShaderNodeVolumeScatter'); vol.inputs['Density'].default_value = 0.0045
vol.inputs['Anisotropy'].default_value = 0.55; vol.inputs['Color'].default_value = (0.82, 0.88, 1.0, 1)
wn.links.new(vol.outputs[0], wout.inputs['Volume'])

sun = bpy.data.lights.new('sun', 'SUN'); sun.energy = 7.0; sun.color = (1.0, 0.58, 0.3); sun.angle = R(1.0)
so = bpy.data.objects.new('sun', sun); so.rotation_euler = (R(-(90 - 7)), 0, R(8)); coll.objects.link(so)

cam_d = bpy.data.cameras.new('cam'); cam_d.lens = 20; cam_d.sensor_width = 36
cam_d.dof.use_dof = True; cam_d.dof.focus_distance = 30; cam_d.dof.aperture_fstop = 5.6
cam = bpy.data.objects.new('cam', cam_d); cam.location = (2.4, PY0 + 6.0, PLAT_Z + 1.6)   # off the lamp line, so the clock is clear
cam.rotation_euler = (R(96), 0, R(3.0)); coll.objects.link(cam); scene.camera = cam

# ================================================================= render settings and grade (same pipeline as the station)
scene.render.engine = 'CYCLES'; scene.cycles.device = 'CPU'
scene.render.resolution_x, scene.render.resolution_y = 1920, 1080
if MODE == 'final':
    scene.render.resolution_percentage = 100; scene.cycles.samples = 320
else:
    scene.render.resolution_percentage = 50; scene.cycles.samples = 64
scene.cycles.use_adaptive_sampling = True; scene.cycles.adaptive_threshold = 0.02
scene.cycles.use_denoising = True; scene.cycles.denoiser = 'OPENIMAGEDENOISE'
scene.cycles.max_bounces = 8; scene.cycles.diffuse_bounces = 3; scene.cycles.glossy_bounces = 4
scene.cycles.transmission_bounces = 6; scene.cycles.volume_bounces = 0; scene.cycles.transparent_max_bounces = 12
scene.cycles.caustics_reflective = False; scene.cycles.caustics_refractive = False
scene.cycles.sample_clamp_indirect = 8.0; scene.cycles.blur_glossy = 1.0
scene.cycles.volume_step_rate = 1.0; scene.cycles.volume_max_steps = 256
scene.view_settings.view_transform = 'AgX'; scene.view_settings.look = 'AgX - Medium High Contrast'
scene.view_settings.exposure = 0.5
scene.render.image_settings.file_format = 'PNG'; scene.render.image_settings.color_depth = '16'

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
ld = ct.nodes.new('CompositorNodeLensdist'); ld.inputs['Dispersion'].default_value = 0.01
em = ct.nodes.new('CompositorNodeEllipseMask'); em.width = 1.5; em.height = 1.3
bl = ct.nodes.new('CompositorNodeBlur'); bl.filter_type = 'FAST_GAUSS'; bl.size_x = 400; bl.size_y = 400; bl.use_relative = False
mr = ct.nodes.new('CompositorNodeMapRange'); mr.inputs['From Min'].default_value = 0; mr.inputs['From Max'].default_value = 1
mr.inputs['To Min'].default_value = 0.6; mr.inputs['To Max'].default_value = 1.0
mul = ct.nodes.new('CompositorNodeMixRGB'); mul.blend_type = 'MULTIPLY'
ct.links.new(rl.outputs['Image'], glare.inputs['Image']); ct.links.new(glare.outputs['Image'], cb.inputs['Image'])
ct.links.new(cb.outputs['Image'], ld.inputs['Image'])
ct.links.new(em.outputs['Mask'], bl.inputs['Image']); ct.links.new(bl.outputs['Image'], mr.inputs['Value'])
ct.links.new(ld.outputs['Image'], mul.inputs[1]); ct.links.new(mr.outputs['Value'], mul.inputs[2])
ct.links.new(mul.outputs['Image'], comp.inputs['Image'])

# ================================================================= render
os.makedirs(ROOT + '/renders', exist_ok=True)
if "anim" in ARGS:
    # A  1-96   dolly down the middle island toward the clock
    # B  97-168 from the concourse end of the island, tilt up from the board to the roof and the clock
    SHOTS = [('A', 96), ('B', 72)]
    scene.render.fps = 24
    f, bounds = 1, {}
    for nm, n in SHOTS: bounds[nm] = (f, f + n - 1); f += n
    F0, F1 = 1, f - 1
    scene.frame_start, scene.frame_end = F0, F1
    def key(ob, frame, loc, rot):
        ob.location = loc; ob.keyframe_insert('location', frame=frame)
        ob.rotation_euler = rot; ob.keyframe_insert('rotation_euler', frame=frame)
    def newcam(name, lens, focus, fstop=5.6):
        cd = bpy.data.cameras.new(name); cd.lens = lens; cd.sensor_width = 36
        cd.dof.use_dof = True; cd.dof.focus_distance = focus; cd.dof.aperture_fstop = fstop
        ob = bpy.data.objects.new(name, cd); coll.objects.link(ob); return ob
    a0, a1 = bounds['A']; camA = newcam('camA', 20, 30)
    key(camA, a0, (2.4, PY0 + 2.0, PLAT_Z + 1.55), (R(95), 0, R(3.2))); key(camA, a1, (2.2, PY0 + 12.0, PLAT_Z + 1.9), (R(97), 0, R(2.6)))
    b0, b1 = bounds['B']; camB = newcam('camB', 24, 16)
    key(camB, b0, (0.6, 34.0, PLAT_Z + 1.6), (R(90), 0, R(-2))); key(camB, b1, (0.6, 33.0, PLAT_Z + 1.7), (R(116), 0, R(0)))
    for nm, cam_ob in (('A', camA), ('B', camB)):
        mk = scene.timeline_markers.new(nm, frame=bounds[nm][0]); mk.camera = cam_ob
    scene.camera = camA
    for ob in (camA, camB):
        for fc in ob.animation_data.action.fcurves:
            for kp in fc.keyframe_points: kp.interpolation = 'LINEAR'
    print('SHOTS', bounds, 'TOTAL', F1)
    scene.render.resolution_percentage = 50; scene.cycles.samples = 40
    scene.render.image_settings.file_format = 'PNG'; scene.render.image_settings.color_depth = '8'
    out_dir = f'{ROOT}/renders/london_fly_{TAG}'; os.makedirs(out_dir, exist_ok=True)
    scene.render.filepath = f'{out_dir}/f_'
    if os.environ.get('STATION_FRAMES'):
        a, b = os.environ['STATION_FRAMES'].split('-'); scene.frame_start, scene.frame_end = int(a), int(b)
        print('FRAME RANGE', scene.frame_start, scene.frame_end)
    if os.environ.get('STATION_RES'): scene.render.resolution_percentage = int(os.environ['STATION_RES'])
    if os.environ.get('STATION_SAMPLES'): scene.cycles.samples = int(os.environ['STATION_SAMPLES'])
    bpy.ops.wm.save_as_mainfile(filepath=ROOT + '/london_anim.blend')
    bpy.ops.render.render(animation=True)
    print('RENDERED ANIMATION', scene.render.filepath)
else:
    if os.environ.get('STATION_RES'): scene.render.resolution_percentage = int(os.environ['STATION_RES'])
    if os.environ.get('STATION_SAMPLES'): scene.cycles.samples = int(os.environ['STATION_SAMPLES'])
    bpy.ops.wm.save_as_mainfile(filepath=ROOT + '/london.blend')
    scene.render.filepath = f'{ROOT}/renders/london_{MODE}_{TAG}.png'
    bpy.ops.render.render(write_still=True)
    print('RENDERED', scene.render.filepath, 'objects:', len(bpy.data.objects))
