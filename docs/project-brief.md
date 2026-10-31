# SmartIoT Home Control Platform

**Project brief** · Software Quality Assurance and Test Automation · Author: Arshaduzzaman

## Summary

SmartIoT is a complete smart-home monitoring platform that I designed, built and tested end to end. Sensors in every room report temperature, humidity, air pressure, light and battery level. The platform collects these readings, checks them, stores them, raises alerts when something is wrong, and presents everything in a secure web dashboard. From there, people can control devices and install software updates remotely.

The project's purpose is to demonstrate professional quality engineering: how a real product is planned, built in small verified steps, tested at every level, secured, measured under load and documented. The sensors are simulated in software, so the whole system runs on a single laptop with one command.

## What the product does

| Capability | What it means for the user |
|---|---|
| Live home overview | One screen shows how the home is doing: devices online, average temperature and humidity, and anything that needs attention, updated every few seconds |
| Alerts | Automatic warnings for low batteries, temperatures out of range, high humidity and devices that stop reporting |
| Device control | Restart a device, ask for a fresh reading, or change how often it reports, and see the result |
| Remote software updates | Upload a new firmware version and install it on a device; a failed or interrupted update leaves the device on its previous version |
| Secure access | Sign-in with three roles (viewer, operator, administrator); administrators create and remove accounts and assign roles |
| Account recovery | A user who forgets their username or password receives both by email, with a one-time, time-limited reset link |

## My role and approach

I owned the project from requirements to final report: planning, architecture, implementation, test strategy, automation, security, performance testing, CI/CD and documentation.

The work was split into 19 phases. Every phase followed the same professional routine:

1. Build only that phase's scope.
2. Verify it by hand on the running system.
3. Add automated tests for normal use, invalid input and edge cases.
4. Update the documentation.
5. Review, commit and merge through a pull request with automated checks.

This mirrors how quality-focused teams deliver software: small, verified increments with evidence at each step.

## Results

| Area | Result |
|---|---|
| Automated tests | **816 tests** across 7 levels, from single functions to the full system in a real browser; all passing |
| Requirements | **11 of 11** requirements traced to the tests that prove them |
| Defects | **41 defects** found and fixed during development, each now guarded by a test |
| Reliability | **No data lost or duplicated** when the database, message broker or data receiver failed during operation |
| Performance | **303 requests per second** with 300 simultaneous users and **0 % errors** |
| Scale | **100 devices** reporting every second, stored within one second |
| Security | Encrypted connections everywhere (TLS), role-based access, protection against password guessing, secure account recovery, automatic checks for vulnerable dependencies |
| Test effectiveness | Deliberately introduced bugs were caught by the test suite (mutation checks) |

## Quality engineering highlights

- **Layered test strategy.** Fast unit tests for logic; integration tests against a real database and message broker; browser tests for every screen state; end-to-end tests with simulated devices. When something breaks, the failing level points to the cause.
- **Failure testing.** The database, broker and receiver were switched off in the middle of operation to prove that no reading is lost or counted twice.
- **Performance testing that changed the design.** Load tests revealed that the API stopped responding after heavy traffic. The fix raised throughput from 124 to 303 requests per second with zero errors.
- **Security verified by tests, not assumed.** Every role was tested against every function, every device account against every message channel, and outdated encryption versions were confirmed to be refused by the server.
- **Continuous integration.** Every pull request runs the full test suite, a fresh start of the whole system, and a dependency vulnerability audit on GitHub Actions.
- **AI-assisted QA.** A tool built on the Claude API turns a written requirement into structured test cases and explains why a test run failed.

## Technology

| Area | Tools |
|---|---|
| Languages | Python, TypeScript |
| Backend | FastAPI (REST API), SQLAlchemy, MySQL |
| Device messaging | MQTT (Mosquitto broker) |
| Frontend | React, Vite, nginx |
| Testing | pytest, Playwright (browser automation), k6 (load testing) |
| Security | TLS certificates, JWT sign-in, role-based access control |
| DevOps | Docker, Docker Compose, GitHub Actions |
| AI | Claude API (Anthropic) |

## Architecture at a glance

```text
Room sensors ──encrypted MQTT──▶ Message broker ──▶ Data receiver ──▶ Database
     ▲                                                                 │
     │ commands and updates                                            ▼
     └─────────────────────── REST API ◀───────────────────────────────┘
                                 ▲
                          encrypted HTTPS
                                 │
                          Web dashboard
```

Each part has a single responsibility and can be tested on its own, which is what makes the layered test strategy possible.

## Five-minute demonstration

1. Start everything with `docker compose up -d --build` and open https://localhost:8443.
2. Sign in as the administrator. The home status banner and overview tiles show the live state of the home.
3. Under **Devices**, search, filter offline devices, sort by temperature, and switch to the rooms view.
4. Open a device: view its trend chart, then restart it (the system asks for confirmation) and watch the command complete.
5. Under **Firmware**, upload a version and install it on a device; watch it download, verify and install.
6. Under **Users**, create an account with an email address, then use **Forgot username or password?** on the sign-in page and open the email at http://localhost:8025.
7. Stop the database for a moment and start it again: the dashboard reports the outage, and no data is lost.
8. Run the full test suite: `docker compose -f compose.test.yaml run --rm --build tests`.

## Skills demonstrated

Test strategy and planning · Test automation (API, integration, UI, end to end) · Performance and reliability testing · Security testing · Defect analysis and reporting · Requirements traceability · CI/CD · Docker · Python and TypeScript development · Technical documentation · AI-assisted testing

## Further reading

- [Final QA report](testing/final-report.md): test inventory, requirements traceability, defect log, known limitations
- [Reliability tests](testing/reliability.md) and [performance tests](testing/performance.md)
- [Security](security/security.md) and [encryption (TLS)](security/tls.md)
- [README](../README.md): quick start and feature overview
