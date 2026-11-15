# Ops plane on Linux — journald, forwarding, sizing

Placeholders: `<app>` is the service name; field values are examples.

## Requirements

| ID | Rule |
|---|---|
| OPS-01 | The service writes to stdout/stderr and `journald` collects it. One event per line, structured (JSON or native journal fields) |
| OPS-02 | Every entry carries `LOG_CATEGORY` (`diag`, `audit`, or `ai`), plus `SW_VERSION` and `MODEL_VERSION`. Add the device identifier (UDI-DI) where one is assigned. The central tier uses the category to apply different retention |
| OPS-03 | Journal storage is persistent |
| OPS-04 | The journal is sized to hold **≥ 90 days** at the 95th-percentile daily volume × 1.5. The time cap is the floor **plus a buffer** (120 days), never the floor itself |
| OPS-05 | A daily floor monitor reads the oldest entry. It raises an `audit` warning when the oldest entry is younger than 90 days and the host has been in service longer than 90 days |
| OPS-06 | Alarms fire when the journal passes 80 % of its size cap, and when forwarding lags by more than 24 hours |
| OPS-07 | Rate limits are set so a burst of studies drops no message; suppression notices are themselves alerted on |
| OPS-08 | The clock is synchronised, and every timestamp is UTC with an explicit offset |
| OPS-09 | The software supports forwarding by `systemd-journal-upload` over TLS and by syslog (RFC 5424) over TLS. Where the central store is the long-term tier, forwarding is a documented installation requirement |
| OPS-10 | Forward Secure Sealing is on, with the verification key stored off the host |
| OPS-11 | In a container deployment, the runtime sends stdout to `journald` |

Standards behind OPS-04 to OPS-06: IEC 62443-4-2 CR 2.9 (audit storage capacity) and
CR 2.10 (response to audit-processing failure).

## journald facts that are easy to get wrong

From `man journald.conf`; confirm against the systemd version on the target distribution.

- **There is no minimum-retention setting.** `journald` deletes the oldest files whenever
  a size limit is reached. Every setting below is a cap or a threshold.
- `SystemMaxUse=` defaults to 10 % of the filesystem, **capped at 4 GB**.
- `SystemKeepFree=` defaults to 15 %, capped at 4 GB.
- `MaxRetentionSec=` defaults to 0: no time limit. Setting it to the floor (`90d`) makes
  entries disappear *at* 90 days, so the oldest entry is usually younger than the floor.
- `MaxFileSec=` defaults to one month and controls rotation only, not deletion.
- `Storage=auto` (the default) persists only when `/var/log/journal` exists. Otherwise
  the journal lives in `/run/log/journal` and is lost at reboot.
- `Seal=yes` works only after `journalctl --setup-keys`. Sealing **detects** tampering;
  it does not prevent deletion.
- `RateLimitIntervalSec=30s` and `RateLimitBurst=10000` are the global defaults. A unit
  can override them with `LogRateLimitIntervalSec=` and `LogRateLimitBurst=`.
- Native field names are UPPERCASE letters, digits, and underscores.

## Reference configuration

```ini
# /etc/systemd/journald.conf.d/50-<app>.conf
[Journal]
Storage=persistent
Compress=yes
Seal=yes
SystemMaxUse=8G          # example: size from the measured p95 day × 90 × 1.5
SystemKeepFree=2G
MaxRetentionSec=120day   # 90-day floor + 30-day buffer
MaxFileSec=1week
ForwardToSyslog=no       # forward with journal-upload or an agent instead
```

```ini
# /etc/systemd/system/<app>.service  (excerpt)
[Service]
StandardOutput=journal
StandardError=journal
SyslogIdentifier=<app>
LogExtraFields=LOG_CATEGORY=diag
LogExtraFields=SW_VERSION=2.3.1
LogRateLimitIntervalSec=30s
LogRateLimitBurst=20000  # raise the per-unit burst for heavy study loads
```

`LogExtraFields=` sets a default for the unit. A component that emits `audit` or `ai`
lines must set `LOG_CATEGORY` itself, with native fields:

```python
from systemd import journal   # python-systemd
journal.send("inference failed; result not delivered",
             LOG_CATEGORY="ai", EVENT_ID=event_id, RUN_ID=run_id,
             MODEL_VERSION=model_version, ERROR_CODE="GPU_OOM", PRIORITY=3)
```

Then `journalctl LOG_CATEGORY=ai EVENT_ID=<uuid>` finds every line for one inference.

For Docker, set `"log-driver": "journald"` in `/etc/docker/daemon.json`; `journald` adds a
`CONTAINER_NAME` field.

## Tiers

```
 [Host journald]  ── journal-upload (TLS) · rsyslog · log agent ──►  [Hospital central store / SIEM]  ──►  [Cold archive]
   hot: ≥ 90 days                                                      searchable: 13 months                to 24 months, then delete
   sealed, persistent                                                  per-category retention               write-once storage
   tagged by LOG_CATEGORY                                              role-based access                    legal hold overrides deletion
```

The periods come from [retention.md](retention.md). If the hospital has no central
store, the tiers to the right do not exist: say so in the design, and do not let
`LOG_CATEGORY=ai` metadata be the only trace of an inference.

Minimal syslog forwarding over TLS (CA and certificate globals are also needed):

```
# /etc/rsyslog.d/60-forward.conf
*.* action(type="omfwd" target="siem.example.org" port="6514" protocol="tcp"
           StreamDriver="gtls" StreamDriverMode="1" StreamDriverAuthMode="x509/name")
```

## Sizing and the floor monitor

1. Measure during the pilot: `journalctl --disk-usage`, sampled daily.
2. Take the 95th-percentile day. Budget = p95 × 90 days × 1.5.
3. Set `SystemMaxUse=` to that budget and confirm the filesystem can hold it.
4. Verify continuously with the floor monitor (OPS-05).

The oldest entry, cheaply (the reader stops after one entry):

```bash
journalctl --no-pager --output=json | head -n 1 | jq -r '.__REALTIME_TIMESTAMP'   # microseconds since epoch
```

Run the same check on the central store against its own period.

Fleet arithmetic, for a first estimate only: 100 clients × 100 MB/day is about 3.65 TB a
year before compression. Compression usually cuts that several-fold. Replace the
estimate with measurements.

## Time

- Run `chrony`; `timedatectl` must report `System clock synchronized: yes`.
- Outcome linkage joins events across systems. Clock drift there produces wrong
  conclusions, not just untidy logs.

## Checks worth scripting

| Check | Command |
|---|---|
| Errors since boot | `journalctl -u <app> -p err -b` |
| Lines for one inference | `journalctl EVENT_ID=<uuid>` |
| Journal size | `journalctl --disk-usage` |
| Dropped bursts | `journalctl -u systemd-journald \| grep -i suppressed` |
| Seal integrity | `journalctl --verify` (with the verification key) |
| Time sync | `timedatectl` · `chronyc tracking` |
