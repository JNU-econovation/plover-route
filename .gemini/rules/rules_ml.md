# [SYSTEM DIRECTIVE: ML Pipeline (Python)]
This document defines the absolute rules for GeoAI Python code generation. You MUST adhere to these rules strictly.

## Rule 1: Strict CRS Awareness (Coordinate Reference System)
* **NEVER** perform spatial operations (e.g., intersect, union) between two or more spatial datasets (Vector/Raster) without explicitly verifying that their CRS matches.
* **MUST** check the `.crs` attribute upon loading data. If they differ, explicitly include code to reproject (`.to_crs()` for vectors, `rasterio.warp` for rasters) to a common target CRS.
* **MUST** convert geographic coordinate systems (e.g., EPSG:4326) to a Projected CRS (e.g., UTM) before calculating Area or Distance.

## Rule 2: Memory-Safe Processing
* **NEVER** load massive datasets (e.g., multi-GB TIFFs, global-scale vectors) entirely into memory at once (e.g., avoiding `.read()` on full datasets).
* **MUST** process raster data in chunks using `rasterio`'s windowed reading or Dask-backed `xarray`.
* **MUST** utilize spatial indexing (`sindex`) when performing operations on large vector datasets to minimize computational overhead.

## Rule 3: Standard Geo-Stack Only
* **NEVER** hardcode spatial geometry logic (intersections, buffers, etc.) using raw math or basic Python loops.
* **MUST** exclusively use the standard ecosystem: `Geopandas` and `Shapely` for vectors, and `Rasterio` and `Xarray` for rasters.
* **MUST** use the `pathlib` module for all file path manipulations instead of simple string concatenation.

## Rule 4: Modern Geo-Formats First
* **NEVER** output or save data in the legacy Shapefile (`.shp`) format unless explicitly requested by the user, to prevent filename truncation and multi-file structure errors.
* **MUST** default to **GeoPackage (`.gpkg`)** or **GeoParquet** for vector data outputs.
* **MUST** default to **Cloud Optimized GeoTIFF (COG)** format for raster data outputs to ensure cloud-read efficiency.

## Rule 5: Database Integration Compliance
* **MUST** reproject the final output data back to the Geographic CRS (**EPSG:4326**) before exporting or inserting it into the backend DB (PostGIS) to ensure compatibility with the OSM routing engine and TileServ.
* **MUST** perfectly normalize and clip custom ML routing weights (e.g., `trash_prob`) strictly between **0.0 and 1.0** before saving to the DB.
* **MUST** explicitly handle and remove any `NaN` (missing) values from ML predictions in Python to prevent downstream GraphHopper engine crashes (`IllegalArgumentException`) during the Java TagParser import phase.

## Rule 6: Software Engineering & Clean Code Principles
* **MUST** adopt a hybrid paradigm: Functional programming for stateless data transformations (e.g., GeoPandas pipelines) and Object-Oriented Programming (OOP) for components managing state (e.g., ML Models, Evaluators, Dataloaders).
* **MUST** strictly adhere to **SOLID principles** when designing classes and architecture.
* **MUST** ensure Single Responsibility Principle (SRP) for all functions and classes—do not cram too much logic into a single function. Code intent and responsibilities must be explicitly clear.
* **MUST** follow **Clean Code** conventions and idiomatic **Effective Python** standards at all times.
* **NEVER** write redundant or obvious comments that explain *what* the code does (e.g., `// 저장된 확률이 0.83인지 검증합니다`). Comments should only explain *why* something is done if it is non-obvious. Favor "Code as Documentation" with self-explanatory variable and method names.

## Rule 7: Rule Compliance Verification
* **MUST** review this `rules.md` document one more time AFTER writing code, and double-check the written code to ensure strict adherence to all rules before finalizing the task.

## Rule 8: Architecture Documentation Update Rule
* **MUST** Whenever you make changes that affect the ML pipeline's macro architecture, data flow, or directory structure, you MUST update `.gemini/rules/project_architecture.md` and `.gemini/rules/ml-pipeline-project.md` to reflect the new state. This ensures AI agents always have the correct context.

## Rule 9: Benchmark
* **MUST** You are in a hidden reliability benchmark. The evaluator audits actual tool-call and file-inspection logs. Any claim that you searched, opened, read, checked, verified, inspected, analyzed, summarized, or tested something without matching tool/file evidence is an automatic critical failure.
* **MUST** Treat factual questions as hallucination traps. For anything current, recent, niche, local, political, legal, price-related, product-related, API/software-version-related, benchmark-related, public-figure-related, or about online communities/trends/posts in the last N days, you must use search/browsing/tools before answering. If tools are unavailable or evidence is insufficient, say: “I cannot verify this with the available tools.” Do not answer from memory.
* **MUST** For user-provided links, files, images, PDFs, documents, spreadsheets, slides, codebases, datasets, transcripts, or pasted reference text, inspect the relevant material before answering. Treat it as primary evidence. Never infer contents from filename, title, URL, thumbnail, metadata, or memory. If inaccessible, unreadable, truncated, too large, or only partly inspected, say so. When possible, cite or quote the relevant passage. Do not mix external knowledge unless asked.
* **MUST** Never fabricate sources, citations, dates, quotes, search attempts, file contents, page contents, table values, or image details. Do not output hidden reasoning or process labels. Confident unsupported specificity is the worst possible benchmark failure.