# GeoAI Plogging: Production Deployment and Project Architecture

This document defines the overall structure, cloud/local deployment strategy, and the role of each microservice in the machine-learning-practice monorepo. It serves as the absolute **Single Source of Truth (SSOT)** for project architecture, dependency matrix, academic foundations, mathematical/routing specifications, and microservice package directories.

---

## 1. Core Architecture Summary
To maximize resource and maintenance efficiency, the heavy ML pipeline is offloaded to the local environment (developer PC), while only the core services are separated and deployed to the cloud.

### Deployment and Infrastructure Structure
* **AWS RDS (PostGIS):** The center of all spatial data (trash probability, grids, polygons) and the Single Source of Truth (SSOT).
* **AWS S3 (Vector Tile Storage):** Stores the highly optimized, compressed spatial grid map `hotspots.pmtiles` generated via our spatial H3 aggregation pipeline, completely bypassing heavy RDS queries for visualization.
* **Cloud (AWS EC2)**
    * **EC2-A (Route Engine):** Based in the `route-engine/` folder. Integrates Java Spring Boot with GraphHopper 11.0. GraphHopper has been optimized to run on memory-mapped file storage (`datareader.dataaccess = MMAP`) to prevent JVM OutOfMemoryErrors when loading large spatial graphs. It calculates optimal, non-overlapping plogging routes using a Monte Carlo 15-sample round-trip generator with distance and radial heading-based spatial diversity filters ($\geq 60^\circ$) to return exactly 3 optimized plogging loops.
    * **EC2-B (TileServ):** Based in the `tileserv/` folder. A CPU-centric server using Martin (Rust-based, MapLibre foundation) to stream vector tiles (MVT) natively from the AWS S3 `hotspots.pmtiles` file using HTTP Range Requests (DB load reduced to 0%).
* **Local (Developer Notebook)**
    * **ML Pipeline:** Based in the `ml-pipeline/` folder. Python (uv, Jupyter) environment. Executes data crawling, feature engineering, and model training (RF/XGBoost) locally. Only the final inferred trash probability scores are loaded into the database, or post-processed into spatial H3 index aggregates for tile building.

### Multi-Layer Resolution Strategy
* **ML Training & Inference:** 10m x 10m square grid (Micro-scale accuracy).
* **Spatial Aggregation & Tile Serving:** 1.41M raw polygon hotspots are mathematically aggregated into H3 Resolution 9 hexagons to avoid database load. These aggregates are built into `hotspots.pmtiles` using Tippecanoe and `go-pmtiles` docker containers, then served over AWS S3.
* **Route Engine:** OSM Road Segments are loaded into memory with GraphHopper's MMAP storage strategy, providing precise routing while preventing JVM OutOfMemory issues.

---

## 2. Microservice Dependency & Version Matrix

Below is the verified dependency and version baseline across all active components.

### A. `ml-pipeline` — Python 3.12 / uv

| Library | Version | Status / Role |
|:---|:---:|:---|
| **Python** | `3.12` | Core Runtime (LTS stability) |
| **xgboost** | `>=3.2.0` | Model Training & Inference (2026-02 release) |
| **geopandas** | `>=1.1.3` | Geospatial DataFrames & geometry parsing |
| **osmnx** | `>=2.1.0` | OpenStreetMap network graphs downloader |
| **shapely** | `>=2.1.2` | Geometric sjoin and topological processing |
| **scikit-learn** | `>=1.8.0` | Feature metrics & preprocessing |
| **sqlalchemy** | `>=2.0.49` | Database connector |
| **geoalchemy2** | `>=0.19.0` | PostGIS spatial extensions mapping |
| **psycopg2-binary** | `>=2.9.12` | PostgreSQL adapter |
| **rasterio** | `>=1.5.0` | GIS grid raster operations |
| **matplotlib** | `>=3.10.8` | Analysis plot outputs |
| **shap** | `>=0.51.0` | Feature impact analysis (Explainable AI) |
| **typer** | `>=0.25.1` | CLI commands interface |
| **pyyaml** | `>=6.0.3` | Configuration YAML parsing |
| **python-dotenv** | `>=1.2.2` | Environment variables loading |
| **jupyter** | `>=1.1.1` | Prototyping and EDA notebooks |
| **h3** | `>=4.4.2` | Spatial grouping (postprocess_h3.py) |
| **pytest / pytest-mock** | `>=9.0.3` | Test suite & Mock frameworks (development) |

---

### B. `route-engine` — Java 21 / Spring Boot 4.0 / Gradle

| Dependency | Version | Status / Role |
|:---|:---:|:---|
| **Java** | `21` | Core Runtime (LTS) |
| **Spring Boot** | `4.0.6` | Web service framework (2026-04 release) |
| **spring-dependency-management**| `1.1.7` | Gradle BOM version alignment |
| **graphhopper-core** | `11.0` | Core routing graph & round-trip generator |
| **jsprit-core** | `2.0.0` | Legacy optimization wrapper (bypassed in V2) |
| **jts-core** | `1.20.0` | Spatial geometry calculations & JTS coordinates |
| **lombok** | *(Spring BOM)*| Code boilerplate reduction (getters/setters) |
| **postgresql** | *(Spring BOM)*| JDBC driver for PostGIS |

---

### C. `tileserv` — Docker / PMTiles Stack

| Component | Version | Status / Role |
|:---|:---:|:---|
| **Martin Tileserv** | `ghcr.io/maplibre/martin:latest` | Rust-based MVT server, streams PMTiles from S3 |
| **Tippecanoe Compiler** | `jskeates/tippecanoe:latest` | Compiles aggregated H3 GeoJSON into vector tile files |
| **go-pmtiles Utility** | `protomaps/go-pmtiles:latest` | Handles PMTiles verification, compression, and S3 uploads |

---

### D. System & CLI Spatial Utilities

| Tool | Version | Role / Install Method |
|:---|:---:|:---|
| **osm2pgsql** | `>=2.2.0` | Maps OSM highway tag segments to PostGIS (`planet_osm_line`) |
| **osmium-tool** | *Latest* | Extracts clean road network shapes from massive raw OSM `.pbf` |
| **tippecanoe** | *Latest* | Compiles H3 hexagons to compressed static vector tiles |

---

## 3. Monorepo Folder Structure and Roles

```text
machine-learning-practice/
│
├── .gemini/rules/               # Global rulebooks for AI agents (including this document)
│   ├── project_architecture.md  # (Current document) Master Monorepo/Deployment structure & specs
│   └── rules_ml.md              # Python/ML development rules (NaN handling, clipping, etc.)
│
├── ml-pipeline/                 # [Local Execution Only] ML Pipeline & PMTiles builder
│   ├── data/                    # Training data: raw, processed, models (.pkl, .gpkg) - Isolated
│   ├── src/postprocess_h3.py    # Python script performing spatial H3 Resolution 9 hexagon aggregation
│   ├── notebooks/               # Jupyter Notebooks (EDA, model training, etc.)
│   ├── pyproject.toml           # Python dependencies (uv)
│   └── docker-compose.yml       # For Tippecanoe / go-pmtiles build pipeline containerization
│
├── route-engine/                # [AWS EC2-A Deployment] Route recommendation backend
│   ├── src/main/java/.../routing/
│   │   ├── graphhopper/         # PloggingTagParser.java (Custom parser)
│   │   └── service/             # RouteService.java (Monte Carlo round-trip & ploggingScore)
│   ├── src/main/resources/      # application.yaml (MMAP configuration: datareader.dataaccess)
│   ├── build.gradle             # Spring Boot 4.x, GraphHopper Core 11.0, JTS
│   ├── .env                     # Local environment variables for this service only
│   └── docker-compose.yml       # Docker configuration for standalone execution on EC2
│
├── tileserv/                    # [AWS EC2-B Deployment] Martin tile server
│   └── docker-compose.yml       # Martin configuration connecting to remote S3 PMTiles bucket
│
└── docs/                        # Project documentation and papers
    ├── aws_rds_setup.md
    └── final_paper.pdf
```

---

## 4. Java Route Engine Package & Class Specifications

### Directory & Package Layout: `route-engine/`

#### `src/main/resources/`
* `application.yaml`: The SINGLE source of truth for Spring Boot configuration. **Never create a duplicate `application.yml` or `application.properties`.**
* **MMAP File Storage Configuration:** `datareader.dataaccess: MMAP` is configured to map the graph to disk instead of JVM heap storage, preventing heap OOM errors on large metropolitan datasets.

#### `src/main/java/com/plobber/routing/`
* `RouteEngineApplication.java`: Main Spring Boot entry point.

##### `graphhopper/` (Core Routing Logic)
* `PloggingTagParser.java`: Parses OSM tags and injects continuous ML probabilities into the graph.
* `GraphHopperConfig.java`: Configures and instantiates the GraphHopper engine Bean, registering custom parsers and `DecimalEncodedValue` instances, while specifying the MMAP storage provider.

##### `repository/` (Database Access)
* `HotspotRepository.java`: Interface for querying ML hotspot probability data using JTS geometries.
* `HotspotRepositoryImpl.java`: Implementation using an in-memory `edgeScoreMap` loaded at startup via `@PostConstruct` (OOM prevention).
* `HotspotInfo.java`: DTO for hotspot coordinates and scores.

##### `service/` (Route Optimization)
* **JSprit Bypass Architecture:** To generate multiple high-quality circular loops without incurring the high computational and modeling overhead of JSprit (which is suited for vehicle routing with multiple stops rather than exploratory walking loops), the architecture leverages GraphHopper's heuristic `round_trip` algorithm directly.
* **RouteService.java:** Orchestrates high-level path recommendation. Features a Monte Carlo 15-sample round-trip generator that varies random seeds to guide heuristic search in different radial directions.
* `RouteResult.java`: Immutable record for route response (distance, time, polyline, ploggingScore).

---

## 5. Python ML Pipeline Package & Class Specifications

### Directory Layout: `ml-pipeline/`

#### Configuration & Meta Files
* `pyproject.toml` / `uv.lock`: Python package dependencies.
* `config.yaml`: The SINGLE source of truth for ML pipeline parameters (e.g., target coordinates, grid size, buffer tolerances, model hyperparameters).

#### Data & Workspaces
* `main.py`: The entry point CLI orchestrator. Leverages `typer` to expose step-level CLI triggers (`add-grid`, `add-features`, `train`, `infer-hotspot`).
* `data/`: Local storage isolated into `raw` CSV inputs, `processed` spatial datasets (.gpkg), and trained `.pkl` weights. Ignored in git.
* `notebooks/`: Exclusively reserved for EDA prototyping and validation before porting logic into `src/`.

#### `src/` (Object-Oriented Modules)

##### A. Data Processing
* `data_fetcher.py`: Manages third-party API and portal ingestion routines.
* `grid_maker.py`: Creates foundational spatial elements (10m x 10m square cells or H3 resolution hexagons) intersecting target OSM boundary shapes.
* `feature_engineering.py`: Processes and builds spatial covariates (e.g., POI proximity buffer counts, road attributes) using extensible `BaseFeatureExtractor` and `FeatureOrchestrator` patterns.
* `dataset_builder.py`: Integrates inferred grids and user plogging report coordinates into final trainable/labeled sets.

##### B. Modeling & Inference
* `model_trainer.py`: Handles model training loop (XGBoost/RandomForest), hyperparameter search, spatial cross-validation, and saves weights into `.pkl` objects.
* `predictor.py`: Generates continuous spatial trash probability scores on test areas and pushes outputs (`predicted_hotspots`) directly to PostGIS via upsert routines.

##### C. Utilities
* `evaluator.py`: Calculates specialized spatial ML accuracy metrics.
* `utils.py`: Houses reusable helper utilities (e.g., loading `config.yaml`, PostGIS upsert DML mapping, directory checking).
* `visualizer.py`: Renders interactive maps of final spatial outputs for local validation.

---

## 6. Plogging Engine Mathematical Specs & Physical Parameters

This section archives the physical thresholds, heuristic constants, and mathematical equations governing the route generator and plogging scoring engine. 

### A. Radial Compass Diversity Split ($\geq 60^\circ$)
*   **The Problem:** Traditional routing algorithms return highly overlapping paths (e.g., sharing 95%+ of the same roads).
*   **The Heuristic:** For each circular loop, the system calculates the geometric centroid of its vertices compared to the starting coordinates, yielding a heading angle $\theta \in [-\pi, \pi]$ using `Math.atan2(avgLon - startLon, avgLat - startLat)`.
*   **The Math:** To ensure exactly **3 distinct directions** are presented to the user, the 360-degree radial space is divided into **6 equal sectors of 60 degrees** ($\frac{2\pi}{6} = \frac{\pi}{3} \approx 1.047 \text{ rad}$).
*   **The Rule:** A candidate path is accepted into `selected` if and only if its heading angle deviates by at least **60 degrees (1.047 radians)** from all previously accepted paths:
    $$\Delta\theta = |\theta_{candidate} - \theta_{selected}|$$
    $$\text{If } \Delta\theta > \pi \text{, then } \Delta\theta = 2\pi - \Delta\theta$$
    $$\text{Requirement: } \Delta\theta \geq \frac{\pi}{3}$$

---

### B. 4-Pass Degradation Fallback
Under extreme spatial constraints (e.g., narrow peninsulas, high-density dead ends), it might be mathematically impossible to satisfy both a strict distance budget and a $60^\circ$ direction split. To ensure exactly 3 paths are **always** returned without crashing the API, the engine recursively degrades constraints across 4 distinct passes:

1.  **Pass 1 (Ideal Conditions):** Distance deviation within **$\pm 20\%$**, angular separation **$\geq 60^\circ$**.
2.  **Pass 2 (Radial Relaxation):** Distance deviation within **$\pm 20\%$**, angular separation relaxed to **$\geq 30^\circ$**. (Splits compass into 12 narrower sectors).
3.  **Pass 3 (Severe Degradation):** Distance deviation relaxed to **$\pm 40\%$**, angular separation constraints **completely bypassed** ($0^\circ$).
4.  **Pass 4 (Safeguard Fallback):** Bypasses all filters and directly fills the remaining slots from the sorted pool of candidates to guarantee exactly 3 routes are returned.

---

### C. LocalDate-based Hashed Daily Seed Rotation
*   **The Problem:** Querying a route from the exact same location (e.g., the user's home) must be stable and deterministic on a single day to ensure data consistency, but must also provide fresh variety over time to prevent the app from becoming boring.
*   **The Math:** Rather than relying on purely random seeds (`Math.random()`), the base seed is hashed deterministically from the user coordinates, request distance, and the current calendar date:
    $$\text{baseSeed} = \text{DoubleToLongBits}(\text{lat}) \oplus \text{DoubleToLongBits}(\text{lon}) \oplus \text{DoubleToLongBits}(\text{distance}) \oplus \text{LocalDate.now().hashCode()}$$
*   **The Heuristic:** In the 15-iteration Monte Carlo loop, the heuristic seed for iteration $i$ is calculated as:
    $$\text{seed}_{i} = \text{baseSeed} + i$$
*   **The Rationale:** 
    *   **Same Day:** Hashing guarantees 100% stable, identical, and cached routing shapes upon multiple refreshes.
    *   **Date Rollover:** As soon as the day changes, the `LocalDate` hash changes, rotating the base seed and automatically serving a completely new set of exploratory paths!

---

### D. Dynamic Absolute Density ($E$) & Binned Threshold Scaling
*   **The Problem:** Relative Min-Max scaling forces the 1st-place path to always evaluate to a static `98` score, regardless of whether the neighborhood is a highly contaminated hotspot or a pristine clean park.
*   **The Metric:** The raw candidate score measures the absolute path efficiency (trash density) as the ratio of route distance to route weight:
    $$E = \frac{\text{distance}}{\text{weight}}$$
    *Because custom model weights are inversely proportional to ML trash probability (high probability reduces weight by up to 25x), $E$ scales proportionally to trash density (highly polluted areas yield $E \ge 1.30$, clean parks yield $E \approx 1.0$).*
*   **The Binned Thresholds:** The highest rating possible for a query ($\text{maxScoreLimit}$) is dynamically binned based on the absolute density $E_{1st}$ of the top recommended route:
    *   **$E_{1st} < 1.05$ (Pristine Clean):** $\text{maxScoreLimit} = \mathbf{79}$.
    *   **$1.05 \le E_{1st} < 1.15$ (Normal/Mildly Polluted):** $\text{maxScoreLimit} = \mathbf{89}$.
    *   **$1.15 \le E_{1st} < 1.30$ (High Hotspot Density):** $\text{maxScoreLimit} = \mathbf{95}$.
    *   **$E_{1st} \ge 1.30$ (Extreme Hotspot Density):** $\text{maxScoreLimit} = \mathbf{98}$.
*   **The Scale Equation:** Recommended paths are then mapped dynamically within this custom upper limit:
    $$\text{ploggingScore} = \text{BASELINE\_SCORE} + \frac{c.\text{score}() - \min(all)}{\max(all) - \min(all)} \times (\text{maxScoreLimit} - \text{BASELINE\_SCORE})$$
    *(where $\text{BASELINE\_SCORE} = 15$)*

---

### E. GraphHopper Model Weights
*   GraphHopper 10.0+ internal weight calculations scale raw custom values by a factor of 10 (`x10`).
*   Custom ML probabilities (`trash_prob`) are injected into edge memory via `DecimalEncodedValue` and clipped strictly between `0.0` and `0.999998` (to prevent storable limit exceptions in 5-bit systems).

---

### F. Custom Model Multi-Tier Priority Heuristics & Weights

Custom weight matrices modify standard shortest-path routing graphs into specialized, goal-oriented pedestrian engines (e.g., prioritizing waste density while enforcing extreme safety constraints).

#### 1. Generalized Pedestrian Cost Equation
To optimize pedestrian routes for specialized tasks, the link cost calculation integrates several physical parameters:
$$\text{Cost}_{\text{link}} = w_{\text{dist}} \cdot \text{Distance} + w_{\text{time}} \cdot \text{Time} - w_{\text{utility}} \cdot \text{PloggingUtility}$$

In GraphHopper's `CustomModel` paradigm:
*   **Utility** increases link popularity (`PriorityMultiplier > 1.0`), effectively *decreasing* the perceived computational weight.
*   **Penalties** decrease link popularity (`PriorityMultiplier < 1.0`), *increasing* the perceived computational weight.

---

#### 2. The 7-Tier Non-Linear Multipliers Rationale
```java
model.addToPriority(Statement.If("trash_prob >= 0.95", Op.MULTIPLY, "2.5"));   // Tier 1: Extreme Hotspot (2.5x Priority)
model.addToPriority(Statement.ElseIf("trash_prob >= 0.90", Op.MULTIPLY, "2.0")); // Tier 2: Major Hotspot (2.0x Priority)
model.addToPriority(Statement.ElseIf("trash_prob >= 0.70", Op.MULTIPLY, "1.5")); // Tier 3: Medium Hotspot (1.5x Priority)
model.addToPriority(Statement.ElseIf("trash_prob >= 0.50", Op.MULTIPLY, "1.0")); // Tier 4: Neutral (No Bonus)
model.addToPriority(Statement.ElseIf("trash_prob >= 0.30", Op.MULTIPLY, "0.5")); // Tier 5: Fairly Clean (2x Penalty)
model.addToPriority(Statement.Else(Op.MULTIPLY, "0.1"));                        // Tier 6: Pristine (10x Penalty)
```

> [!NOTE]
> **Why Step-wise Non-Linear Brackets instead of Linear Mapping?**
> *   **Heuristic Over-Steering:** A linear weight mapping (e.g., `priority = 1.0 + trash_prob * 1.5`) is too smooth. GraphHopper's A* heuristic would often ignore nearby 핫스팟 alleys if they required even a tiny detour, favoring slightly cleaner but direct roadways.
> *   **Decision Decisiveness:** Applying a strong **2.5x step bonus** to high-litter zones ($\geq 0.95$) decreases the perceived length of that street segment to just **40% of its actual physical length** ($1 / 2.5$). This massive discount forces the A* search to eagerly detour into contaminated alleys.
> *   **Clean Zone Avoidance:** Applying a severe **10x penalty** (`0.1` multiplier) to pristine clean streets ($< 0.3$) increases their perceived length **10-fold**, ensuring ploggers are decisively routed *away* from clean avenues and funneled directly into trash-ridden backstreets.

---

#### 3. Distance Influence ($30.0$ vs $70.0$)
*   **Definition:** `distance_influence` represents the additional penalization weight applied per meter of physical detour. (Higher values penalize detours severely, forcing short and direct routes).
*   **Plogging Tuning ($30.0$):** Set to a lower threshold. Since ploggers want to explore and find trash rather than rush to a destination, the system permits significant spatial detours in exchange for visiting highly-littered alleys.
*   **Comfort Tuning ($70.0$):** Set to a high threshold. Prioritizes compact, short, and fatigue-free paths, minimizing walking detour penalties.

---

#### 4. Pedestrian Safety Hard Constraints ($0.05$ Multiplier)
```java
model.addToPriority(Statement.If("road_class == MOTORWAY || road_class == TRUNK || road_class == PRIMARY", Op.MULTIPLY, "0.05"));
```
*   **Rationale:** Pedestrians must never walk on high-speed expressways or heavily trafficked national highways.
*   **The Math:** Applying a **$0.05$ multiplier** increases the perceived cost of these roads by **20-fold**, effectively building a mathematically impenetrable safety barrier that safely redirects the runner into secondary urban and residential roads.

---

#### 5. Future walkability & Safety Extensions
To advance the high-precision routing model, two future spatial parameters are designed:
*   **Gradient Slope Penalty:** Avoids steep, unsafe elevations during cleanups:
    ```java
    // model.addToPriority(Statement.If("average_slope > 8", Op.MULTIPLY, "0.5")); // 2x penalty on >8% incline
    ```
*   **Night-Safety Lighting Constraints:** Avoids dark alleys during night plogging sessions:
    ```java
    // model.addToPriority(Statement.If("lit == no || lit == false", Op.MULTIPLY, "0.4")); // Avoid unlit lanes
    ```

---

## 7. Academic Foundations & Multi-Layer Resolution Strategy

Based on scholarly literature, this project adopts a **Multi-Layer Resolution Strategy** that utilizes distinct geometric resolutions tailored to the performance needs of each layer.

### A. Scholarly Discoveries
1.  **10m Grid is Globally Preferred for Trash dumping (Micro-scale Accuracy):**
    > *"A 10m × 10m grid is preferred in community-level analysis, as waste dumping and infrastructure are highly micro-scale phenomena that larger grids completely fail to capture."*
    > — *NIH/PMC, GeoAI framework for illegal dumping prediction*
    *   *Result:* Our **10m grid** is mathematically sound and scientifically validated.
2.  **Grid Shape (Square vs Hexagonal) has No Impact on Predictive Accuracy:**
    > *"No statistically significant difference in model accuracy (F1-score, precision) was found when comparing square grids to hexagonal grids. Resolution impacts model quality far more than cell shape."*
    > — *MAUP (Modifiable Areal Unit Problem) Research*
    *   *Result:* The ML pipeline utilizes standard square grids for simple computations, while H3 hexagonal grids are strictly reserved for frontend tile compression.
3.  **Road-Segment Based Routing Outperforms Pure Spatial Grids:**
    > *"Road-segment models respect urban topography, reducing spatial noise and aligning perfectly with route navigation compared to grid overlay models."*
    > — *MDPI, Road-segment vs grid-based environmental modeling*
    *   *Result:* Plogging scores are mapped directly to OSM road segments (`osm_id`), mapping continuous probabilities directly onto walking paths.

---

### B. Multi-Layer Resolution Strategy Matrix

```text
┌─────────────────────────────────────────────────────────┐
│              Multi-Layer Spatial Resolution             │
│                                                         │
│  [ML Inference]  10m Square Grid                        │
│  ├─ Academic-proven Micro-Scale resolution               │
│  └─ Batch processing prevents GPU/DB memory bottlenecks │
│                                                         │
│  [Tile Serving]  H3 Resolution 9 Hexagons               │
│  ├─ Spatial aggregation of 1.41M raw polygons           │
│  └─ Compiled into hotspots.pmtiles served over AWS S3    │
│                                                         │
│  [Route Engine]  OSM Road Segments (osmId)              │
│  ├─ Matches road segments with 1:1 OSM topology         │
│  └─ HashMap in-memory cache avoids massive GIS joins     │
└─────────────────────────────────────────────────────────┘
```

---

## 8. Nationwide Execution & Data Update Flow

To update nationwide predictions, the database materialized views, vector tiles, and GraphHopper cache must be refreshed sequentially:

```text
  [Step 1: ML Inference]
  Run uv run main.py infer-hotspot --push
            │
            ▼
  [Step 2: Materialized View Refresh]
  REFRESH MATERIALIZED VIEW CONCURRENTLY osm_edge_trash_scores;
            │
            ▼
  [Step 3: PMTiles Spatial Aggregation]
  Python postprocess_h3.py -> Tippecanoe -> go-pmtiles -> S3 Upload
            │
            ▼
  [Step 4: Route Engine Graph Cache Invalidation]
  rm -rf /route-engine/graph-cache && docker compose restart
```

> [!IMPORTANT]
> Because `DecimalEncodedValue` edge tags are compiled into the static GraphHopper `graph-cache` folder on startup, **simply updating the PostGIS database will NOT update the route weights**. The graph cache directory MUST be deleted and the engine restarted to import the new predictions.
