# Deployment Runbook

Last verified: 2026-08-17

## Web Production

- Repository: `git@github.com:ghz98315/content_ecosystem.git`
- Production branch: `master`
- Web platform: Vercel via GitHub automatic deployment
- Production URL: `https://content-ecosystem-neon.vercel.app`
- Last pushed Web commit: `697ac55`
- Verification: `curl -I https://content-ecosystem-neon.vercel.app` returned HTTP 200.

The Vercel CLI is not authenticated on this workstation. Use the GitHub push
path unless a Vercel token is explicitly provided. Never store a Vercel token
in this repository.

## Worker / SSH

The Worker is not deployed by Vercel. Heavy processing runs on the designated
SSH host or the local machine and connects to Supabase using `worker/.env`.

SSH host, port, user, and key path are intentionally not stored in Git. Keep
them in the local SSH config (`%USERPROFILE%\\.ssh\\config`) or the team's
secret manager. Do not put passwords, private keys, Supabase service keys, or
APIMart keys in this file.

For a task-scoped run, use the repository script after connecting to the host:

```powershell
powershell -ExecutionPolicy Bypass -File worker/start_task_worker.ps1 `
  -TaskId <task-uuid> `
  -ShutdownAfter
```

The Worker must be isolated with `WORKER_TASK_ID=<task-uuid>`; do not start the
global queue for acceptance tests. Start the IndexTTS cloud instance before a
dual-voice sample and shut it down after the audio/render artifacts are checked.

## Release Checklist

1. Run focused Worker tests and `npm.cmd run build`.
2. Push the intended Web source commit to `origin/master`.
3. Verify the production URL returns HTTP 200 and the expected route loads.
4. Apply any required Supabase migration before using a new online RPC.
5. Restart the task-scoped Worker with the exact task UUID.
6. Record the task UUID, deployment commit, result URL, and acceptance outcome
   in the next progress checkpoint.

## Current Acceptance Blockers

- Video-channel links require an authorized manual video/audio upload.
- The APIMart Web settings are deployed, but Worker-only changes require the
  SSH/local Worker to use the current source tree.
