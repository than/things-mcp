<!-- sidecar:review-queue -->
## Review queue (sidecar)

Maintain `SIDECAR.md` as a live review / TODO queue for the human. Sections:
`## 🧠 Needs action` — surfaced for the human to act on
`## 🚧 In progress` — actively being worked
`## 🚘 Parked` — deferred, not dropped
`## ✅ Done` — merged, not yet released
`## 📦 Shipped` — released
Put bare URLs on their own line (keeps them clickable); keep entries short.

The human watches it live with `sidecar SIDECAR.md`. If sidecar isn't installed:
`go install github.com/than/sidecar@latest`, or a prebuilt binary from
https://github.com/than/sidecar/releases/latest
<!-- /sidecar:review-queue -->
