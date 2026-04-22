# Veeder Root Relay — Project Estimate

## Summary

Rebuild of the Veeder Root relay system to resolve the field issues identified (serial port locking, overlapping connections, device crashes) and improve security posture. The new system replaces ~6,700 lines of Node.js with a ~100 line Python script, eliminates PM2 and AWS IoT dependencies, and includes a CLI management tool, firewall hardening, and automated testing.

## Prior Engagements

Debugging and troubleshooting of the existing Node.js relay system, including root cause analysis of serial port locking, unhandled error events, shutdown lifecycle bugs, and connection overlap issues.

| Item | Hours | Cost |
|---|---|---|
| Debugging and troubleshooting | 5 | $500 |
| **Prior engagements total** | **5** | **$500** |

## Development

Rebuild of the relay system, including testing, documentation, and tooling:

- Relay application (Python)
- CLI management tool (`veeder` command)
- Unit tests (17 tests)
- Integration test suite (16 tests — health checks + end-to-end relay)
- Install script (single command deployment)
- systemd scheduling (replaces PM2)
- Firewall configuration
- Documentation (README, architecture decisions)

| Item | Hours | Cost |
|---|---|---|
| Architecture and rebuild | 4 | $400 |
| CLI management tool | 2 | $200 |
| Unit and integration tests | 2 | $200 |
| Install script and systemd setup | 1 | $100 |
| Firewall and security hardening | 1 | $100 |
| Documentation | 1 | $100 |
| **Development total** | **11** | **$1,100** |

## Phase 1: Pilot Deployment (1 site)

Deploy to a single site, validate against a live Veeder Root, and confirm data reaches the central server correctly.

| Item | Hours | Cost |
|---|---|---|
| Install and configure on pilot device | 1 | $100 |
| Validate data flow with central server | 1 | $100 |
| Monitor pilot site over 48 hours | 1 | $100 |
| Address any issues found | 2 | $200 |
| Disable old Node.js relay on pilot device | 0.5 | $50 |
| **Phase 1 total** | **5.5** | **$550** |

## Phase 2: Post-Deployment Support (2 weeks)

Monitoring and support window after rollout to catch any issues that didn't appear during pilot.

| Item | Hours | Cost |
|---|---|---|
| Daily fleet health checks (15 min/day x 10 business days) | 2.5 | $250 |
| Issue investigation and fixes (estimated) | 3 | $300 |
| **Phase 2 total** | **5.5** | **$550** |

## Project Total

| Phase | Hours | Cost |
|---|---|---|
| Prior engagements | 5 | $500 |
| Development | 11 | $1,100 |
| Phase 1 — Pilot | 5.5 | $550 |
| Phase 2 — Post-deployment support | 5.5 | $550 |
| **Total** | **27** | **$2,700** |

## Timeline

| Phase | Duration |
|---|---|
| Prior engagements | Complete |
| Development | 1 week |
| Phase 1 — Pilot | 1 week (includes 48-hour monitoring) |
| Phase 2 — Support | 2 weeks (runs concurrently after pilot) |
| **Total estimated timeline** | **3 weeks from approval** |

## What's Included

- Complete rewrite of relay system (Python)
- CLI management tool for device diagnostics
- Automated install script (single command per device)
- Unit and integration test suites
- Firewall hardening
- systemd scheduling (replaces PM2)
- Full documentation
- Decommission of old Node.js/PM2 system on pilot device
- 2-week post-deployment support window

## Ongoing Support Options

### Monthly Retainer

A fixed block of hours reserved each month for proactive maintenance, fleet health monitoring, software updates, and support. Unused hours do not roll over.

| Plan | Hours/Month | Monthly Cost | Savings |
|---|---|---|---|
| Basic | 3 | $250 | 17% off hourly rate |
| Standard | 5 | $400 | 20% off hourly rate |
| Premium | 10 | $750 | 25% off hourly rate |

Retainer hours cover:

- Periodic fleet health checks
- Software updates and patches
- Configuration changes
- Performance monitoring
- Priority response (within 4 business hours)

Hours beyond the retainer are billed at the standard rate of $100/hour.

### Ad-Hoc Troubleshooting

For clients without a retainer, troubleshooting and support services are available on demand.

| Item | Rate |
|---|---|
| Hourly rate | $100/hour |
| Minimum charge per incident | $100 (1 hour) |
| Billing increment | 15 minutes |

Examples of ad-hoc work:

- Diagnosing a device that has stopped reporting
- Investigating connection or serial port issues
- Deploying the relay to additional devices
- Configuration changes across multiple sites
- Emergency troubleshooting

### Optional: TLS Encryption

If the TCP connection between the Pi and the central server traverses the public internet, TLS encryption is recommended. This would require a change on the central server side.

| Item | Hours | Cost |
|---|---|---|
| Pi-side TLS implementation | 1 | $100 |
| Central server TLS coordination/testing | 2 | $200 |
| **TLS total** | **3** | **$300** |
