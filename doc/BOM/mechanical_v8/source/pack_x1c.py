"""Prepare one-part, model-only 3MF files for a stock Bambu Lab X1 Carbon.

This is a geometry/placement check, not slicing or printer configuration.
Run: python -B doc/BOM/mechanical_v8/source/pack_x1c.py
Use --input-dir to inspect another revision without changing its source STL.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
from html import escape
import json
import math
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
from zipfile import ZipFile, ZIP_DEFLATED

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT.parents[2] / "tmp" / "cad-runtime"
if RUNTIME.exists():
    sys.path.insert(0, str(RUNTIME))
import numpy as np
import trimesh

BED = np.array([256.0, 256.0])
DEFAULT_HEIGHT = 250.0
EXCLUDED = np.array([[0.0, 0.0], [18.0, 28.0]])
CORE = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
PRINTER_EVIDENCE = {
    "checked_date": "2026-10-23",
    "printer": "Bambu Lab X1 Carbon 0.4 nozzle",
    "official_nominal_build_mm": [256, 256, 256],
    "stock_profile_printable_height_mm": 250,
    "stock_profile_excluded_polygon_xy_mm": [[0, 0], [18, 0], [18, 28], [0, 28]],
    "sources": [
        {"claim": "Nominal build volume 256 x 256 x 256 mm",
         "url": "https://public-cdn.bambulab.com/store/bambulab-X1-carbon-tech-specs.pdf?v=20241019045941"},
        {"claim": "X1 Carbon 0.4 nozzle bed_exclude_area overrides common profile: 0x0,18x0,18x28,0x28",
         "url": "https://github.com/bambulab/BambuStudio/blob/master/resources/profiles/BBL/machine/Bambu%20Lab%20X1%20Carbon%200.4%20nozzle.json"},
        {"claim": "Inherited printable_area 0x0,256x0,256x256,0x256",
         "url": "https://github.com/bambulab/BambuStudio/blob/master/resources/profiles/BBL/machine/fdm_bbl_3dp_001_common.json"},
        {"claim": "Inherited printable_height 250",
         "url": "https://github.com/bambulab/BambuStudio/blob/master/resources/profiles/BBL/machine/fdm_machine_common.json"},
    ],
    "profile_note": "Official upstream source values; the installed Bambu Studio profile was not inspected.",
}


def rotation(axis: str, degrees: float) -> np.ndarray:
    return trimesh.transformations.rotation_matrix(
        math.radians(degrees), {"x": [1, 0, 0], "y": [0, 1, 0], "z": [0, 0, 1]}[axis])


def contact_area(mesh: trimesh.Trimesh, tolerance: float = 0.025) -> float:
    """Area of actual triangles lying at the build-plane, not bbox area."""
    triangles = mesh.triangles
    on_plane = np.max(np.abs(triangles[:, :, 2] - mesh.bounds[0, 2]), axis=1) < tolerance
    downward = mesh.face_normals[:, 2] < -0.99
    return float(mesh.area_faces[on_plane & downward].sum())


def largest_lower_plane(mesh: trimesh.Trimesh, tolerance: float = 0.025) -> dict:
    """Near-bed faces only: internal cap roofs are not service split faces."""
    planar = ((np.ptp(mesh.triangles[:, :, 2], axis=1) < 1e-5)
              & (mesh.face_normals[:, 2] < -0.9999)
              & (mesh.triangles_center[:, 2] <= mesh.bounds[0, 2] + 5.01))
    if not np.any(planar):
        return {"area_mm2": 0.0, "height_above_bottom_mm": None}
    heights = mesh.triangles_center[planar, 2]
    areas = mesh.area_faces[planar]
    keys = np.round(heights / tolerance).astype(np.int64)
    totals = {}
    for key, area in zip(keys, areas):
        totals[int(key)] = totals.get(int(key), 0.0) + float(area)
    key = max(totals, key=totals.get)
    chosen = keys == key
    height = float(np.average(heights[chosen], weights=areas[chosen]) - mesh.bounds[0, 2])
    return {"area_mm2": round(totals[key], 3), "height_above_bottom_mm": round(height, 4)}


def orientation(name: str, original: trimesh.Trimesh) -> tuple[np.ndarray, str, str]:
    # v7/v8 source coordinates: service split is parallel to XZ, at Y=40
    # for arms/hands and Y=-27 for head. Front retains Y<=split: maxY down.
    if name.startswith("SEAM_SPLICE_"):
        return rotation("x", 180), "Rx 180 deg; top nut-pocket face down, locator pegs up; pocket bridges need preview", "defined_splice_pegs_up"
    service_part = any(key in name for key in ("CURVED_ARM_CORE", "WRAP_HAND", "HEAD_"))
    if service_part and (name.endswith("_FRONT") or "HEAD_FRONT" in name):
        return rotation("x", -90), "Rx -90 deg; original max-Y split face down", "defined_service_split"
    if service_part and (name.endswith("_REAR") or "HEAD_REAR" in name):
        return rotation("x", 90), "Rx +90 deg; original min-Y split face down", "defined_service_split"
    flat_z_names = ("PILL_BASE_", "SEAM_PLATE_", "BASE_JOIN", "BASE_ALIGNMENT", "ROUND_YAW_COLLAR", "ROUNDED_PHONE_CRADLE")
    if any(key in name for key in flat_z_names):
        return np.eye(4), "R0; original flat lower-Z face down", "defined_source_base"
    # New pins/plates are included automatically. Unknown names get the largest
    # actual coplanar exterior face among six axial orientations, never a claim
    # that its supports, anisotropic strength or cosmetic finish were verified.
    candidates = [(np.eye(4), "R0"), (rotation("x", 180), "Rx 180"),
                  (rotation("x", 90), "Rx +90"), (rotation("x", -90), "Rx -90"),
                  (rotation("y", 90), "Ry +90"), (rotation("y", -90), "Ry -90")]
    ranked = []
    for matrix, label in candidates:
        mesh = original.copy()
        mesh.apply_transform(matrix)
        ranked.append((contact_area(mesh), -float(mesh.extents[2]), matrix, label))
    best = max(ranked, key=lambda row: row[:2])
    return best[2], best[3] + "; largest axial planar boundary face (automatic)", "automatic_review_required"


def rectangles_overlap(a: np.ndarray, b: np.ndarray) -> bool:
    return bool(np.all(a[1] > b[0] + 1e-7) and np.all(b[1] > a[0] + 1e-7))


def place(mesh: trimesh.Trimesh, brim: float, edge: float) -> tuple[np.ndarray, np.ndarray]:
    """Prefer bed centre; move only if conservative brim bbox hits exclusion."""
    extents = mesh.extents
    if extents[2] > DEFAULT_HEIGHT + 1e-5:
        raise ValueError(f"Height {extents[2]:.3f} exceeds stock-profile 250 mm")
    if np.any(extents[:2] + 2 * (brim + edge) > BED + 1e-5):
        raise ValueError(f"Footprint {extents[:2]} + brim/edge cannot fit stock bed")
    centre = BED / 2
    required_low = np.array([brim + edge, brim + edge])
    required_high = BED - brim - edge - extents[:2]
    central_low = centre - extents[:2] / 2
    choices = [central_low]
    # Rightward or rearward minimal displacement clears the unchanged corner.
    choices += [np.array([max(central_low[0], EXCLUDED[1, 0] + brim + edge), central_low[1]]),
                np.array([central_low[0], max(central_low[1], EXCLUDED[1, 1] + brim + edge)])]
    choices.sort(key=lambda low: float(np.linalg.norm(low + extents[:2] / 2 - centre)))
    for low in choices:
        brim_box = np.array([low - brim, low + extents[:2] + brim])
        if np.all(low >= required_low - 1e-5) and np.all(low <= required_high + 1e-5) and not rectangles_overlap(brim_box, EXCLUDED):
            translation = np.r_[low - mesh.bounds[0, :2], -mesh.bounds[0, 2]]
            return translation, brim_box
    raise ValueError("No checked placement clears stock exclusion with requested brim")


def write_3mf(path: Path, mesh: trimesh.Trimesh, name: str) -> None:
    """3MF Core: one mesh/object/build item, millimetres, actual bed coordinates."""
    ET.register_namespace("", CORE)
    model = ET.Element(f"{{{CORE}}}model", {"unit": "millimeter", "{http://www.w3.org/XML/1998/namespace}lang": "en-US"})
    for key, value in [("Title", name), ("Application", "Fold Wing Buddy geometry packer"),
                       ("Description", "Model only; one part; no slicer profile, brim geometry or G-code")]:
        ET.SubElement(model, f"{{{CORE}}}metadata", {"name": key}).text = value
    resources = ET.SubElement(model, f"{{{CORE}}}resources")
    obj = ET.SubElement(resources, f"{{{CORE}}}object", {"id": "1", "type": "model", "name": name})
    mesh_node = ET.SubElement(obj, f"{{{CORE}}}mesh")
    vertices = ET.SubElement(mesh_node, f"{{{CORE}}}vertices")
    for v in mesh.vertices:
        ET.SubElement(vertices, f"{{{CORE}}}vertex", {axis: f"{float(n):.8f}" for axis, n in zip("xyz", v)})
    triangles = ET.SubElement(mesh_node, f"{{{CORE}}}triangles")
    for face in mesh.faces:
        ET.SubElement(triangles, f"{{{CORE}}}triangle", {f"v{i + 1}": str(int(n)) for i, n in enumerate(face)})
    build = ET.SubElement(model, f"{{{CORE}}}build")
    ET.SubElement(build, f"{{{CORE}}}item", {"objectid": "1"})
    content_types = '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>'
    relationships = '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>'
    with ZipFile(path, "w", ZIP_DEFLATED) as package:
        package.writestr("[Content_Types].xml", content_types)
        package.writestr("_rels/.rels", relationships)
        package.writestr("3D/3dmodel.model", ET.tostring(model, encoding="utf-8", xml_declaration=True))


def verify_3mf(path: Path, expected: trimesh.Trimesh) -> dict:
    with ZipFile(path) as package:
        if package.testzip() is not None:
            raise ValueError(f"Corrupt archive: {path}")
        root = ET.fromstring(package.read("3D/3dmodel.model"))
    ns = {"m": CORE}
    objs = root.findall("m:resources/m:object", ns)
    items = root.findall("m:build/m:item", ns)
    if root.attrib.get("unit") != "millimeter" or len(objs) != 1 or len(items) != 1:
        raise ValueError(f"Invalid one-object millimetre 3MF: {path}")
    vs = [[float(v.attrib[a]) for a in "xyz"] for v in root.findall(".//m:vertex", ns)]
    fs = [[int(t.attrib[f"v{i}"]) for i in (1, 2, 3)] for t in root.findall(".//m:triangle", ns)]
    checked = trimesh.Trimesh(vertices=vs, faces=fs, process=False)
    if not checked.is_watertight or not np.allclose(checked.bounds, expected.bounds, atol=1e-6):
        raise ValueError(f"3MF roundtrip mismatch: {path}")
    return {"zip_crc": "pass", "unit": "millimeter", "objects": 1, "build_items": 1,
            "watertight": True, "bounds_roundtrip": "pass"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def path_label(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def write_overview(path: Path, records: list[dict]) -> None:
    """Static SVG: footprint + reserved brim rectangle; no fabricated toolpath."""
    columns = 4
    cw, ch = 330, 348
    rows = math.ceil(len(records) / columns)
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{cw*columns}" height="{70+ch*rows}" viewBox="0 0 {cw*columns} {70+ch*rows}">',
           '<rect width="100%" height="100%" fill="#f6f5f0"/>',
           '<g font-family="Arial,sans-serif" fill="#243129">',
           '<text x="20" y="28" font-size="21">X1 Carbon / one part per model 3MF / mm</text>',
           f'<text x="20" y="51" font-size="14">Static bbox placement only. Dashed: {records[0]["brim_width_reserved_mm"]:g} mm brim reservation. Red: stock 18 x 28 exclusion. No slicing performed.</text>']
    for index, record in enumerate(records):
        x0, y0 = 22 + (index % columns) * cw, 102 + (index // columns) * ch
        bounds = np.asarray(record["plate_bbox_mm"])
        brim = np.asarray(record["brim_bbox_xy_mm"])
        svg += [f'<text x="{x0}" y="{y0-13}" font-size="12">{index+1:02d} {escape(record["part"])}</text>',
                f'<g transform="translate({x0},{y0})">',
                '<rect width="256" height="256" fill="white" stroke="#708478"/>',
                '<rect x="0" y="228" width="18" height="28" fill="#d55145"/>']
        for box, style in [(brim, 'fill="none" stroke="#c18d2e" stroke-dasharray="4 3"'),
                           (bounds[:, :2], 'fill="#dce7d8" stroke="#506a49"')]:
            size = box[1] - box[0]
            svg += [f'<rect x="{box[0,0]:.3f}" y="{256-box[1,1]:.3f}" width="{size[0]:.3f}" height="{size[1]:.3f}" {style}/>']
        dims = record["oriented_bbox_mm"]
        svg += ['<text x="0" y="272" font-size="11">Front-left = (0,0); centre = (128,128)</text>',
                f'<text x="0" y="287" font-size="12">{dims[0]:.2f} x {dims[1]:.2f}; height {dims[2]:.2f}</text>',
                f'<text x="0" y="302" font-size="11">{escape(record["orientation_status"])}</text>', '</g>']
    path.write_text("\n".join(svg + ['</g></svg>']), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=ROOT / "stl")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "print")
    parser.add_argument("--brim", type=float, default=5.0, help="Reserved bbox expansion, not generated brim geometry")
    parser.add_argument("--edge-clearance", type=float, default=1.0)
    args = parser.parse_args()
    if args.brim < 0 or args.edge_clearance < 0:
        parser.error("brim and edge clearance must be nonnegative")
    inputs = sorted(args.input_dir.glob("*.stl"))
    if not inputs:
        parser.error(f"No *.stl source files found in {args.input_dir}")
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    for folder in ("oriented_stl", "single_part_3mf"):
        (output / folder).mkdir(exist_ok=True)
    records = []
    for source in inputs:
        original = trimesh.load(str(source), force="mesh", process=True)
        components = len(original.split(only_watertight=False))
        if not original.is_watertight or not original.is_winding_consistent or original.volume <= 0 or components != 1:
            raise ValueError(f"Source is not one closed consistent positive-volume mesh: {source}")
        transform, description, status = orientation(source.stem, original)
        oriented = original.copy()
        oriented.apply_transform(transform)
        flatten = -oriented.bounds[0]
        oriented.apply_translation(flatten)
        plane_area = contact_area(oriented)
        lower_plane = largest_lower_plane(oriented)
        if plane_area < 1:
            status += "; small_or_nonplanar_contact_review_required"
        gap = lower_plane["height_above_bottom_mm"]
        if status.startswith("defined_service_split") and gap is not None and gap > 0.1:
            status += "; broad_split_plane_lifted_support_required"
        stl_path = output / "oriented_stl" / (source.stem + ".stl")
        oriented.export(str(stl_path))
        stl_check = trimesh.load(str(stl_path), force="mesh", process=True)
        if not stl_check.is_watertight or not np.allclose(stl_check.bounds, oriented.bounds, atol=1e-4):
            raise ValueError(f"Oriented STL roundtrip mismatch: {stl_path}")
        translation, brim_box = place(oriented, args.brim, args.edge_clearance)
        on_bed = oriented.copy()
        on_bed.apply_translation(translation)
        package = output / "single_part_3mf" / (source.stem + ".3mf")
        write_3mf(package, on_bed, source.stem)
        check = verify_3mf(package, on_bed)
        matrix = transform.copy()
        matrix[:3, 3] += flatten + translation
        records.append({
            "part": source.stem, "quantity": 4 if source.stem == "HAND_DOWEL_4x6" else 1, "source_stl": path_label(source),
            "source_sha256": sha256(source), "source_bbox_mm": original.extents.tolist(),
            "orientation": description, "orientation_status": status,
            "oriented_bbox_mm": oriented.extents.tolist(), "bottom_planar_triangle_area_mm2": round(plane_area, 3),
            "largest_downward_plane_within_5mm_of_bottom": lower_plane,
            "plate_bbox_mm": on_bed.bounds.tolist(), "plate_bbox_centre_xy_mm": on_bed.bounds.mean(axis=0)[:2].tolist(),
            "brim_width_reserved_mm": args.brim, "brim_bbox_xy_mm": brim_box.tolist(),
            "source_to_plate_transform_4x4": matrix.tolist(),
            "bed_boundary_with_brim": "pass", "stock_exclusion_with_brim": "pass",
            "stock_250_height": "pass", "watertight": True, "connected_components": components,
            "oriented_stl": path_label(stl_path), "oriented_stl_sha256": sha256(stl_path),
            "model_3mf": path_label(package), "model_3mf_sha256": sha256(package), "model_3mf_checks": check,
            "support": "candidate direction only; slicer preview and support placement required",
            "sliced": False, "physical_print_verified": False,
        })
    manifest = {"generated_at_utc": datetime.now(timezone.utc).isoformat(), "units": "mm",
                "input_dir": path_label(args.input_dir), "format": "3MF Core model only; one object per file",
                "printer_evidence": PRINTER_EVIDENCE, "brim_is_reserved_only": True,
                "edge_clearance_mm": args.edge_clearance, "part_count": len(records),
                "physical_part_count": sum(record["quantity"] for record in records),
                "all_static_checks_pass": True, "slicer_import_verified": False,
                "slicing_performed": False, "physical_print_verified": False,
                "limitations": ["No Bambu preset/material/process profile, support or G-code is included.",
                                "The brim reservation is an axis-aligned bbox expansion at every height, not a real toolpath.",
                                "Purge lines, prime towers, support growth and head travel are not checked.",
                                "Automatic directions and planar contact area do not validate strength or adhesion.",
                                "Opening a model may cause a slicer to recenter it; compare its position against this manifest."],
                "parts": records}
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with (output / "manifest.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["part", "quantity", "print_x_mm", "print_y_mm", "print_z_mm", "orientation", "contact_area_mm2", "exclusion_and_reserved_brim", "sliced", "3mf"])
        for record in records:
            writer.writerow([record["part"], record["quantity"], *[round(v, 3) for v in record["oriented_bbox_mm"]],
                             record["orientation"], record["bottom_planar_triangle_area_mm2"], "PASS", False, record["model_3mf"]])
    write_overview(output / "bed_overview.svg", records)
    (output / "printer_evidence.json").write_text(json.dumps(PRINTER_EVIDENCE, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"parts": len(records), "output": str(output), "all_static_checks_pass": True,
                      "largest_print_height_mm": max(r["oriented_bbox_mm"][2] for r in records),
                      "sliced": False, "physical_print_verified": False}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
