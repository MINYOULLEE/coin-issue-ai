# Alert and local startup repair — 2026-09-01

News alert oscillation was caused by immediate notification of each transient failure and immediate recovery on the following success. Notification v29 debounces news only: at least three distinct-minute observations over two minutes to open, and two observations over one minute to resolve. Existing active incidents retain their text until resolved. A/B execution failures remain immediate; raw news status and error collection remain intact. Final verification: all 82 Node tests passed, 58 frozen files passed the separation audit, and two Python reserved-margin tests passed. All four deployed notification source files match local sources. Cron timeout is confirmed at 45 seconds. A/B enabled=true and test_mode=false were verified after deployment; cloud collector and notifier timestamps continue updating.

The screenshot's 15-second timeout occurred during DNS lookup, before HTTP response. Telegram scheduler timeout increased from 15 to 45 seconds while preserving one-minute cadence. This mitigates short network stalls, but does not guarantee external DNS availability or suppress genuine timeout errors.

Windows task `\Coin Issue AI Collector` launches `C:\Users\Admin\Desktop\coin-issue-ai-live\START_COLLECTOR_WINDOWS.bat`. Its Python app can overwrite the cloud live snapshot with legacy local data, so the running task and its identified children were stopped. Windows denied disabling the task (administrator permission). The task remains enabled and needs an administrator to disable it in Task Scheduler. No local files were deleted; no OS/system collectors were touched. Do not claim startup disable is complete.

A/B trading switches, sizing, signals and schedules are unchanged. News 403 sources remain unresolved. This repair does not perform the previously proposed large-scale function-call consolidation.

## Follow-up: Windows administrator approval completed

On 2026-09-01 the owner explicitly authorized administrator execution. An elevated Windows PowerShell process disabled only `\Coin Issue AI Collector`, after checking its action targets the exact legacy batch path above. A fresh task query confirmed `Settings.Enabled=false` and state Disabled. The earlier access-denied status is historical, not the current outcome. Files and cloud schedules were not changed.

News dependency review: A's `answerFeatures` uses market candles and its decision tree; B's `runCombinationSignals` uses completed candles and its own opportunity state. News feeds populate issues/status/dashboard themes, not the adopted A/B signal inputs. The cloud collector currently waits for market and news fetches together before A signal management; do not disable that whole function to remove news. News-only removal or reduced cadence needs a separate scoped change; neither was performed in this follow-up.
