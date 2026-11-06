# Graph Report - ByaHero  (2026-11-03)

## Corpus Check
- 54 files · ~207,368 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 17 file(s) not represented in the graph (top: (none) 6, .csv 4, .css 4)

## Summary
- 493 nodes · 848 edges · 27 communities (20 shown, 7 thin omitted)
- Extraction: 96% EXTRACTED · 4% INFERRED · 0% AMBIGUOUS · INFERRED: 38 edges (avg confidence: 0.86)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- API Routes & Route Config
- Test Suite & Dependencies
- Data Manager (CSV/DB)
- Weather & Commute Reasoner
- Byahero App Core & API
- Input Validators & Time Utils
- Arrival Predictor v2 (ML)
- Konduktor Chat UI (JS)
- Location & Arrival APIs
- Main Prediction UI (JS)
- Konduktor LLM Integration
- Custom Select UI Component
- Public Static Script (JS)
- Flask App & LLM Imports
- Trip Planner & Routes
- PWA Manifest
- Konduktor System Prompt & LLM
- Arrival Predictor v1 (ML)
- Trip Planning Handlers
- Service Worker (PWA)
- CSV Export APIs
- Vercel Config
- PWA Offline Queue
- Route Management API
- App Tests

## God Nodes (most connected - your core abstractions)
1. `DataManager` - 26 edges
2. `ArrivalPredictor` - 15 edges
3. `get_db_connection()` - 15 edges
4. `InputValidator` - 13 edges
5. `Byahero` - 12 edges
6. `predict()` - 10 edges
7. `trip_plan_api()` - 10 edges
8. `get_all_routes()` - 10 edges
9. `get_weather()` - 10 edges
10. `refresh_arrival_predictor()` - 9 edges

## Surprising Connections (you probably didn't know these)
- `refresh_arrival_predictor()` --uses--> `ArrivalPredictor`  [INFERRED]
  app.py → models/arrival_predictor_v2.py
- `manage_locations()` --calls--> `get_known_model_routes()`  [INFERRED]
  app.py → data/routes_config.py
- `manage_locations()` --calls--> `get_known_model_stops()`  [INFERRED]
  app.py → data/routes_config.py
- `add_route_api()` --calls--> `add_route()`  [INFERRED]
  app.py → data/routes_config.py
- `add_route_api()` --calls--> `get_known_model_routes()`  [INFERRED]
  app.py → data/routes_config.py

## Import Cycles
- None detected.

## Communities (27 total, 7 thin omitted)

### Community 0 - "API Routes & Route Config"
Cohesion: 0.06
Nodes (25): _as_int(), get_location_by_id(), get_location_id_by_name(), predict(), trip_plan_api(), add_route(), _deserialize_model_stops(), _deserialize_stops() (+17 more)

### Community 1 - "Test Suite & Dependencies"
Cohesion: 0.07
Nodes (10): run_tests(), check(), main(), restore_data(), snapshot_data(), to_min(), get_db_connection(), get_live_bus_locations() (+2 more)

### Community 3 - "Weather & Commute Reasoner"
Cohesion: 0.10
Nodes (12): weather_api(), CommuteReasoner, get_reasoner(), get_weather(), _cache_key(), get_weather(), get_weather_factor(), get_weather_for_location() (+4 more)

### Community 4 - "Byahero App Core & API"
Cohesion: 0.10
Nodes (4): ApiError, Byahero, ByaHeroApi, main()

### Community 6 - "Arrival Predictor v2 (ML)"
Cohesion: 0.12
Nodes (3): ArrivalPredictor, _to_hhmm(), _to_minutes()

### Community 7 - "Konduktor Chat UI (JS)"
Cohesion: 0.17
Nodes (24): addBotMessage(), addUserMessage(), addWelcomeMessage(), bindEvents(), cacheElements(), checkLLMStatus(), closePanel(), createMessageElement() (+16 more)

### Community 8 - "Location & Arrival APIs"
Cohesion: 0.09
Nodes (11): add_location_api(), delete_location_api(), edit_location_api(), export_preview_api(), get_arrivals_api(), get_locations_api(), get_statistics_api(), get_timezone_api() (+3 more)

### Community 9 - "Main Prediction UI (JS)"
Cohesion: 0.18
Nodes (13): displayResults(), errorSection, escapeHtml(), generateInsights(), getWeatherIcon(), hidePanel(), loadHeaderWeather(), predictForm (+5 more)

### Community 10 - "Konduktor LLM Integration"
Cohesion: 0.13
Nodes (8): add_arrival_record_api(), _arrivals_stamp(), generate_konduktor_response(), handle_followup_question(), handle_next_bus_query(), handle_waiting_time_query(), predict_arrival_api(), refresh_arrival_predictor()

### Community 11 - "Custom Select UI Component"
Cohesion: 0.29
Nodes (15): currentHighlightedIndex(), enhanceSelects(), handleKeydown(), hiddenSetSelected(), highlightItem(), onValueChange(), renderOptions(), scrollToOption() (+7 more)

### Community 12 - "Public Static Script (JS)"
Cohesion: 0.22
Nodes (11): displayResults(), errorSection, escapeHtml(), generateInsights(), hidePanel(), predictForm, resetForm(), resultsSection (+3 more)

### Community 13 - "Flask App & LLM Imports"
Cohesion: 0.15
Nodes (3): internal_error(), _load_or_create_secret_key(), not_found()

### Community 14 - "Trip Planner & Routes"
Cohesion: 0.18
Nodes (7): add_arrival(), get_routes_api(), historical_data(), manage_locations(), trip_planner(), _wants_splash(), get_all_routes()

### Community 15 - "PWA Manifest"
Cohesion: 0.14
Nodes (13): background_color, categories, description, dir, display, icons, lang, name (+5 more)

### Community 16 - "Konduktor System Prompt & LLM"
Cohesion: 0.18
Nodes (5): get_konduktor_system_prompt(), is_llm_available(), konduktor_chat_api(), konduktor_status_api(), stream_llm_response()

### Community 18 - "Trip Planning Handlers"
Cohesion: 0.25
Nodes (4): generate_trip_recommendation(), get_stops_after_api(), handle_trip_planning(), _location_name_map()

### Community 19 - "Service Worker (PWA)"
Cohesion: 0.50
Nodes (7): CORE_ASSETS, getOfflineQueue(), handleOfflinePost(), notifyClients(), openQueueDB(), setOfflineQueue(), syncOfflineQueue()

### Community 20 - "CSV Export APIs"
Cohesion: 0.33
Nodes (3): _csv_response(), export_arrivals_csv(), export_locations_csv()

### Community 21 - "Vercel Config"
Cohesion: 0.33
Nodes (5): builds, env, PYTHONPATH, routes, version

### Community 22 - "PWA Offline Queue"
Cohesion: 0.60
Nodes (3): queueOfflineSubmission(), sendArrival(), showOfflineBanner()

## Knowledge Gaps
- **7 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `DataManager` connect `Data Manager (CSV/DB)` to `Test Suite & Dependencies`, `Arrival Predictor v2 (ML)`?**
  _High betweenness centrality (0.106) - this node is a cross-community bridge._
- **Are the 3 inferred relationships involving `ArrivalPredictor` (e.g. with `refresh_arrival_predictor()` and `retrain_model_api()`) actually correct?**
  _`ArrivalPredictor` has 3 INFERRED edges - model-reasoned connections that need verification._
- **Should `API Routes & Route Config` be split into smaller, more focused modules?**
  _Cohesion score 0.06259426847662142 - nodes in this community are weakly interconnected._
- **Why does `ArrivalPredictor` connect `Arrival Predictor v2 (ML)` to `Location & Arrival APIs`, `Test Suite & Dependencies`, `Konduktor LLM Integration`, `Data Manager (CSV/DB)`?**
  _High betweenness centrality (0.064) - this node is a cross-community bridge._
- **Should `Test Suite & Dependencies` be split into smaller, more focused modules?**
  _Cohesion score 0.06612244897959184 - nodes in this community are weakly interconnected._
- **Should `Data Manager (CSV/DB)` be split into smaller, more focused modules?**
  _Cohesion score 0.07678075855689177 - nodes in this community are weakly interconnected._
- **Should `Weather & Commute Reasoner` be split into smaller, more focused modules?**
  _Cohesion score 0.0957983193277311 - nodes in this community are weakly interconnected._