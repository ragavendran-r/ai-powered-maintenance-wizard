INSERT INTO users (
  id,
  email,
  display_name,
  role,
  password_hash,
  is_active
) VALUES
  (
    'USER-ADMIN',
    'admin@plant.local',
    'Plant Admin',
    'admin',
    '$2b$12$qekSj9KAF4s6g0pqxwySkeurvNetGsTOs1wLHpd39ZjgXUOAuP7Xi',
    1
  ),
  (
    'USER-MAINTENANCE',
    'maintenance@plant.local',
    'Maintenance Engineer',
    'maintenance_engineer',
    '$2b$12$qekSj9KAF4s6g0pqxwySkeurvNetGsTOs1wLHpd39ZjgXUOAuP7Xi',
    1
  ),
  (
    'USER-TECHNICIAN',
    'technician@plant.local',
    'Maintenance Technician',
    'maintenance_technician',
    '$2b$12$qekSj9KAF4s6g0pqxwySkeurvNetGsTOs1wLHpd39ZjgXUOAuP7Xi',
    1
  ),
  (
    'USER-SUPERVISOR',
    'supervisor@plant.local',
    'Maintenance Supervisor',
    'maintenance_supervisor',
    '$2b$12$qekSj9KAF4s6g0pqxwySkeurvNetGsTOs1wLHpd39ZjgXUOAuP7Xi',
    1
  ),
  (
    'USER-RELIABILITY',
    'reliability@plant.local',
    'Reliability Engineer',
    'reliability_engineer',
    '$2b$12$qekSj9KAF4s6g0pqxwySkeurvNetGsTOs1wLHpd39ZjgXUOAuP7Xi',
    1
  ),
  (
    'USER-PLANNER',
    'planner@plant.local',
    'Maintenance Planner',
    'planner',
    '$2b$12$qekSj9KAF4s6g0pqxwySkeurvNetGsTOs1wLHpd39ZjgXUOAuP7Xi',
    1
  ),
  (
    'USER-OPERATOR',
    'operator@plant.local',
    'Shift Operator',
    'operator',
    '$2b$12$qekSj9KAF4s6g0pqxwySkeurvNetGsTOs1wLHpd39ZjgXUOAuP7Xi',
    1
  ),
  (
    'USER-IOT-SERVICE',
    'iot-service@plant.local',
    'IoT Service Account',
    'iot_service',
    '$2b$12$qekSj9KAF4s6g0pqxwySkeurvNetGsTOs1wLHpd39ZjgXUOAuP7Xi',
    1
  )
ON CONFLICT(email) DO NOTHING;
