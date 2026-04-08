# Sandy Cloud Migration Plan

Status: Draft - Awaiting user approval

## Scope
- Move Sandy brain from local Python runtime to Azure Functions HTTP gateway.
- Keep ESP32 and ESP32-CAM as edge executors (servo, display, camera, motors).
- Keep current behavior working while migrating gradually.

## Constraints
- No breaking changes to working hardware behaviors.
- Single endpoint first: `/api/sandy_brain`.
- Synchronous request-response for ESP32.
- Memory remains local fallback first, then migrate to MongoDB Atlas.

## Phase 1 (Now): Foundation and Safety
1. Security hygiene
2. Azure Function bootstrap endpoint
3. Local smoke test

### Tasks
- [x] Ensure secrets are not tracked in git (`.env`, Arduino `secrets.h`).
- [x] Add safe template files for Arduino secrets.
- [x] Add basic `sandy_brain` endpoint in `function_app.py`.
- [ ] Validate local function host start and endpoint response.

## Phase 2: Brain Routing
1. Add source-aware request parser (`esp32`, `telegram`).
2. Route text command to cloud brain handler.
3. Return unified response envelope.

## Phase 3: Telegram Webhook in Cloud
1. Add webhook endpoint.
2. Verify Telegram updates trigger same command pipeline.
3. Remove local polling dependency.

## Phase 4: Memory Migration
1. Keep JSON fallback.
2. Add MongoDB Atlas repository layer.
3. Switch by environment flag.

## Phase 5: Voice Path
1. Add audio payload contract.
2. Add STT in cloud.
3. Optional TTS audio response stream to ESP32.

## Validation Checklist
- Endpoint health: returns `alive`.
- Echo path: returns normalized payload.
- ESP32 timeout under target budget.
- No secrets committed.

## Notes
- Arduino sketches can be edited via Arduino Cloud Editor after initial setup.
- OTA updates reduce cable usage but first provisioning and recovery may still require USB.
