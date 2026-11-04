import http from 'k6/http';
import { check, sleep } from 'k6';

// SLO Performance & Error Budget Thresholds
export const options = {
  stages: [
    { duration: '15s', target: 20 }, // Ramp-up
    { duration: '30s', target: 20 }, // Steady state production load
    { duration: '10s', target: 0 },  // Ramp-down
  ],
  thresholds: {
    // 95% of requests must complete below 300ms (SLO Latency target)
    http_req_duration: ['p(95)<300'],
    // HTTP failure rate must stay below 1% (SLO Availability target)
    http_req_failed: ['rate<0.01'],
  },
};

const BASE_URL = __ENV.API_URL || 'http://localhost:8000';

export default function () {
  // 1. Fetch item list
  const listRes = http.get(`${BASE_URL}/api/v1/items`, {
    headers: { 'X-Trace-ID': `k6-trace-${Date.now()}` },
  });

  check(listRes, {
    'list status is 200': (r) => r.status === 200,
    'response body has items': (r) => r.json().items !== undefined,
  });

  // 2. Fetch specific item
  const itemId = Math.floor(Math.random() * 15) + 1;
  const itemRes = http.get(`${BASE_URL}/api/v1/items/${itemId}`);

  check(itemRes, {
    'item status is 200': (r) => r.status === 200,
  });

  sleep(0.1);
}

