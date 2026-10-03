<div align="center">

<h2>🗺️ EPS/PDF Administrative Boundary Registration</h2>

**Turn administrative vector EPS/PDF maps without geographic coordinates into reviewable GIS boundaries**

[![Python](https://img.shields.io/badge/Python-3.11-blue.svg)](https://www.python.org/)
[![Input](https://img.shields.io/badge/Input-Vector%20EPS%2FPDF-2b6cb0.svg)](#supported-scope)
[![Output](https://img.shields.io/badge/Output-GeoPackage-38a169.svg)](#-outputs-and-quality-checks)
[![Use](https://img.shields.io/badge/Use-Research%20cartography-orange.svg)](#️-accuracy-and-limitations)

*Supports vector EPS and PDF; current examples mainly use Tianditu EPS.*

[🚀 Quick start](#-quick-start) · [🖼️ Examples](#️-examples) · [🛡️ Limitations](#️-accuracy-and-limitations) · [简体中文](README.md)

</div>

---

> [!CAUTION]
> **For research mapping and exploratory analysis only.** Results have error; they are not legal boundaries, standard maps, or surveying products. Even an accurate reference outline cannot prove that every internal boundary on the sheet is correct. Check `qc.json` and `overlay.png` before use, and follow the data licenses.

> [!IMPORTANT]
> **First verify what area the sheet depicts.** You need a vector EPS/PDF without geographic coordinates and an SHP/GPKG reference boundary for the same target area with a correct coordinate system. The runner checks their relationship before fitting and their agreement afterward. A matching filename, place name, or raw coordinate range is insufficient; uncertain cases pause without a final output.

> [!WARNING]
> **Interpret outputs carefully.** `batch_preview.gpkg` is created only when every city submitted in this run and the merge checks pass but the reference contains additional cities; it contains only the submitted cities. A district polygon can be placed successfully while its name stays blank because the sheet does not support a reliable reading. “Conform to reference” (Mode C) may add edge areas from the reference that were not drawn on the sheet.

## ✨ What it does

This project places **administrative vector EPS/PDF sheets without geographic coordinates** on a real map and exports a GeoPackage (`.gpkg`) that QGIS and other GIS tools can open. Tianditu EPS is the main example; a multi-page vector PDF can select a page. Photos, scans, and image-only PDFs are outside this workflow.

For one map, provide **one sheet to register** and **one boundary whose real-world location is already known**. The runner extracts administrative areas, compares the two outlines, and finds the sheet's location. It pauses if no reliable match exists.

### Features

- **Extract boundaries:** read filled areas or drawn lines without treating a wide colored border as an administrative area.
- **Verify and locate:** check the depicted area against the reference, then fit the outlines and check for multiple plausible placements.
- **Preserve evidence:** use sheet text or reviewed crops for names; leave uncertain names blank.
- **Optional batches:** process cities one by one and inspect the merged result when the user asks for it.
- **Pause when uncertain:** provide review material instead of a final GPKG when scope, extraction, or fitting lacks evidence.

## 📐 Two output modes

| Mode | What changes | When to use it | File |
|---|---|---|---|
| **Keep the drawn boundaries (Mode R, default)** | Apply one transform to the whole sheet and keep its outer outline. For same-extent sheets only, close narrow interior gaps no wider than 0.25 source-page points at the fitted scale, and only when one adjacent unit is the clear owner. | Usually start here. Shared-border inputs have no full reference mask for this gap check. Ambiguous ownership pauses delivery. | `registered.gpkg` |
| **Conform the outer outline to the reference (Mode C)** | Start with Mode R, then adjust the outside edge to the reference. An edge area not drawn on the sheet may be added to an administrative unit. | **Only when both datasets cover the same full area and an exact outer outline is needed.** Pause if the added area has no clear owner. | Keeps `registered.gpkg` and adds `conformed.gpkg` |

Mode R gap patches are inferred from adjacent boundaries, not drawn-sheet evidence; they appear in the `internal_gap_repairs` layer and `qc.json`. Gaps at the outside edge are left alone. Mode C does not prove that internal boundaries are more accurate. Added areas come from the reference and must be disclosed in the QC report. City batches check Mode C city by city and retain Mode R for comparison.

## 🎯 Supported scope

| Input | Support |
|---|---|
| CRS-free administrative EPS, including Tianditu exports | **Primary use case** |
| Vector PDF with real paths or filled shapes | Read directly; page 1 by default, with an option to select another page |
| Scans, raster maps, SVG, DXF, or general drawing files | Outside the current runner's scope |

If the input already has a reliable geographic coordinate system, reproject it in GIS instead.

## Required inputs: a sheet and a located reference boundary

Prepare two files with **different roles**:

| Dataset | Required file | Requirement |
|---|---|---|
| Sheet to register | Administrative vector `.eps` or `.pdf` | Contains the filled areas or lines to extract but no real-world coordinates |
| Reference boundary | Located `.shp` or `.gpkg` for the target area | Has the **correct coordinate reference system (CRS)**. Keep a Shapefile's `.shp/.shx/.dbf/.prj` files together; choose the right layer if a GeoPackage has several |

In the configuration, `source_map` names the sheet and `reference_boundary` names the located boundary. Set `reference_layer` if the reference GPKG has multiple layers; use `reference.filter` if one layer contains multiple cities. The output uses the reference's CRS, but the runner does not merely assign that CRS to page coordinates.

**The depicted extents must be relatable.** The simplest case is a sheet and reference depicting the same complete area, such as all of Shenzhen; their lines need not coincide before registration. If the sheet shows only part of the reference, this runner needs a verified shared outer border and two points whose locations are known both on the sheet and in the real world. “Both are in Shenzhen” is insufficient. The runner creates a side-by-side preview; the sheet has no geographic coordinates, so its raw numeric bounds cannot be compared directly with the reference's bounds.

**Similar-looking outlines are not proof.** For a wide colored boundary band, prefer the verified administrative fill's edge; use the band's inner edge only if its direction and uniqueness are clear. An uncertain island, name, or placement pauses for review. The fitted whole-sheet boundary must also pass the geometry checks before final delivery.

## 🚀 Quick start

> These are Windows PowerShell commands. Installing the Skill needs Node.js/npm; running it needs **Python 3.11**. **If you only process native vector PDFs, skip Ghostscript in step 2.**

### 1. Install the Skill and Python dependencies

```powershell
# Installs the skill directly from GitHub; no manual clone is needed.
# Requires Node.js/npm (npx). Reopen Codex after the skill install.
npx skills@latest add zhuangcg/eps-pdf-boundary-registration --skill tianditu-eps-boundary-registration --agent codex --global --copy --yes
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r https://raw.githubusercontent.com/zhuangcg/eps-pdf-boundary-registration/main/requirements.txt
```

The npx command installs the skill files and scripts for Codex; the separate pip command installs Python libraries. You do not need to clone the repository. See the [skills CLI documentation](https://www.npmjs.com/package/skills). The `--skill tianditu-eps-boundary-registration` value is the existing Skill install ID; it stays the same after the repository rename.

On macOS/Linux, create the environment with `python3.11 -m venv .venv` and replace `.venv\Scripts\python.exe` below with `./.venv/bin/python`.

### 2. Install Ghostscript for EPS; skip it for native vector PDF

The runner uses Ghostscript to turn EPS into a **vector PDF that still contains paths and fills**, then reads that PDF. A source that is already a vector PDF is read directly, so Ghostscript is not involved. Install Ghostscript from the [official downloads page](https://ghostscript.com/releases/), then check:

```powershell
gswin64c -version
```

An image-only PDF is still unsupported even though it has a `.pdf` extension. If text was converted to shapes and needs automatic text recognition (OCR), you may install OCR separately; OCR and Ghostscript serve different purposes:

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

The paths above are examples; replace them with your own files. The less obvious options are:

| Setting | Plain-language meaning |
|---|---|
| `admin_level: district` | Extract district areas; use `street` for a street-level map. |
| `source_scope: same_extent` | The sheet and reference depict the same complete area. Use `shared_boundary` only for a verified common outer border and provide two reliable location points. With no shared border, this workflow stops. |
| `user_intent` | What the user actually wants and how the sheet relates to the reference; do not copy the sample Shenzhen request. |
| `source_page: 2` | Optional: use page 2 of a vector PDF. Page numbers start at 1; EPS has only page 1. |
| `scope_confirmation` | Optional: record the user's explicit answer. Preserve their wording and state whether it means `same_extent` or `shared_boundary`; never infer a confirmation from a filename. |

If the same reference layer contains several cities, select one with `reference.filter`; see the [configuration template](templates/config.example.yaml). If street labels appear on a map whose intended areas are district fills, inspect the sheet first. Record specific evidence in `scope_review.admin_level_conflict` only when supported; it does not replace the user's extent confirmation.

### 4. Inspect inputs and run

```powershell
$skillRoot = Join-Path $HOME ".codex\skills\tianditu-eps-boundary-registration"
& ".\.venv\Scripts\python.exe" "$skillRoot\scripts\inspect_environment.py" --config runs/my-case.yaml
& ".\.venv\Scripts\python.exe" "$skillRoot\scripts\run.py" --config runs/my-case.yaml
# Only after run.py reports a delivered result:
& ".\.venv\Scripts\python.exe" "$skillRoot\scripts\check_output_manifest.py" runs/my-case/output --config runs/my-case.yaml
```

Run the final file check only after `run.py` reports delivery. If it pauses for review, inspect `work/review.json` and the relevant preview instead of treating the run as complete. The command-line `--intent` flag applies only to one map and must reflect the user's actual request.

## Agent routing and review

Agents should follow this order: **choose one map or a batch → inspect the sheet and reference → run → act on the result**. Use `config.example.yaml` for one map; use `batch.example.yaml` only when the user requests a multi-city merge. Record an existing user confirmation, but do not manufacture a passing result by renaming places or lowering checks.

| Runner status | Meaning and next action |
|---|---|
| `REVIEW_SCOPE` / `NO_COMMON_BOUNDARY` | The sheet/reference relationship is unclear, or they have no common border. Inspect the comparison; ask for a confirmed extent or a better reference when needed. |
| `REVIEW_EXTRACTION` | It is unclear which fills or lines are administrative areas, or which side of a band or island belongs to the target. Inspect local previews. |
| `REVIEW_NAMES` | Complete names were requested, but some lack evidence on the sheet. Inspect text crops rather than guessing. |
| `REVIEW_REGISTRATION` | The fit is poor or several placements are plausible. Inspect the overlay and reference; a correct city name does not override this result. |
| `REVIEW_CONFORMANCE` | A Mode R interior line gap or Mode C added area has no unique owner. Pause delivery and inspect the overlay and review record. |
| `REGISTERED_REVIEW_NAMES` | A boundary file was delivered, but some administrative polygons have blank name fields; disclose that limitation. The default name setting may also permit blank names and record them in `qc.json`. |

> [!NOTE]
> **Numeric thresholds decide automatic delivery; they are not accuracy promises.** For same-extent sheets, the runner checks overlap (IoU, closer to 1 is better), boundary distance (P90 means about 90% of sampled distances are no greater than this value), and whether the placement is unique. Current thresholds are IoU ≥ 0.95 and P90 in both directions ≤ 1% of the reference's area-equivalent radius. A failure goes to review; a pass still calls for checking the overlay and internal boundaries.

## 🖼️ Examples

| Shenzhen district EPS | Luohu street-level EPS |
|:---:|:---:|
| ![Shenzhen example: Tianditu EPS plus a reference boundary produces unfilled solid vector boundaries](docs/images/shenzhen-example.png) | ![Luohu example: Tianditu EPS plus a reference boundary produces unfilled solid vector boundaries](docs/images/luohu-example.png) |
| Both the sheet and reference cover Shenzhen; 10 districts were extracted. Sampled outline-to-reference distance was 12.75 m median and 72.99 m P90. No same-level district reference was available to check internal borders. | Placement used about 13.76 km of verified shared border. Distance was 10.90 m median and 23.63 m P90. About 73.34% of sampled source-outline points were not used for placement. |

These values describe their specific cases and data versions; they are not general accuracy guarantees or acceptance thresholds. Original EPS and reference data are not included. Reproduction requires authorized copies of the matching data.

## 📦 Outputs and quality checks

| File | Contents |
|---|---|
| `registered.gpkg` | Default Mode R; includes `internal_gap_repairs` when same-extent interior gaps were closed |
| `conformed.gpkg` | Only after Mode C succeeds: areas whose outer outline conforms to the reference |
| `qc.json` | Check report: extent evidence, name coverage, boundary agreement, and more |
| `overlay.png` | Picture of the result over the reference for visual checking |
| `run.log` | Run summary |

The output directory is created only after the relevant checks pass. Mode C also writes `conformance_qc.json` with adjusted and added areas. See the [mode comparison](#-two-output-modes) above.

## Multi-city batch delivery

**Batch processing is still available.** When the user asks to merge several cities, copy `templates/batch.example.yaml`. This list (a manifest) names the common city-level reference, each EPS/PDF's city, and any city-specific settings. `parent_id` is the city's ID in the reference; `defaults` holds shared options and `options` holds one city's options. Run `python scripts/run.py --config <batch.yaml>`.

The runner keeps both Mode R and Mode C for each city, then checks for gaps, overlaps, and mismatched borders:

| Situation | Batch output |
|---|---|
| Only some reference cities were submitted, and every submitted city passed its checks | `batch_preview.gpkg`, **containing only the submitted cities**; names unsupported by the sheet may still be blank |
| Every reference city and merge check passed | `province_conformed.gpkg`, plus `province_qc.json` and `city_adjacency_qc.csv` |
| A city needs review, or the merge check fails | No province merge is published; inspect city review material first |

For example, if the reference contains Guangzhou, Foshan, Shenzhen, and more, but this run submits only Guangzhou and Foshan, a passing preview contains only those two cities. If a district outline in Foshan is clear but its printed name is unreadable, the polygon remains in the preview with an empty `admin_name`; the name has not been verified.

See the [batch guide](references/batch-hierarchical.md) for configuration details.

> [!WARNING]
> **A city ID does not prove what area the sheet depicts.** Check every sheet against its reference city. Set that city's `options.scope_confirmation` only when the user explicitly confirmed the extent. If a city pauses, inspect `work/batch_review.json` and `work/<parent_id>/review.json`.

## 🛡️ Accuracy and limitations

- Registration error cannot be eliminated. Results depend on reference quality, how the source sheet was drawn, shared-border length, and review quality.
- A reference outer boundary constrains the overall position and outline; it does not validate internal administrative boundaries by itself.
- Reported boundary distances are approximations from sampled points, not a universal accuracy grade or legal acceptance standard.
- Do not treat outputs as annotated-map originals, legal boundaries, or surveying results.

## ❓ FAQ

**Can an inland map be registered using only a city or province outline?**

No. This runner needs either the same complete extent or a verified shared outer border plus two reliable location points. If the local sheet does not touch the parent outline, this workflow stops; use a more suitable reference or another registration method.

**What if administrative names are not recognized?**

The runner preserves stable `admin_id` values and does not guess names. Review OCR status and `qc.json`, then resolve labels manually if needed.

**Does a good outer-boundary fit prove internal boundaries are accurate?**

No. Internal boundaries require independent same-level reference data for validation.

## 🗂️ Project structure

```text
eps-pdf-boundary-registration/
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
| [SKILL.md](SKILL.md) | Agent execution order and pause rules |
| [Generic config](templates/config.example.yaml) | Input, reference, and output settings |
| [Case notes](docs/cases.md) | Shenzhen and Luohu data definitions |
| [Methodology](references/methodology.md) | Algorithm details for readers who need them |
| [QC definitions](references/qc-spec.md) | Quality-check metrics |
| [Input contract](references/input-and-name-contract.md) | Input fields and naming rules |
