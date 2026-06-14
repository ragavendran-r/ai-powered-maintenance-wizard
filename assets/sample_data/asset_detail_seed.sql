INSERT INTO asset_profiles (
  equipment_id,
  asset_type,
  location_code,
  location_name,
  parent_system,
  manufacturer,
  model,
  serial_number,
  installed_at,
  owner_team,
  supervisor,
  description,
  last_updated
) VALUES
  ('RM-DRIVE-01', 'AC main drive motor', 'HSM-FS-01', 'Hot strip mill finishing stand F1', 'Hot rolling mill power train', 'Bharat Heavy Electricals', 'MDR-7800', 'RM01-2017-044', '2017-09-14', 'Rolling maintenance', 'Dhruv', 'Main finishing stand drive motor supporting high-torque strip rolling campaigns.', '2026-06-12T09:10:00+05:30'),
  ('BF-BLOWER-02', 'Combustion air blower', 'BF-STOVE-02', 'Blast furnace stove house blower bay', 'Blast furnace combustion air system', 'Howden', 'Variax-CA-2200', 'BF02-2016-118', '2016-11-03', 'Blast furnace maintenance', 'Blast Furnace Supervisor', 'Variable inlet guide vane blower feeding combustion air to the blast furnace stove system.', '2026-06-12T08:40:00+05:30'),
  ('CC-PUMP-03', 'Cooling water pump', 'CC-SEC-03', 'Continuous caster secondary cooling pump room', 'Continuous casting secondary cooling', 'Kirloskar', 'KPD-900', 'CC03-2019-211', '2019-04-22', 'Caster maintenance', 'Caster Maintenance Supervisor', 'Secondary cooling water pump maintaining mold and strand cooling flow during casting.', '2026-06-12T07:55:00+05:30'),
  ('HYD-SYS-04', 'Hydraulic power unit', 'HSM-AGC-04', 'Hot rolling automatic gauge control hydraulic room', 'AGC and roll-gap control', 'Parker Hannifin', 'HPU-4500', 'HYD04-2018-067', '2018-02-18', 'Rolling maintenance', 'Rolling Mill Supervisor', 'Hydraulic power unit and servo circuit controlling roll gap correction and stand force.', '2026-06-12T08:25:00+05:30'),
  ('OH-CRANE-05', 'Overhead process crane', 'MS-CRN-05', 'Melt shop ladle handling bay', 'Melt shop material handling', 'Konecranes', 'LadleMaster-280T', 'OH05-2015-009', '2015-06-30', 'Crane maintenance', 'Melt Shop Supervisor', 'High-capacity overhead crane used for ladle handling and critical maintenance lifts.', '2026-06-12T08:50:00+05:30')
ON CONFLICT(equipment_id) DO UPDATE SET
  asset_type=excluded.asset_type,
  location_code=excluded.location_code,
  location_name=excluded.location_name,
  parent_system=excluded.parent_system,
  manufacturer=excluded.manufacturer,
  model=excluded.model,
  serial_number=excluded.serial_number,
  installed_at=excluded.installed_at,
  owner_team=excluded.owner_team,
  supervisor=excluded.supervisor,
  description=excluded.description,
  last_updated=excluded.last_updated;

INSERT INTO asset_metric_snapshots (
  id,
  equipment_id,
  metric_key,
  label,
  value,
  unit,
  target_value,
  status,
  trend,
  detail,
  captured_at,
  sort_order
) VALUES
  ('AMS-RM-HEALTH', 'RM-DRIVE-01', 'health', 'Health', 10, '%', 80, 'under_target', 'down', 'Health is constrained by vibration, bearing temperature, and bearing spare availability.', '2026-06-12T09:10:00+05:30', 1),
  ('AMS-RM-EFF', 'RM-DRIVE-01', 'efficiency', 'Efficiency', 68, '%', 82, 'under_target', 'down', 'Mill drive load was reduced after vibration exceeded the advisory threshold.', '2026-06-12T09:10:00+05:30', 2),
  ('AMS-RM-RISK', 'RM-DRIVE-01', 'risk', 'Risk', 90, '%', 40, 'over_target', 'up', 'Risk combines critical vibration, temperature trend, and unavailable bearing spare.', '2026-06-12T09:10:00+05:30', 3),
  ('AMS-BF-HEALTH', 'BF-BLOWER-02', 'health', 'Health', 29, '%', 80, 'under_target', 'down', 'Pressure variance has increased above normal operating range.', '2026-06-12T08:40:00+05:30', 1),
  ('AMS-BF-EFF', 'BF-BLOWER-02', 'efficiency', 'Efficiency', 74, '%', 86, 'under_target', 'flat', 'Combustion airflow stability is limited by inlet guide vane response drift.', '2026-06-12T08:40:00+05:30', 2),
  ('AMS-BF-RISK', 'BF-BLOWER-02', 'risk', 'Risk', 71, '%', 40, 'over_target', 'up', 'Pressure variance and actuator drift increase combustion-air delivery risk.', '2026-06-12T08:40:00+05:30', 3),
  ('AMS-CC-HEALTH', 'CC-PUMP-03', 'health', 'Health', 72, '%', 80, 'watch', 'flat', 'Cooling water pump remains stable with no active critical alerts.', '2026-06-12T07:55:00+05:30', 1),
  ('AMS-CC-EFF', 'CC-PUMP-03', 'efficiency', 'Efficiency', 91, '%', 88, 'on_target', 'flat', 'Cooling flow remains above threshold during the sampled casting period.', '2026-06-12T07:55:00+05:30', 2),
  ('AMS-CC-RISK', 'CC-PUMP-03', 'risk', 'Risk', 28, '%', 40, 'on_target', 'flat', 'Risk is low with available spares and stable cooling flow.', '2026-06-12T07:55:00+05:30', 3),
  ('AMS-HYD-HEALTH', 'HYD-SYS-04', 'health', 'Health', 0, '%', 80, 'under_target', 'down', 'Hydraulic temperature and pressure pulsation are both elevated.', '2026-06-12T08:25:00+05:30', 1),
  ('AMS-HYD-EFF', 'HYD-SYS-04', 'efficiency', 'Efficiency', 63, '%', 84, 'under_target', 'down', 'Roll-gap correction is being constrained by temperature and pulsation.', '2026-06-12T08:25:00+05:30', 2),
  ('AMS-HYD-RISK', 'HYD-SYS-04', 'risk', 'Risk', 94, '%', 40, 'over_target', 'up', 'Risk is driven by oil temperature, pulsation, and unavailable pump cartridge.', '2026-06-12T08:25:00+05:30', 3),
  ('AMS-OH-HEALTH', 'OH-CRANE-05', 'health', 'Health', 0, '%', 80, 'under_target', 'down', 'Hoist current and brake temperature require lift restriction review.', '2026-06-12T08:50:00+05:30', 1),
  ('AMS-OH-EFF', 'OH-CRANE-05', 'efficiency', 'Efficiency', 58, '%', 85, 'under_target', 'down', 'Heavy-lift throughput is restricted pending brake inspection follow-up.', '2026-06-12T08:50:00+05:30', 2),
  ('AMS-OH-RISK', 'OH-CRANE-05', 'risk', 'Risk', 96, '%', 40, 'over_target', 'up', 'Critical hoist current and brake spare constraints keep crane risk elevated.', '2026-06-12T08:50:00+05:30', 3)
ON CONFLICT(id) DO UPDATE SET
  equipment_id=excluded.equipment_id,
  metric_key=excluded.metric_key,
  label=excluded.label,
  value=excluded.value,
  unit=excluded.unit,
  target_value=excluded.target_value,
  status=excluded.status,
  trend=excluded.trend,
  detail=excluded.detail,
  captured_at=excluded.captured_at,
  sort_order=excluded.sort_order;

INSERT INTO asset_recommendations (
  id,
  equipment_id,
  action_type,
  title,
  description,
  priority,
  source,
  created_at,
  sort_order
) VALUES
  ('AR-RM-001', 'RM-DRIVE-01', 'inspection', 'Bearing housing inspection', 'Verify drive-end bearing housing temperature, looseness, lubrication condition, and vibration after load reduction.', 1, 'asset_detail_seed', '2026-06-12T09:10:00+05:30', 1),
  ('AR-RM-002', 'RM-DRIVE-01', 'planning', 'Reserve bearing replacement window', 'Coordinate bearing spare delivery and outage planning if vibration remains above threshold.', 2, 'asset_detail_seed', '2026-06-12T09:10:00+05:30', 2),
  ('AR-BF-001', 'BF-BLOWER-02', 'inspection', 'Stroke-test inlet guide vane actuator', 'Check actuator travel, linkage looseness, and feedback drift against pressure variance trend.', 1, 'asset_detail_seed', '2026-06-12T08:40:00+05:30', 1),
  ('AR-BF-002', 'BF-BLOWER-02', 'calibration', 'Calibrate position feedback', 'Calibrate the inlet guide vane position transmitter if command and feedback differ during stroke testing.', 2, 'asset_detail_seed', '2026-06-12T08:40:00+05:30', 2),
  ('AR-CC-001', 'CC-PUMP-03', 'monitoring', 'Continue cooling flow trend review', 'Keep secondary cooling flow and motor current on shift watch during long casting campaigns.', 3, 'asset_detail_seed', '2026-06-12T07:55:00+05:30', 1),
  ('AR-CC-002', 'CC-PUMP-03', 'preventive', 'Verify standby pump readiness', 'Confirm standby pump availability and minimum spare seal kit inventory before campaign extension.', 3, 'asset_detail_seed', '2026-06-12T07:55:00+05:30', 2),
  ('AR-HYD-001', 'HYD-SYS-04', 'inspection', 'Inspect cooler differential temperature', 'Check cooler fouling, bypass valve position, and return-line temperature while oil temperature is elevated.', 1, 'asset_detail_seed', '2026-06-12T08:25:00+05:30', 1),
  ('AR-HYD-002', 'HYD-SYS-04', 'spares', 'Reserve pump cartridge assembly', 'Hold pump cartridge assembly before intrusive inspection because pressure pulsation is increasing.', 2, 'asset_detail_seed', '2026-06-12T08:25:00+05:30', 2),
  ('AR-OH-001', 'OH-CRANE-05', 'restriction', 'Maintain heavy-lift restriction', 'Keep heavy lifts restricted until brake temperature and hoist current are verified after inspection.', 1, 'asset_detail_seed', '2026-06-12T08:50:00+05:30', 1),
  ('AR-OH-002', 'OH-CRANE-05', 'planning', 'Plan brake shoe replacement', 'Schedule brake shoe replacement planning because the brake shoe set is not currently available.', 2, 'asset_detail_seed', '2026-06-12T08:50:00+05:30', 2)
ON CONFLICT(id) DO UPDATE SET
  equipment_id=excluded.equipment_id,
  action_type=excluded.action_type,
  title=excluded.title,
  description=excluded.description,
  priority=excluded.priority,
  source=excluded.source,
  created_at=excluded.created_at,
  sort_order=excluded.sort_order;

INSERT INTO asset_subsystems (
  id,
  equipment_id,
  name,
  component,
  condition,
  detail,
  sort_order
) VALUES
  ('AS-RM-001', 'RM-DRIVE-01', 'Drive train and coupling', 'Flexible coupling and guard', 'watch', 'Coupling alignment must be checked because vibration rose under rolling load.', 1),
  ('AS-RM-002', 'RM-DRIVE-01', 'Bearing housing and lubrication', 'Drive-end spherical roller bearing', 'critical', 'Bearing temperature and vibration exceed advisory limits.', 2),
  ('AS-RM-003', 'RM-DRIVE-01', 'Protection signals', 'Vibration and temperature monitoring', 'degraded', 'Primary protection signals are active and require confirmation.', 3),
  ('AS-BF-001', 'BF-BLOWER-02', 'Inlet guide vane assembly', 'IGV actuator and linkage', 'degraded', 'Pressure variance indicates actuator response drift or linkage looseness.', 1),
  ('AS-BF-002', 'BF-BLOWER-02', 'Blower rotor', 'Impeller and shaft bearings', 'watch', 'Rotor should be inspected if pressure variance persists after actuator checks.', 2),
  ('AS-BF-003', 'BF-BLOWER-02', 'Combustion air controls', 'Position feedback transmitter', 'watch', 'Command and feedback alignment should be verified during stroke testing.', 3),
  ('AS-CC-001', 'CC-PUMP-03', 'Pump hydraulic end', 'Impeller and casing', 'normal', 'Cooling flow is stable and above minimum campaign threshold.', 1),
  ('AS-CC-002', 'CC-PUMP-03', 'Mechanical seal', 'Seal cartridge and flush line', 'watch', 'Seal kit availability should be verified for campaign extension.', 2),
  ('AS-CC-003', 'CC-PUMP-03', 'Motor and starter', 'Pump motor current monitoring', 'normal', 'Motor current remains within normal sampled range.', 3),
  ('AS-HYD-001', 'HYD-SYS-04', 'Hydraulic power unit', 'Main pump cartridge', 'critical', 'Pump cartridge spare is unavailable while pressure pulsation is increasing.', 1),
  ('AS-HYD-002', 'HYD-SYS-04', 'Oil cooling circuit', 'Cooler and bypass valve', 'degraded', 'Oil temperature is above target during roll-gap corrections.', 2),
  ('AS-HYD-003', 'HYD-SYS-04', 'Servo control loop', 'AGC servo valves', 'watch', 'Pressure pulsation must be trended against command signal changes.', 3),
  ('AS-OH-001', 'OH-CRANE-05', 'Main hoist drive', 'Hoist motor and gearbox', 'critical', 'Hoist current is above safe heavy-lift limit.', 1),
  ('AS-OH-002', 'OH-CRANE-05', 'Hoist braking system', 'Brake shoe set', 'critical', 'Brake shoe set is unavailable and replacement planning is required.', 2),
  ('AS-OH-003', 'OH-CRANE-05', 'Wire rope and hook block', 'Load path components', 'watch', 'Load path should remain under inspection during lift restriction.', 3)
ON CONFLICT(id) DO UPDATE SET
  equipment_id=excluded.equipment_id,
  name=excluded.name,
  component=excluded.component,
  condition=excluded.condition,
  detail=excluded.detail,
  sort_order=excluded.sort_order;

INSERT INTO asset_reliability_metrics (
  id,
  equipment_id,
  metric_name,
  value,
  unit,
  target_value,
  status,
  trend,
  detail,
  sort_order
) VALUES
  ('ARM-RM-001', 'RM-DRIVE-01', 'MTBF', 96, 'days', 180, 'under_target', 'down', 'Bearing and alignment events reduced mean time between failures.', 1),
  ('ARM-RM-002', 'RM-DRIVE-01', 'MTTR', 14, 'hours', 8, 'over_target', 'up', 'Bearing replacement requires outage coordination and crane support.', 2),
  ('ARM-RM-003', 'RM-DRIVE-01', 'Repeat failure count', 2, 'events', 1, 'watch', 'flat', 'Recent vibration recurrence is linked to drive-end bearing and alignment findings.', 3),
  ('ARM-BF-001', 'BF-BLOWER-02', 'MTBF', 140, 'days', 200, 'watch', 'down', 'Actuator drift events are increasing in the pressure-control loop.', 1),
  ('ARM-BF-002', 'BF-BLOWER-02', 'MTTR', 6, 'hours', 6, 'on_target', 'flat', 'Actuator inspection can normally be completed in one shift.', 2),
  ('ARM-BF-003', 'BF-BLOWER-02', 'Repeat failure count', 1, 'events', 1, 'on_target', 'flat', 'Current pressure variance is the first high event in the sampled period.', 3),
  ('ARM-CC-001', 'CC-PUMP-03', 'MTBF', 240, 'days', 210, 'on_target', 'flat', 'Cooling pump reliability is above campaign target.', 1),
  ('ARM-CC-002', 'CC-PUMP-03', 'MTTR', 5, 'hours', 6, 'on_target', 'flat', 'Standby pump and seal kits keep repair time within target.', 2),
  ('ARM-CC-003', 'CC-PUMP-03', 'Repeat failure count', 0, 'events', 1, 'on_target', 'flat', 'No repeat cooling-flow failures are present in the sampled history.', 3),
  ('ARM-HYD-001', 'HYD-SYS-04', 'MTBF', 82, 'days', 160, 'under_target', 'down', 'Hydraulic temperature and pulsation events are recurring.', 1),
  ('ARM-HYD-002', 'HYD-SYS-04', 'MTTR', 16, 'hours', 8, 'over_target', 'up', 'Pump cartridge availability can extend repair time.', 2),
  ('ARM-HYD-003', 'HYD-SYS-04', 'Repeat failure count', 2, 'events', 1, 'watch', 'up', 'Hydraulic pressure pulsation has repeated across recent campaigns.', 3),
  ('ARM-OH-001', 'OH-CRANE-05', 'MTBF', 70, 'days', 180, 'under_target', 'down', 'Brake and hoist current events are reducing crane availability.', 1),
  ('ARM-OH-002', 'OH-CRANE-05', 'MTTR', 12, 'hours', 6, 'over_target', 'up', 'Brake shoe material constraints can delay return to full lift service.', 2),
  ('ARM-OH-003', 'OH-CRANE-05', 'Repeat failure count', 3, 'events', 1, 'critical', 'up', 'Repeated hoist braking issues require supervisor follow-up.', 3)
ON CONFLICT(id) DO UPDATE SET
  equipment_id=excluded.equipment_id,
  metric_name=excluded.metric_name,
  value=excluded.value,
  unit=excluded.unit,
  target_value=excluded.target_value,
  status=excluded.status,
  trend=excluded.trend,
  detail=excluded.detail,
  sort_order=excluded.sort_order;

INSERT INTO documents (id, source_type, equipment_id, title, content) VALUES
  ('DOC-RM-LOG-03', 'log', 'RM-DRIVE-01', 'Main Drive Vibration Shift Log', 'Shift log: vibration increased after finishing stand load rose. Operator reduced load and maintenance verified drive-end bearing housing temperature.'),
  ('DOC-RM-HIST-04', 'history', 'RM-DRIVE-01', 'Main Drive Bearing Replacement History', 'History note: the drive-end bearing was replaced after outer race pitting and grease degradation were found during a previous vibration event.'),
  ('DOC-BF-LOG-03', 'log', 'BF-BLOWER-02', 'Combustion Air Blower Pressure Log', 'Shift log: outlet pressure oscillation repeated during furnace ramp-up when inlet guide vane feedback lagged command position.'),
  ('DOC-BF-HIST-04', 'history', 'BF-BLOWER-02', 'Combustion Blower Actuator History', 'History note: prior pressure variance was corrected by cleaning actuator linkage and recalibrating the position feedback transmitter.'),
  ('DOC-BF-MAN-02', 'manual', 'BF-BLOWER-02', 'Inlet Guide Vane Actuator Manual', 'Manual excerpt: inspect actuator linkage, position feedback calibration, and pneumatic supply before replacing the inlet guide vane actuator.'),
  ('DOC-CC-SOP-01', 'sop', 'CC-PUMP-03', 'Cooling Pump Flow Stability SOP', 'SOP excerpt: verify pump suction pressure, strainer differential pressure, seal flush flow, and standby pump readiness when cooling flow approaches alarm limits.'),
  ('DOC-CC-MAN-02', 'manual', 'CC-PUMP-03', 'Secondary Cooling Pump Manual', 'Manual excerpt: inspect impeller clearance, mechanical seal flush, bearing temperature, and motor current before extending casting campaign operation.'),
  ('DOC-CC-LOG-03', 'log', 'CC-PUMP-03', 'Cooling Water Flow Shift Log', 'Shift log: cooling water flow stayed above the minimum campaign threshold after seal flush line inspection and standby pump verification.'),
  ('DOC-CC-HIST-01', 'history', 'CC-PUMP-03', 'Cooling Pump Campaign History', 'History note: cooling flow remained stable through the previous campaign after seal flush inspection and standby pump verification.'),
  ('DOC-HYD-LOG-03', 'log', 'HYD-SYS-04', 'Hydraulic Temperature Pulsation Event Log', 'Event log: oil temperature and pressure pulsation increased during roll-gap correction. Cooler differential temperature check was requested.'),
  ('DOC-HYD-HIST-04', 'history', 'HYD-SYS-04', 'Hydraulic Servo Valve Cleaning History', 'History note: previous pressure hunting was reduced after servo valve cleaning, return filter replacement, and relief valve calibration.'),
  ('DOC-OH-LOG-04', 'log', 'OH-CRANE-05', 'Overhead Crane Hoist Current Shift Log', 'Shift log: hoist current exceeded the heavy-lift limit during ladle bay movement and the lift restriction remained in force pending brake inspection.'),
  ('DOC-OH-HIST-03', 'history', 'OH-CRANE-05', 'Overhead Crane Hoist Brake History', 'History note: brake temperature normalized after lift restriction, but brake shoe replacement remains a follow-up planning item.')
ON CONFLICT(id) DO UPDATE SET
  source_type=excluded.source_type,
  equipment_id=excluded.equipment_id,
  title=excluded.title,
  content=excluded.content;

INSERT INTO maintenance_events (
  id,
  equipment_id,
  date,
  issue,
  root_cause,
  action,
  downtime_hours
) VALUES
  ('ME-8805', 'CC-PUMP-03', '2026-05-19', 'Secondary cooling flow dipped during long casting campaign', 'Seal flush strainer restriction reduced pump margin', 'Cleaned seal flush strainer, verified standby pump auto-start, and increased shift flow checks', 1.5)
ON CONFLICT(id) DO UPDATE SET
  equipment_id=excluded.equipment_id,
  date=excluded.date,
  issue=excluded.issue,
  root_cause=excluded.root_cause,
  action=excluded.action,
  downtime_hours=excluded.downtime_hours;

INSERT INTO work_orders (
  id,
  equipment_id,
  title,
  description,
  status,
  priority,
  work_type,
  failure_class,
  problem_code,
  classification,
  assigned_to,
  supervisor,
  due_date,
  recommended_action,
  follow_up_required,
  ai_summary,
  completion_summary,
  created_at,
  updated_at,
  completed_at
) VALUES
  (
    'WO-8320',
    'CC-PUMP-03',
    'Verify secondary cooling pump standby readiness',
    'Confirm standby pump auto-start, seal flush flow, suction strainer condition, and minimum flow margin before campaign extension.',
    'APPR',
    3,
    'PM',
    'MECH',
    'FLOWMARGIN',
    'Cooling flow margin',
    'Caster Technician',
    'Caster Maintenance Supervisor',
    '2026-06-15T09:00:00+05:30',
    'Verify seal flush line cleanliness and standby pump readiness before extending the casting campaign.',
    0,
    'Cooling pump is stable, but standby readiness should be confirmed before campaign extension.',
    NULL,
    '2026-06-12T07:40:00+05:30',
    '2026-06-12T07:55:00+05:30',
    NULL
  )
ON CONFLICT(id) DO UPDATE SET
  equipment_id=excluded.equipment_id,
  title=excluded.title,
  description=excluded.description,
  status=excluded.status,
  priority=excluded.priority,
  work_type=excluded.work_type,
  failure_class=excluded.failure_class,
  problem_code=excluded.problem_code,
  classification=excluded.classification,
  assigned_to=excluded.assigned_to,
  supervisor=excluded.supervisor,
  due_date=excluded.due_date,
  recommended_action=excluded.recommended_action,
  follow_up_required=excluded.follow_up_required,
  ai_summary=excluded.ai_summary,
  completion_summary=excluded.completion_summary,
  updated_at=excluded.updated_at,
  completed_at=excluded.completed_at;

DELETE FROM work_order_logs WHERE work_order_id = 'WO-8320';
INSERT INTO work_order_logs (work_order_id, author, entry_type, content) VALUES
  ('WO-8320', 'Maintenance Wizard', 'assistant', 'Check standby pump auto-start, seal flush flow, suction strainer differential pressure, and minimum campaign flow margin.'),
  ('WO-8320', 'Caster Maintenance Supervisor', 'planning', 'Schedule readiness check before campaign extension approval.');
