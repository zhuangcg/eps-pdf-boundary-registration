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

## ✨ What it does

This project is designed for **CRS-free administrative EPS maps obtained from Tianditu**. It extracts administrative polygons, registers them against a trusted boundary supplied by the user, and writes a GeoPackage with QC outputs.

The core workflow uses one source sheet, one reference boundary, and one global transform. It never assigns the reference CRS directly to EPS page coordinates. If the available boundary does not provide a reliable spatial anchor, the workflow stops for review.

### Features

- 🧭 **Tianditu-focused** — the project name, examples, and defaults target Tianditu EPS maps.
- ✂️ **Vector extraction** — reads filled faces or boundary strokes and retains reviewable geometry.
- 📍 **Reference-based registration** — supports matching extents or a verified shared boundary arc.
- 📦 **Inspectable delivery** — writes administrative units, reference/registered outlines, QC metrics, and an overlay figure.

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
# Primary input: a CRS-free Tianditu administrative EPS (vector PDF is secondary).
source_map: "D:/maps/tianditu-districts.eps"
# Required reference: CRS-defined .shp/.gpkg for the same city or target area
# This is separate from the source EPS/PDF and must have a known, correct CRS.
# For Shapefile, keep .shp/.shx/.dbf/.prj sidecars together; GeoPackage embeds its CRS.
reference_boundary: "D:/gis/same-area-reference.gpkg"
reference_layer: boundaries # only for a multi-layer GeoPackage
admin_level: district
source_scope: same_extent
output_dir: "runs/my-case/output"
work_dir: "runs/my-case/work"
```

Set `reference_layer` when the GeoPackage has multiple layers. Use `same_extent` when the source and reference cover the same area. Use `shared_boundary` only for a verified common boundary arc. If neither condition holds, registration stops instead of forcing an interior map onto a parent outline.

### 4. Inspect inputs and run

```powershell
$skillRoot = Join-Path $HOME ".codex\skills\tianditu-eps-boundary-registration"
& ".\.venv\Scripts\python.exe" "$skillRoot\scripts\inspect_environment.py" --config runs/my-case.yaml
& ".\.venv\Scripts\python.exe" "$skillRoot\scripts\run.py" --config runs/my-case.yaml --intent "Extract district boundaries; the sheet and reference cover the same extent"
& ".\.venv\Scripts\python.exe" "$skillRoot\scripts\check_output_manifest.py" runs/my-case/output --config runs/my-case.yaml
```

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
