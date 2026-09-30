<div align="center">

<h2>🗺️ Tianditu EPS Boundary Registration</h2>

**Turn CRS-free Tianditu administrative EPS maps into reviewable GIS boundaries**

[![Python](https://img.shields.io/badge/Python-3.11-blue.svg)](https://www.python.org/)
[![Input](https://img.shields.io/badge/Input-Tianditu%20EPS-2b6cb0.svg)](#supported-scope)
[![Output](https://img.shields.io/badge/Output-GeoPackage-38a169.svg)](#-outputs-and-quality-checks)
[![Use](https://img.shields.io/badge/Use-Research%20cartography-orange.svg)](#️-accuracy-and-limitations)

*Focused on Tianditu administrative maps, with reviewable vectors and QC evidence.*

[🚀 Quick start](#-quick-start) · [🖼️ Examples](#️-examples) · [🛡️ Limitations](#️-accuracy-and-limitations) · [简体中文](README.md)

</div>

---

> [!CAUTION]
> **For research cartography and exploratory analysis only.** Outputs are not a standard map, annotated-map original, legal boundary, or surveying deliverable, and cannot replace authoritative map data. Registration error cannot be zero and no accuracy level is guaranteed. Results depend on reference-boundary accuracy and date, EPS feature complexity, cartographic generalization, shared-boundary length, and review quality. A reference outer boundary does not independently validate internal administrative boundaries. Inspect `qc.json` and `overlay.png` for each run, and follow source-data licenses.

> [!IMPORTANT]
> **Verify both inputs before running.** The source EPS/PDF has no geographic CRS; the reference SHP/GPKG must cover the target area and have a trustworthy CRS. Intersecting their raw bounding boxes cannot establish matching extent. A matching place name or scope confirmation cannot replace the post-fit geometry check. Insufficient evidence produces a `REVIEW_*` status and no final GPKG.

> [!WARNING]
> **Interpret batch previews, unresolved names, and Mode C additions explicitly.** `batch_preview.gpkg` covers only the processed cities. `REGISTERED_REVIEW_NAMES` means registration succeeded but names are not fully confirmed. Mode C adds reference area without source-sheet evidence. None of these is a complete, fully named province deliverable.

## ✨ What it does

This project handles **CRS-free administrative vector EPS/PDF maps**, with Tianditu EPS as the primary example. It extracts administrative polygons, registers them against a trusted boundary supplied by the user, and writes a GeoPackage with QC outputs. A vector PDF can select `source_page`; scans are outside this workflow.

The core workflow uses one source sheet, one reference boundary, and one global transform. It never assigns the reference CRS directly to EPS page coordinates. If the available boundary does not provide a reliable spatial anchor, the workflow stops for review.

### Features

- 🧭 **Tianditu-focused** — the project name, examples, and defaults target Tianditu EPS maps.
- ✂️ **Vector extraction** — reads filled faces or boundary strokes and retains reviewable geometry.
- 📍 **Reference-based registration** — supports matching extents or a verified shared boundary arc.
- 🧩 **Optional city batches** — an explicit manifest runs EPS/PDF maps city by city and merges them after global QC.
- 📦 **Inspectable delivery** — writes administrative units, reference/registered outlines, QC metrics, and an overlay figure.
- 🛑 **Evidence-gated review** — ambiguous scope, boundary bands, islands, required names, transforms, or Mode C ownership stop before partial delivery.

## 🎯 Supported scope

| Input | Support |
|---|---|
| CRS-free administrative EPS exported from Tianditu | **Primary use case** |
| Structurally complete vector PDF maps | Compatible secondary input; examples focus on Tianditu EPS |
| Scans, raster maps, SVG, DXF, or general drawing files | Outside the current runner's scope |

If the input already has a reliable CRS, reproject it in GIS instead.

## Required inputs: EPS map + georeferenced reference boundary

Prepare two separate datasets:

| Dataset | Required file | Requirement |
|---|---|---|
| Map to register | CRS-free administrative `.eps` exported from Tianditu (primary); structurally complete vector `.pdf` (secondary) | Must contain the boundaries to extract. EPS page coordinates have no geographic CRS. |
| Reference boundary | `.shp` or `.gpkg` for the **same city or target area**, with the correct CRS defined | Must provide a location anchor. Prefer matching extent and administrative level. Keep a Shapefile's `.shp/.shx/.dbf/.prj` files together; GeoPackage must contain the correct CRS. |

`reference_boundary` is required and points to the reference dataset, not the EPS. The two files may use different CRSs; output uses the reference CRS. A local map also needs a verified shared boundary arc or another reliable location anchor. Sharing a city name alone cannot locate an interior map with no shared boundary.

## 🚀 Quick start

> Requirements: Node.js/npm (for npx installation) and **Python 3.11**. Commands below use Windows PowerShell. EPS processing also requires Ghostscript.

### 1. Install the Skill and Python dependencies

```powershell
# Installs the skill directly from GitHub; no manual clone is needed.
# Requires Node.js/npm (npx). Reopen Codex after the skill install.
npx skills@latest add zhuangcg/tianditu-eps-boundary-registration --skill tianditu-eps-boundary-registration --agent codex --global --copy --yes
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r https://raw.githubusercontent.com/zhuangcg/tianditu-eps-boundary-registration/main/requirements.txt
```

The npx command installs the skill files and scripts for Codex; the separate pip command installs Python libraries. You do not need to clone the repository. See the [skills CLI documentation](https://www.npmjs.com/package/skills).

On macOS/Linux, create the environment with `python3.11 -m venv .venv` and replace `.venv\Scripts\python.exe` below with `./.venv/bin/python`.

### 2. Install Ghostscript

Install it from the [official downloads page](https://ghostscript.com/releases/) and check that it is available:

```powershell
gswin64c -version
```

Vector PDF does not need Ghostscript. If names in the EPS are outlined and need OCR, install the optional package:

```powershell
.\.venv\Scripts\python.exe -m pip install rapidocr-onnxruntime==1.4.4
```

### 3. Create a case configuration

The commands assume Codex's default user skills directory. If you set a custom `CODEX_HOME`, adjust `$skillRoot` to the installation path.

```powershell
New-Item -ItemType Directory -Force runs | Out-Null
$skillRoot = Join-Path $HOME ".codex\skills\tianditu-eps-boundary-registration"
Copy-Item "$skillRoot\templates\config.example.yaml" runs/my-case.yaml
```

Edit `runs/my-case.yaml` and set at least:

```yaml
# CRS-free administrative vector EPS or PDF.
source_map: "D:/maps/shenzhen-districts.eps"
# Required reference: CRS-defined .shp/.gpkg for the same city or target area
# This is separate from the source EPS/PDF and must have a known, correct CRS.
# For Shapefile, keep .shp/.shx/.dbf/.prj sidecars together; GeoPackage embeds its CRS.
reference_boundary: "D:/gis/shenzhen-boundary.gpkg"
reference_layer: null # set the actual layer name for a multi-layer GeoPackage
admin_level: district
source_scope: same_extent
user_intent: "Extract Shenzhen districts; the sheet and city reference cover the same extent"
output_dir: "runs/my-case/output"
work_dir: "runs/my-case/work"
```

The paths and intent above illustrate the format; replace them with the user's data and actual request. Set `reference_layer` when the GeoPackage has multiple layers. Use `same_extent` when the source and reference cover the same area. Use `shared_boundary` only for a verified common boundary arc. Record `scope_confirmation` only when the user has explicitly confirmed the relationship; an agent must not fill it from a filename guess. If neither condition holds, registration stops instead of forcing an interior map onto a parent outline.

If secondary street labels conflict with district-level administrative fills, inspect the fills and labels first. Record the specific map evidence in `scope_review.admin_level_conflict` only when supported; it does not replace the user's extent confirmation.

The workflow reports reference layers, feature composition, and extent with a side-by-side preview. An EPS/PDF page has no CRS, so its bounding box cannot be spatially intersected with the reference before fitting. Uncertain scope pauses for user confirmation. When a boundary is a filled ribbon, prefer the verified administrative fill boundary and exclude the ribbon; use a ribbon's inner edge only when it is unique and demonstrably faces the target unit. Otherwise, pause for review. Small islands with more than one plausible parent are not assigned by nearest distance. After fitting, whole-extent IoU, bidirectional residuals, and transform uniqueness must pass before a GeoPackage is delivered. Required names get review crops when unresolved; ambiguous Mode C additions stop before delivery.

### 4. Inspect inputs and run

```powershell
$skillRoot = Join-Path $HOME ".codex\skills\tianditu-eps-boundary-registration"
& ".\.venv\Scripts\python.exe" "$skillRoot\scripts\inspect_environment.py" --config runs/my-case.yaml
& ".\.venv\Scripts\python.exe" "$skillRoot\scripts\run.py" --config runs/my-case.yaml
# Only after run.py reports a delivered result:
& ".\.venv\Scripts\python.exe" "$skillRoot\scripts\check_output_manifest.py" runs/my-case/output --config runs/my-case.yaml
```

Run the final manifest check only after `run.py` has delivered. A review status calls for inspecting `work/review.json` first. `--intent` applies only to one map and should quote the user's real request; batch runs use manifest `defaults` and case `options`.

## Agent routing and review

Locate scripts relative to the installed `SKILL.md`. Choose from the user's actual request: `config.example.yaml` for one map, and `batch.example.yaml` **only when multi-city extraction and merging were requested**. Inspect the source preview and reference metadata first, then act on `##VERDICT`. Record an existing user confirmation without asking again. When evidence conflicts, pause; changing labels, lowering thresholds, or selecting a merely similar outline does not establish a valid match.

| Status | Next action |
|---|---|
| `REVIEW_SCOPE` / `NO_COMMON_BOUNDARY` | Compare the sheet and reference layers; ask for a confirmed extent or a reference with a real location anchor if evidence remains insufficient. |
| `REVIEW_EXTRACTION` | Inspect the source, candidate previews, fills, and strokes; leave a ribbon or island unresolved when its inner edge or ownership is unclear. |
| `REVIEW_NAMES` | Inspect `work/review_names.json` and crops; enter only names supported by the sheet. |
| `REVIEW_REGISTRATION` | Check full-extent IoU, both P90 values, and candidate overlays; region confirmation cannot bypass the geometry gate. |
| `REVIEW_CONFORMANCE` | Review Mode C ownership of added areas; do not publish Mode C without a unique source-supported assignment. |
| `REGISTERED_REVIEW_NAMES` | The GPKG was delivered with incomplete names; report blank units from `qc.json` and do not call it fully named. |

> [!NOTE]
> **Automatic release thresholds are not accuracy guarantees.** Same-extent release currently requires IoU ≥ 0.95, full-boundary P90 in both directions ≤ 1% of the reference area-equivalent radius, and a unique transform. Still inspect `overlay.png`, name status, internal boundaries, and reference quality.

## 🖼️ Examples

| Shenzhen district EPS | Luohu street-level EPS |
|:---:|:---:|
| ![Shenzhen example: Tianditu EPS plus a reference boundary produces unfilled solid vector boundaries](docs/images/shenzhen-example.png) | ![Luohu example: Tianditu EPS plus a reference boundary produces unfilled solid vector boundaries](docs/images/luohu-example.png) |
| Same-extent registration; 10 districts extracted. Sampled outline distance: 12.75 m median and 72.99 m P90. No same-level district reference was available to validate internal boundaries. | Uses about 13.76 km of verified shared boundary. Sampled distance: 10.90 m median and 23.63 m P90. About 73.34% of source-outline samples did not participate in fitting. |

These values describe their specific cases and data versions; they are not general accuracy guarantees or acceptance thresholds. Original EPS and reference data are not included. Reproduction requires authorized copies of the matching data.

## 📦 Outputs and quality checks

| File | Contents |
|---|---|
| `registered.gpkg` | Registered administrative units, registered outline, and reference boundary |
| `qc.json` | Scope decision, extraction method, name review, fit parameters, and sampled boundary metrics |
| `overlay.png` | Overlay for reviewing extracted and reference boundaries |
| `run.log` | Run summary |

The default delivery retains geometry extracted from the source map. Consider advanced Mode C only when the EPS and reference have the same extent and the outer outline must conform exactly; it adds area without source-sheet evidence. See [methodology](references/methodology.md).

## Multi-city batch delivery

Use `templates/batch.example.yaml` when the user explicitly requests extraction and merging of multiple cities. One manifest names the common city-level reference, each EPS/PDF and its `parent_id`, shared `defaults`, and per-city `options`. Run `python scripts/run.py --config <batch.yaml>`. Each city retains its Mode R `registered.gpkg` and Mode C `conformed.gpkg`. Province coverage, overlap, and shared borders are checked in `province_qc.json` and `city_adjacency_qc.csv`. A complete passing set publishes `province_conformed.gpkg`; a subset produces only `batch_preview.gpkg`. See the [batch guide](references/batch-hierarchical.md).

> [!WARNING]
> **A `parent_id` is not an extent confirmation.** Check each source sheet against its reference city. Set that case's `options.scope_confirmation` only when the user explicitly confirmed the same extent. If any city needs review, inspect `work/batch_review.json` and `work/<parent_id>/review.json` and withhold the province merge. A `batch_preview.gpkg` from a subset is not a complete province output.

## 🛡️ Accuracy and limitations

- Registration error cannot be eliminated. Accuracy depends on reference data, EPS feature complexity, generalization, shared-boundary length, and review quality.
- A reference outer boundary constrains the overall position and outline; it does not validate internal administrative boundaries by itself.
- Boundary-distance metrics are sampling approximations, not analytic Hausdorff distances or universal acceptance thresholds.
- Do not treat outputs as annotated-map originals, legal boundaries, or surveying results.

## ❓ FAQ

**Can an inland map be registered using only a city or province outline?**

No. The parent outline alone cannot establish the interior map's location. A shared boundary, known control points, or another reliable spatial anchor is required.

**What if administrative names are not recognized?**

The runner preserves stable `admin_id` values and does not guess names. Review OCR status and `qc.json`, then resolve labels manually if needed.

**Does a good outer-boundary fit prove internal boundaries are accurate?**

No. Internal boundaries require independent same-level reference data for validation.

## 🗂️ Project structure

```text
tianditu-eps-boundary-registration/
├── scripts/       # extraction, registration, execution, and output checks
├── templates/     # generic config and run-log templates
├── examples/      # Shenzhen and Luohu case parameters
├── docs/images/   # README case figures
├── references/    # methodology, input contract, and QC definitions
├── tests/         # automated tests
├── SKILL.md       # concise agent workflow
├── README.md      # Chinese documentation
└── README.en.md   # English documentation
```

## 📚 More documentation

| Document | Contents |
|---|---|
| [SKILL.md](SKILL.md) | Tianditu EPS workflow and required safeguards |
| [Generic config](templates/config.example.yaml) | Input, reference, and output settings |
| [Case notes](docs/cases.md) | Shenzhen and Luohu data definitions |
| [Methodology](references/methodology.md) | Extraction, scope, and registration details |
| [QC definitions](references/qc-spec.md) | Quality-check metrics |
| [Input contract](references/input-and-name-contract.md) | Input fields and naming rules |
