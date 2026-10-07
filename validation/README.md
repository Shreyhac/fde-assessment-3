# FDE3 private live validation: index

The source was decoded from `source-package.b64` (SHA256 matched 38ced1d9628af77fbd5784baf05f4ac35a1284f2d4b7611d9a96ef146179bf65)
and unpacked to `AI_Procurement_Copilot/`. `live_mode.diff` holds the only code change: the network-secret live gate.

| Attempt | Model | Probe result | Folder |
|---|---|---|---|
| 1 | gemini-2.5-flash | HTTP 404 NOT_FOUND (model not available to new users) | `attempt1_gemini-2.5-flash_404/` |
| 2 | gemini-3.5-flash (chosen from models.list) | HTTP 503 UNAVAILABLE (high demand) | `attempt2_gemini-3.5-flash_503/` |

Neither attempt produced valid model advice. Public live evals and the live comparison were not run.
To verify attempt 2's archive: `base64 -d live.zip.b64 > live.zip && sha256sum -c live.zip.sha256`.
