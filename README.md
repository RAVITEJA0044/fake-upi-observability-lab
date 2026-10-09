# Fake UPI Observability Lab (simulation only)

This is a browser-cloud lab template. It processes no real payments and must not be connected to a bank, UPI network, real payment gateway, or production data.

## Components
- Python/FastAPI fake payment API on port 8000
- VictoriaMetrics on port 8428
- Loki on port 3100
- Grafana Alloy log collector on port 12345
- Perses on port 8080

## Start in a browser-based cloud dev environment
1. Create a GitHub repository and upload these files, or open them in a cloud IDE that supports Docker Compose.
2. Start a terminal in that cloud environment.
3. Run: `docker compose up --build -d`
4. Open the forwarded port for each service in the cloud IDE. Use the IDE's generated public/forwarded URL, not localhost on your personal computer.
5. Check the API root, `/health`, and `/admin/scenario`.

Some cloud IDEs restrict Docker-in-Docker, public port forwarding, or long-running containers. If Compose is blocked, choose a cloud environment that explicitly supports Docker Compose and port forwarding.

## First checks
- API: `GET /`
- Health: `GET /health`
- Metrics: `GET /metrics`
- Current scenario: `GET /admin/scenario`
- Create fake payment: `POST /payments`
- Payment status: `GET /payments/{payment_id}`

## Trigger simulated incidents
Use the API's forwarded URL as `API_URL` in the commands below.

Normal:
`curl -X POST "$API_URL/admin/scenario/normal"`

HTTP 500 failures:
`curl -X POST "$API_URL/admin/scenario/errors"`

Slow responses (~2 seconds):
`curl -X POST "$API_URL/admin/scenario/slow"`

Service unavailable (health and payment endpoints return 503):
`curl -X POST "$API_URL/admin/scenario/down"`

Random failures (~35% of create requests):
`curl -X POST "$API_URL/admin/scenario/random"`

Return to normal:
`curl -X POST "$API_URL/admin/scenario/normal"`

Generate traffic:
`for i in $(seq 1 20); do curl -s -X POST "$API_URL/payments"; echo; done`

## Configure Perses
1. Open the Perses forwarded URL on port 8080.
2. Create/open a project.
3. Add a Prometheus datasource named `FakeUPI-VictoriaMetrics`.
4. Set its server-side/proxy URL to `http://victoriametrics:8428` (the Compose service name works from inside the Compose network).
5. Save the datasource.
6. Create a dashboard and add Time Series panels using the queries below.

Useful PromQL queries:
- Request rate: `sum(rate(payment_api_requests_total[5m]))`
- HTTP 5xx rate: `sum(rate(payment_api_requests_total{status=~"5.."}[5m]))`
- Request rate by status: `sum by (status) (rate(payment_api_requests_total[5m]))`
- P95 latency by endpoint: `histogram_quantile(0.95, sum by (le, endpoint) (rate(payment_api_request_duration_seconds_bucket[5m])))`
- Payment outcomes: `sum by (result) (fake_upi_payments_total)`
- In-flight requests: `payment_api_in_flight_requests`

Note: Prometheus counters and histogram series may not appear until the corresponding endpoint has been called. Generate requests first, then wait 10–20 seconds for scraping.

## Configure Loki in Perses
1. Add a Loki datasource named `FakeUPI-Loki`.
2. Set its server-side/proxy URL to `http://loki:3100`.
3. Use the Perses Explore or dashboard query feature for the Loki datasource.
4. Example LogQL query: `{service="fake-upi-payment-api"}`.
5. To search failures: `{service="fake-upi-payment-api"} |= "payment_failed"`.

If your Perses version doesn't offer a Loki query panel or Explore view, verify the Loki datasource plugin/version and use the Loki readiness endpoint `/ready` for connectivity checks.

## L1 troubleshooting runbook
1. Record exact timestamp and time zone.
2. Check `/health` and current scenario.
3. In Perses, inspect request rate, 5xx rate, and P95 latency over the same time range.
4. In Loki, search for the incident event or `payment_id`.
5. Capture dashboard/panel names, query, time range, values, affected endpoint, and representative fake log lines.
6. State observed facts, not an unverified root cause.
7. Return the scenario to `normal` after each exercise.

## Important safety notes
- Admin scenario controls are intentionally unauthenticated for this isolated lab. Do not expose this service publicly or reuse this code in production.
- The `down` scenario simulates application endpoint failures while keeping `/metrics` available, so you can observe the distinction between app health and metrics scrape health.
- This is a teaching starter, not production-hardened software.
