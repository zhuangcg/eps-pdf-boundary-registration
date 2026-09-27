## From Tianditu EPS to Reviewable GIS Boundaries

[简体中文](README.md)

Designed for CRS-free administrative EPS maps obtained from Tianditu, with vector PDF also supported. The workflow extracts map faces, estimates one global page-to-map transform from a trusted reference boundary, and writes reviewable GeoPackage vectors and QC figures.

> [!CAUTION]
> **For research cartography and exploratory analysis only.** Outputs are not an authoritative or standard map, an annotated-map original, a legal boundary, or a surveying deliverable. Registration error cannot be zero, and no accuracy level is guaranteed. Results depend on the accuracy and date of the reference boundary, the complexity of EPS map features, cartographic generalization, the length of shared boundary, and review quality. A reference outer boundary does not independently validate internal boundaries. Inspect `qc.json` and `overlay.png` for every case, and follow the source-data licenses.

### From input to result

The three panels show: **EPS vector map + reference boundary = registered vector result**. The reference and result use unfilled solid boundary lines, and the right panel has no legend. See the GeoPackage and QC files for data and review details.

![Shenzhen workflow: EPS vector map plus reference boundary data produces registered vector results](docs/images/shenzhen-example.png)

The runner supports EPS and vector PDF. SVG, DXF, and raster maps are not supported. EPS conversion requires Ghostscript. Source maps and reference data are not included in this repository.

### Install

Python 3.11 is required; the dependency file is pinned from a Python 3.11 environment. Commands below use Windows PowerShell.

Clone or download the repository from GitHub, open the `eps-vector-boundary-registration` root folder in a terminal, then run:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

On macOS/Linux, create the environment with `python3.11 -m venv .venv` and replace `.venv\Scripts\python.exe` in later commands with `./.venv/bin/python`. Use `mkdir -p runs` and `cp templates/config.example.yaml runs/my-case.yaml` to copy the config.

For EPS files, install Ghostscript from the [official downloads page](https://ghostscript.com/releases/) and make `gswin64c` (Windows) or `gs` (macOS/Linux) available on `PATH`. Verify with:

```powershell
gswin64c -version
```

Vector PDF does not need Ghostscript. If administrative names are outlined and need OCR, install the optional dependency:

```powershell
.\.venv\Scripts\python.exe -m pip install rapidocr-onnxruntime==1.4.4
```

### Run a new case

From the repository root, copy the generic configuration and edit its paths and layer name. Set `reference_layer` when the reference GeoPackage contains multiple layers. Absolute paths are recommended.

```powershell
New-Item -ItemType Directory -Force runs | Out-Null
Copy-Item templates/config.example.yaml runs/my-case.yaml
```

Set at least these values in `runs/my-case.yaml`:

```yaml
source_map: "D:/maps/my-map.eps"
reference_boundary: "D:/gis/reference.gpkg"
reference_layer: reference_layer
admin_level: district
source_scope: same_extent
output_dir: "runs/my-case/output"
work_dir: "runs/my-case/work"
```

Choose `admin_level` and `source_scope` from the evidence: use `same_extent` for matching extents; use `shared_boundary` for a verified continuous shared outer arc and provide two checked landmarks. With no shared boundary, the workflow stops instead of forcing an interior map onto a parent outline. Keep `auto` when the relationship is uncertain and resolve the review prompt.

```powershell
.\.venv\Scripts\python.exe scripts/inspect_environment.py --config runs/my-case.yaml
.\.venv\Scripts\python.exe scripts/run.py --config runs/my-case.yaml --intent "Extract district boundaries; the source sheet and reference cover the same extent"
.\.venv\Scripts\python.exe scripts/check_output_manifest.py runs/my-case/output --config runs/my-case.yaml
```

A typical Mode R delivery contains `registered.gpkg`, `qc.json`, `overlay.png`, and `run.log`. Consider Mode C only when the EPS and reference have the same extent. Added area used to conform an outer outline has no source-sheet evidence and must be interpreted separately from Mode R.

### Examples

#### Shenzhen district map: full-outline registration

The unified runner extracted 10 districts and recognized 10 map names. In this run, the sampled outline distance was 12.75 m median and 72.99 m P90. No same-level district reference was available, so these numbers do not validate internal district boundaries. They describe this case and data version only.

#### Luohu street map: registration from a shared boundary arc

![Luohu workflow: EPS vector map plus reference boundary data produces registered street boundaries](docs/images/luohu-example.png)

This case used about 13.76 km of verified shared boundary. The sampled arc distance was 10.90 m median and 23.63 m P90; about 73.34% of the source outline samples did not participate in fitting, and the reference does not validate internal street boundaries. These values are not general acceptance thresholds.

See the [case notes](docs/cases.md) and [experiment record](docs/experiments.md) for calculation details. Original EPS and reference GPKG files are not included; reproducing these examples requires authorized copies of the matching source data.

### Registration limits and review

- One global transform is applied to every extracted unit; the reference CRS is never assigned directly to page coordinates.
- Full extents use the outer outline. A local map uses only a verified shared boundary arc. A parent outline alone cannot locate an interior map.
- `overlay.png` helps reveal spatial mismatch. `qc.json` records scope decisions, extraction method, name coverage, sampled distances, and the unconstrained fraction.
- Boundary sampling metrics are approximations, not analytic Hausdorff distances or accuracy guarantees.
- Figures use Helvetica, 12 pt base text, and 1.5 pt default line width. The workflow illustration has no legend; panel headings identify each stage.

### Documentation

- [Skill workflow](SKILL.md)
- [Generic configuration](templates/config.example.yaml)
- [Input and naming contract](references/input-and-name-contract.md)
- [Methodology](references/methodology.md)
- [QC definitions](references/qc-spec.md)
- [Experiment and reproducibility notes](docs/experiments.md)
