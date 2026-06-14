# Ingestion Sample Files

Use these files from the frontend Ingestion view to test document-file upload. Sign in as an `admin` or `reliability_engineer` demo user; those roles can upload documents through the UI.

Select the matching Source value before uploading each file:

- `sop`: `RM-DRIVE-01_SOP_main_drive_bearing_vibration.md`
- `manual`: `BF-BLOWER-02_MANUAL_inlet_guide_vane_actuator.txt`
- `log`: `HYD-SYS-04_LOG_hydraulic_temperature_pulsation.log`
- `alert`: `OH-CRANE-05_ALERT_hoist_current_brake_temperature.json`
- `spares`: `CC-PUMP-03_SPARES_cooling_pump_inventory.csv`
- `history`: `RM-DRIVE-01_HISTORY_drive_bearing_maintenance.json`

The files use upload-supported formats: Markdown, text, log, JSON, and CSV.

Uploaded text is stored as a document, chunked for retrieval, indexed into Qdrant when the vector store is available, and processed into document intelligence for future assistant context.
