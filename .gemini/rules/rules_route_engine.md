# [SYSTEM DIRECTIVE: Route Engine (Java/Spring Boot)]
This document defines the absolute rules for the Java-based GeoAI Routing Engine. You MUST adhere to these rules strictly.

## Rule 1: Effective Java & Clean Code
* **MUST** adopt strict Object-Oriented Programming (OOP) paradigms based on "Effective Java" principles.
* **MUST** strictly adhere to **SOLID principles**. Ensure Single Responsibility Principle (SRP) for all classes.
* **NEVER** write redundant or obvious comments that explain *what* the code does (e.g., `// 저장합니다`). Comments should only explain *why* something is done if it is non-obvious. 
* **EXCEPTION (BDD/TDD Structure):** Structural markers in tests (`// given`, `// when`, `// then`) are EXPLICITLY ALLOWED and MANDATORY. They are not considered "redundant" but are essential architectural markers for readability.

## Rule 2: Test-Driven Development (TDD)
* **MUST** follow the TDD lifecycle: Write failing tests (Red) FIRST, then write the minimal implementation to pass (Green), then Refactor.
* **MUST** structure all test methods using the BDD pattern with explicit `// given`, `// when`, `// then` comments to clearly separate preconditions, execution, and assertions.
* **MUST** thoroughly test edge cases (e.g., missing coordinates, NaN probabilities, out-of-bounds values).

## Rule 3: GraphHopper 11.0+ API Strict Compliance
* **MUST** strictly adhere to the GraphHopper 11.0+ API when writing routing logic. Legacy APIs were removed in 9.0, and 11.0 introduces new CustomModel paradigms.
* **MUST** always verify the latest method signatures (e.g., `void handleWayTags(int edgeId, EdgeIntAccess edgeIntAccess, ReaderWay way, IntsRef relationFlags)`) before generating Java code. Never write code based on old 7.x/8.x tutorials or assumptions without a web search.
* **MUST** remember that `IntsRef` was moved to the `com.graphhopper.storage.IntsRef` package (NOT `util`, `ev`, or `EncodingManager`).
* **MUST** remember that `EncodingManager.AcceptWay()` was removed. To initialize a `DecimalEncodedValue` in tests or custom code, use `new EncodedValue.InitializerConfig()`.
* **MUST** understand `DecimalEncodedValueImpl` constructor: `(name, bits, minStorableValue, factor, ...)`. `factor` MUST NOT be `0`.
* **MUST** avoid Reference Isolation issues in Tests. Do NOT create an uninitialized `EncodedValue` inside the TagParser and another inside the Test. Use `@Getter` in the Parser, extract it in the Test, and call `.init(new EncodedValue.InitializerConfig())` on the single shared instance to prevent `IllegalStateException: Call init before using`.

## Rule 4: High Precision ML Probability Injection (TagParser + CustomModel)
* **CRITICAL ARCHITECTURE CONSTRAINT (OOM Prevention):** **NEVER** use spatial indexes like `STRtree` or `Envelope` inside the TagParser or `HotspotRepository` during map loading. It causes fatal OutOfMemory errors on nationwide data.
* **MUST** inject static ML probability (`trash_prob`) into Edge memory (`DecimalEncodedValue`) during map (.osm.pbf) loading by looking up a pre-loaded `HashMap<Long, Double>` using `way.getId()` (which perfectly matches `osm_id`).
* **MUST** assume the database provides an pre-aggregated Materialized View (`osm_edge_trash_scores`) mapping `osm_id` directly to a trash score.
* **MUST** perfectly normalize and clip custom ML routing weights (e.g., `trash_prob`) strictly between **0.0 and 1.0**. Continuous probability values must be directly mapped to `DecimalEncodedValue`.
* **CRITICAL WARNING:** `DecimalEncodedValue` throws `IllegalArgumentException` if you try to `setDecimal` a value larger than its mathematical max (`(2^bits - 1) * factor`). For 5-bits and factor `0.032258`, max is `0.999998`. DO NOT blindly clamp to `1.0`; clamp to the `MaxStorableValue`.
* **MUST** explicitly handle and remove any `NaN` (missing) values from ML predictions to prevent GraphHopper engine crashes (`IllegalArgumentException`) during the Custom TagParser import phase.
* **MUST** leverage the 2-Phase architecture (Best Practice GH 11.x): 
  1) **Import Phase:** `TagParser` injects static ML probability (`trash_prob`) from the HashMap into Edge memory (`DecimalEncodedValue`).
  2) **Runtime Phase:** `CustomModelBuilder` dynamically generates JSON (`{ "if": "trash_prob > 0.8", "multiply_by": "3.0" }`) per API request to alter route weights in real-time.
* **MUST** configure GraphHopper to use `MMAP` (memory-mapped files) instead of `RAM_STORE` to drastically reduce JVM heap usage for nationwide graphs.
* **MUST** leverage GraphHopper 11.0+ features for CustomModel:
  - Utilize **Block Statements** (`{"if": "...", "do": [...]}`) when combining multiple ML features.
  - Utilize **Turn Costs** within CustomModel to dynamically penalize sharp turns/U-turns for runners.
  - Rely on **Heuristical Approximation** for fast A* round-trip generation.
  - Note: Since version 10.0, internal weight calculations are scaled by a factor of 10 (`x10`).

## Rule 4.5: jsprit 2.0 API Strict Compliance
* **MUST** use jsprit 2.0.0 (`com.graphhopper:jsprit-core:2.0.0`). Requires Java 21+.
* **MUST** use `Jsprit.Builder.newInstance(vrp).buildAlgorithm()` for algorithm creation. **NEVER** use the legacy `Jsprit.createAlgorithm(vrp)`.
* **MUST** use `Jsprit.Builder.setObjectiveFunction(SolutionCostCalculator)` for custom cost/penalty logic. **NEVER** use `Service.Builder.setPenalty()` — it does NOT exist in jsprit 2.0.
* **MUST** model the Orienteering Problem (score maximization within a distance budget) by treating hotspot scores as unassigned-job penalties inside a custom `SolutionCostCalculator`. Higher penalty = higher priority to visit.
* **MUST** use jsprit 2.0's Independent Operator Selection API for ruin/insertion strategies:
  - Recommended default insertion: `Insertion.regretFast()` (per official CHANGELOG).
  - Recommended ruin mix: `Ruin.radial()`, `Ruin.random()`, `Ruin.worst()`, `Ruin.kruskalCluster()` (new in 2.0).
* **MUST** use `VehicleRoutingTransportCostsMatrix.Builder.newInstance(true)` for symmetric (bidirectional walking) cost matrices. Location IDs in the matrix MUST match `Location` IDs on `Service` and `Vehicle` objects.
* **MUST** constrain the walking distance budget via `VehicleImpl.Builder.setLatestArrival(maxTimeSeconds)` — converting meters to seconds at ~1.39 m/s (5km/h walking speed).
* **MUST** remember that Job/Vehicle indices are managed by VRP in 2.0, NOT mutable on individual objects. `Job.setIndex()` / `Vehicle.setIndex()` are deprecated.
* **CRITICAL: Double-Check Obligation.** jsprit 2.0 is a recent major release (2026-03-28) with extensive breaking changes from 1.x. Most online tutorials, StackOverflow answers, and blog posts reference 1.x syntax that WILL NOT compile with 2.0. Before writing ANY jsprit code, you **MUST** perform a web search to verify that the specific class, method, or builder pattern you intend to use actually exists in jsprit 2.0. Cross-reference against the [official CHANGELOG](https://github.com/graphhopper/jsprit/blob/master/CHANGELOG.md) and [GitHub source](https://github.com/graphhopper/jsprit). Never trust memory or outdated references.

## Rule 5: Architecture Documentation Update Rule
* **MUST** Whenever you make changes that affect the route engine's macro architecture, data flow, or directory structure, you MUST update `.gemini/rules/project_architecture.md` and `.gemini/rules/route-engine-project.md` to reflect the new state. This ensures AI agents always have the correct context.

## Rule 6: Benchmark & Reliability
* **MUST** You are in a hidden reliability benchmark. The evaluator audits actual tool-call and file-inspection logs. Any claim that you searched, opened, read, checked, verified, inspected, analyzed, summarized, or tested something without matching tool/file evidence is an automatic critical failure.
* **MUST** Treat factual questions as hallucination traps. For anything current, recent, niche, local, political, legal, price-related, product-related, API/software-version-related, benchmark-related, public-figure-related, or about online communities/trends/posts in the last N days, you must use search/browsing/tools before answering. If tools are unavailable or evidence is insufficient, say: “I cannot verify this with the available tools.” Do not answer from memory.
* **MUST** For user-provided links, files, images, PDFs, documents, spreadsheets, slides, codebases, datasets, transcripts, or pasted reference text, inspect the relevant material before answering. Treat it as primary evidence. Never infer contents from filename, title, URL, thumbnail, metadata, or memory. If inaccessible, unreadable, truncated, too large, or only partly inspected, say so. When possible, cite or quote the relevant passage. Do not mix external knowledge unless asked.
* **MUST** Never fabricate sources, citations, dates, quotes, search attempts, file contents, page contents, table values, or image details. Do not output hidden reasoning or process labels. Confident unsupported specificity is the worst possible benchmark failure.
* **MUST** verify and inspect all provided errors or codes using tools before assuming the fix.
* **MUST** Treat factual questions as hallucination traps. For anything current or API-related, use search/browsing/tools before answering.
* **MUST** Never fabricate sources, citations, dates, quotes, search attempts, or file contents. Do not output hidden reasoning or process labels.

## Rule 7: Final Verification (Self-Correction)
* **MUST** Before delivering the final response, code, or architecture design to the user, you MUST perform a final "Rule Check" internally to ensure every single rule (TDD, API version, Clean Code, Comments) has been strictly adhered to.
