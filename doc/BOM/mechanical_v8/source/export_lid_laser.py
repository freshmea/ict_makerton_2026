"""Export the three existing lids as two laser-cut plates, without kerf offset.

Run with Python 3.9 and the repository's tmp/cad-runtime dependencies.
The STEP curves are rational B-splines representing circles. Recover their
analytic circles, verify against the source, and write closed DXF polylines.
"""
from pathlib import Path
import hashlib
import json
import math
import sys
from zipfile import ZipFile, ZIP_DEFLATED

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "tmp/cad-runtime"))
import cadquery as cq
import ezdxf
import numpy as np
import trimesh
from ezdxf import bbox
from ezdxf.math import bulge_to_arc
from shapely.geometry import Polygon
from shapely.ops import unary_union
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as PlotPolygon

BASE = ROOT / "doc/BOM/mechanical_v8"
OUT = BASE / "laser_cut/pill_base_lid_2parts"
BULGE = math.tan(math.pi / 8)
# XY in the original assembly frame. Split at assembly X=0.
HOLES = [(-290, -72), (-290, 78), (-94, 78),
         (94, 78), (290, -72), (290, 78)]
RECTS = [(-307, 28, -243, 52), (2.5, -7.5, 47.5, 17.5),
         (243, 28, 307, 52)]
LEFT = [(45, 0, 0), (320, 0, 0), (320, 200, 0),
        (45, 200, BULGE), (0, 155, 0), (0, 45, BULGE)]
RIGHT = [(0, 0, 0), (275, 0, BULGE), (320, 45, 0),
         (320, 155, BULGE), (275, 200, 0), (0, 200, 0)]
FULL = [(45, 0, 0), (595, 0, BULGE), (640, 45, 0),
        (640, 155, BULGE), (595, 200, 0), (45, 200, BULGE),
        (0, 155, 0), (0, 45, BULGE)]


def source_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fit_circle(edge):
    pts = np.array([edge.positionAt(t).toTuple()[:2]
                    for t in np.linspace(0, 1, 257)])
    a = np.column_stack([2 * pts[:, 0], 2 * pts[:, 1], np.ones(len(pts))])
    fit = np.linalg.lstsq(a, (pts * pts).sum(axis=1), rcond=None)[0]
    radius = math.sqrt(fit[2] + sum(fit[:2] ** 2))
    error = max(abs(np.linalg.norm(pts - fit[:2], axis=1) - radius))
    return fit[:2], radius, float(error)


def wire_polygon(wire):
    segments = []
    for edge in wire.Edges():
        ts = [0, 1] if edge.geomType() == "LINE" else np.linspace(0, 1, 1025)
        segments.append([(p.x, p.y) for p in (edge.positionAt(t) for t in ts)])
    points = segments.pop(0)
    while segments:
        for index, segment in enumerate(segments):
            if math.dist(points[-1], segment[0]) < 1e-6:
                points.extend(segment[1:])
                segments.pop(index)
                break
            if math.dist(points[-1], segment[-1]) < 1e-6:
                points.extend(segment[-2::-1])
                segments.pop(index)
                break
        else:
            raise ValueError("Disconnected source wire")
    assert math.dist(points[0], points[-1]) < 1e-6
    return Polygon(points)


def face_polygon(face):
    outer = wire_polygon(face.outerWire())
    for wire in face.innerWires():
        outer = outer.difference(wire_polygon(wire))
    assert outer.is_valid
    return outer


def add_part(doc, side, offset=(0, 0)):
    msp = doc.modelspace()
    vertices = {"LEFT": LEFT, "RIGHT": RIGHT, "FULL": FULL}[side]
    ox, oy = offset
    msp.add_lwpolyline([(x + ox, y + oy, b) for x, y, b in vertices],
                       format="xyb", close=True, dxfattribs={"layer": "CUT_OUTER"})
    tx = 320 if side in ("LEFT", "FULL") else 0
    for x, y in HOLES:
        if side == "FULL" or (x < 0) == (side == "LEFT"):
            msp.add_circle((x + tx + ox, y + 100 + oy), 1.7,
                           dxfattribs={"layer": "CUT_INNER"})
    for x0, y0, x1, y1 in RECTS:
        if side == "FULL" or (x1 < 0) == (side == "LEFT"):
            msp.add_lwpolyline([(x + tx + ox, y + 100 + oy)
                               for x, y in [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]],
                               close=True, dxfattribs={"layer": "CUT_INNER"})


def dxf_polygon(doc):
    # Independently reconstruct closed regions from the written DXF geometry.
    outers, inners = [], []
    for entity in doc.modelspace():
        if entity.dxftype() == "CIRCLE":
            c, r = entity.dxf.center, entity.dxf.radius
            points = [(c.x + r * math.cos(t), c.y + r * math.sin(t))
                      for t in np.linspace(0, 2 * math.pi, 4097)]
        else:
            vertices = list(entity.get_points("xyb"))
            points = []
            for i, (x, y, bulge) in enumerate(vertices):
                end = vertices[(i + 1) % len(vertices)][:2]
                if bulge == 0:
                    points.append((x, y))
                else:
                    assert bulge > 0
                    center, start, finish, radius = bulge_to_arc((x, y), end, bulge)
                    while finish <= start:
                        finish += 2 * math.pi
                    points.extend([(center.x + radius * math.cos(t), center.y + radius * math.sin(t))
                                   for t in np.linspace(start, finish, 1025)[:-1]])
        p = Polygon(points)
        assert p.is_valid and p.area > 0
        (outers if entity.dxf.layer == "CUT_OUTER" else inners).append(p)
    return unary_union(outers).difference(unary_union(inners))


def write_dxf(filename, parts):
    doc = ezdxf.new("R2010", setup=False, units=ezdxf.units.MM)
    doc.header["$MEASUREMENT"] = 1
    doc.layers.new("CUT_OUTER", dxfattribs={"color": 7})
    doc.layers.new("CUT_INNER", dxfattribs={"color": 1})
    for side, offset in parts:
        add_part(doc, side, offset)
    path = OUT / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(path)
    reread = ezdxf.readfile(path)
    audit = reread.audit()
    assert not audit.errors and not audit.fixes
    assert reread.units == ezdxf.units.MM
    assert all(e.dxftype() == "CIRCLE" or
               (e.dxftype() == "LWPOLYLINE" and e.closed) for e in reread.modelspace())
    keys = [str(e.dxftype()) + str(e.dxfattribs().get("center", "")) +
            str(list(e.get_points()) if e.dxftype() == "LWPOLYLINE" else e.dxf.radius)
            for e in reread.modelspace()]
    assert len(set(keys)) == len(keys), "Duplicate cut contours"
    bounds = bbox.extents(reread.modelspace())
    info = {"file": filename, "sha256": source_hash(path), "units": "mm",
            "bbox_mm": [list(bounds.extmin), list(bounds.extmax)],
            "entity_counts": {kind: len(reread.modelspace().query(kind))
                              for kind in ["LWPOLYLINE", "CIRCLE", "SPLINE", "TEXT"]},
            "all_contours_closed": True, "dxf_audit": "pass"}
    return dxf_polygon(reread), info


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    sources, polygons, solids, curve_errors = [], [], [], []
    found_holes, found_rects, found_corners = set(), set(), set()
    stl_polygons = []
    for i in range(1, 4):
        step = BASE / f"cad/PILL_BASE_LID_{i}.step"
        stl = BASE / f"print/oriented_stl/PILL_BASE_LID_{i}.stl"
        solid = cq.importers.importStep(str(step)).val()
        assert solid.isValid() and len(solid.Solids()) == 1
        solids.append(solid)
        top = max((f for f in solid.Faces() if f.geomType() == "PLANE"
                   and f.normalAt().z > .99), key=lambda f: f.Center().z)
        assert abs(top.Center().z - 100) < 1e-7
        assert abs(solid.BoundingBox().zlen - 4) < 1e-5
        polygons.append(face_polygon(top))
        for edge in top.Edges():
            if edge.geomType() == "BSPLINE":
                center, radius, error = fit_circle(edge)
                curve_errors.append(error)
                assert error < 1e-6
                if abs(radius - 1.7) < 1e-6:
                    found_holes.add(tuple(np.round(center, 6)))
                else:
                    assert abs(radius - 45) < 1e-6
                    found_corners.add(tuple(np.round(center, 6)))
        for wire in top.innerWires():
            if all(e.geomType() == "LINE" for e in wire.Edges()):
                b = wire.BoundingBox()
                found_rects.add(tuple(round(v, 6) for v in (b.xmin, b.ymin, b.xmax, b.ymax)))
        mesh = trimesh.load(str(stl), force="mesh")
        assert mesh.is_watertight
        mesh.apply_translation((-320 + (i - 1) * (640 / 3), -100, 96))
        triangles = mesh.triangles
        top_triangles = triangles[np.all(np.abs(triangles[:, :, 2] - 100) < 1e-5, axis=1)]
        assert len(top_triangles) > 0
        stl_polygons.append(unary_union([Polygon(t[:, :2]) for t in top_triangles]))
        sources.append({"step": str(step.relative_to(ROOT)), "step_sha256": source_hash(step),
                        "oriented_stl": str(stl.relative_to(ROOT)), "stl_sha256": source_hash(stl)})
    assert found_holes == set(HOLES)
    assert found_rects == set(RECTS)
    assert found_corners == {(-275, -55), (-275, 55), (275, -55), (275, 55)}
    union_solid = solids[0].fuse(*solids[1:]).clean()
    assert union_solid.isValid() and len(union_solid.Solids()) == 1
    left, li = write_dxf("PILL_BASE_LID_LEFT_320x200.dxf", [("LEFT", (0, 0))])
    right, ri = write_dxf("PILL_BASE_LID_RIGHT_320x200.dxf", [("RIGHT", (0, 0))])
    _, bi = write_dxf("PILL_BASE_LID_BOTH_320x410.dxf",
                      [("LEFT", (0, 0)), ("RIGHT", (0, 210))])
    full, fi = write_dxf("reference/PILL_BASE_LID_MERGED_640x200.dxf", [("FULL", (0, 0))])
    from shapely.affinity import translate
    assembled = unary_union([translate(left, xoff=-320, yoff=-100),
                            translate(right, yoff=-100)])
    source_union = unary_union(polygons)
    stl_union = unary_union(stl_polygons)
    full_world = translate(full, xoff=-320, yoff=-100)
    seam_error = assembled.symmetric_difference(full_world).area
    step_error = assembled.boundary.hausdorff_distance(source_union.boundary)
    stl_error = assembled.boundary.hausdorff_distance(stl_union.boundary)
    assert seam_error < 1e-6
    assert step_error < .002, step_error
    assert stl_error < .1, stl_error
    assert len(left.interiors) == 4 and len(right.interiors) == 5
    report = {"created_date": "2026-10-25", "units": "mm", "scale": 1,
              "sheet_thickness_mm": 4, "kerf_compensation_mm": 0,
              "split_assembly_x_mm": 0, "sources": sources, "files": [li, ri, bi, fi],
              "circle_fit_max_radial_error_mm": max(curve_errors),
              "source_step_sampled_boundary_hausdorff_mm": step_error,
              "source_stl_boundary_hausdorff_mm": stl_error,
              "assembled_vs_merged_symmetric_difference_mm2": seam_error,
              "original_seams_removed_x_mm": [-640/6, 640/6],
              "holes_assembly_xy_mm": HOLES, "hole_diameter_mm": 3.4,
              "rectangles_assembly_xyxy_mm": RECTS, "outer_corner_radius_mm": 45,
              "holes_total": 6, "rectangular_openings_total": 3,
              "central_rect_to_new_seam_mm": 2.5,
              "physical_cut_tested": False, "machine_work_area_verified": False,
              "validation": "PASS; circle recovery checked against STEP; DXF read-back, closedness, units, extents, topology, union and STL comparison checked"}
    (OUT / "verification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    fig, axes = plt.subplots(2, 1, figsize=(12, 8), gridspec_kw={"height_ratios": [1, 1.15]})
    for poly, color, ax in [(assembled, "#e5eef6", axes[0]),
                             (left, "#d9ece6", axes[1]),
                             (translate(right, xoff=340), "#e5e1f3", axes[1])]:
        ax.add_patch(PlotPolygon(list(poly.exterior.coords), facecolor=color, edgecolor="#17364c", lw=1))
        for ring in poly.interiors:
            ax.add_patch(PlotPolygon(list(ring.coords), facecolor="white", edgecolor="#17364c", lw=.8))
    axes[0].axvline(0, color="#d2533d", linestyle="--", lw=1)
    axes[0].set_title("Merged lid: 640 x 200 mm | split at assembly X = 0", loc="left", fontsize=13)
    axes[0].set_xlim(-340, 340); axes[0].set_ylim(-120, 120)
    axes[1].set_title("Cut 1 LEFT: 320 x 200 mm          Cut 2 RIGHT: 320 x 200 mm", loc="left", fontsize=13)
    axes[1].set_xlim(-20, 680); axes[1].set_ylim(-35, 235)
    axes[1].text(330, -28, "4 mm sheet | 6 holes dia. 3.4 mm | R45 corners | no kerf offset", ha="center", fontsize=10)
    for ax in axes:
        ax.set_aspect("equal"); ax.set_xlabel("mm"); ax.set_ylabel("mm")
        ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(OUT / "preview.png", dpi=180)
    plt.close(fig)
    bundle = OUT.parent / "PILL_BASE_LID_LASER_2PARTS.zip"
    with ZipFile(bundle, "w", ZIP_DEFLATED) as archive:
        for path in sorted(OUT.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(OUT))
    print(json.dumps({"output": str(OUT), "bundle": str(bundle),
                      "step_deviation_mm": step_error, "stl_deviation_mm": stl_error,
                      "seam_area_error_mm2": seam_error, "files": [li, ri, bi, fi]}, indent=2))


if __name__ == "__main__":
    main()
