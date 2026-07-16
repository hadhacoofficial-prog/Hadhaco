// Report generator — Processes k6 JSON summary output into structured reports
// Usage: node reports/generate.js results/summary.json
// Reads: k6 --summary-export output (JSON)
// Writes: results/report.json, results/report-summary.txt

const fs = require("fs");
const path = require("path");

const inputFile = process.argv[2] || "results/summary.json";
const outputDir = path.dirname(inputFile);

function loadSummary(filePath) {
  if (!fs.existsSync(filePath)) {
    console.error(`File not found: ${filePath}`);
    process.exit(1);
  }
  return JSON.parse(fs.readFileSync(filePath, "utf-8"));
}

function fmt(ms) {
  if (ms === undefined || ms === null) return "N/A";
  if (ms < 1) return `${(ms * 1000).toFixed(0)}us`;
  if (ms < 1000) return `${ms.toFixed(1)}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

function pct(n) {
  if (n === undefined || n === null) return "N/A";
  return `${(n * 100).toFixed(2)}%`;
}

function metric(m) {
  if (!m) return null;
  // k6 metrics can be flat { avg, min, med, max, p(90), p(95), count, rate }
  // or wrapped { values: { avg, ... } }
  const v = m.values || m;
  return {
    avg: v.avg,
    min: v.min,
    med: v.med,
    max: v.max,
    p90: v["p(90)"],
    p95: v["p(95)"],
    p99: v["p(99)"],
    count: v.count,
    rate: v.rate,
    passes: v.passes,
    fails: v.fails,
    value: v.value,
  };
}

function generateReport(summary) {
  const metrics = summary.metrics || {};
  const rootGroup = summary.root_group || {};

  // --- Group-level checks ---
  const groups = {};
  if (rootGroup.groups) {
    for (const [name, group] of Object.entries(rootGroup.groups)) {
      let totalPasses = 0;
      let totalFails = 0;
      const checksList = [];
      if (group.checks) {
        for (const [checkName, check] of Object.entries(group.checks)) {
          totalPasses += check.passes || 0;
          totalFails += check.fails || 0;
          checksList.push({
            name: checkName,
            passes: check.passes || 0,
            fails: check.fails || 0,
          });
        }
      }
      groups[name] = {
        checks_total: totalPasses + totalFails,
        checks_passed: totalPasses,
        checks_failed: totalFails,
        checks: checksList,
      };
    }
  }

  // --- Build report ---
  const httpReqs = metric(metrics.http_reqs);
  const httpDuration = metric(metrics.http_req_duration);
  const httpFailed = metric(metrics.http_req_failed);
  const iters = metric(metrics.iterations);
  const checks = metric(metrics.checks);
  const status2xx = metric(metrics.status_2xx);
  const status5xx = metric(metrics.status_5xx);
  const timeouts = metric(metrics.timeouts);
  const apiSuccess = metric(metrics.api_success_rate);
  const apiErrors = metric(metrics.api_errors);

  // Endpoint-specific latency metrics
  const endpointMetrics = {};
  for (const [key, val] of Object.entries(metrics)) {
    if (key.startsWith("endpoint_")) {
      endpointMetrics[key] = metric(val);
    }
  }

  // Business metrics
  const businessMetrics = {};
  for (const [key, val] of Object.entries(metrics)) {
    if (key.startsWith("business_")) {
      businessMetrics[key] = metric(val);
    }
  }

  const report = {
    generated_at: new Date().toISOString(),
    executive_summary: {
      total_requests: httpReqs?.count || 0,
      requests_per_sec: httpReqs?.rate || 0,
      total_iterations: iters?.count || 0,
      iteration_rate: iters?.rate || 0,
      avg_response_time: httpDuration?.avg || 0,
      p90_response_time: httpDuration?.p90 || 0,
      p95_response_time: httpDuration?.p95 || 0,
      p99_response_time: httpDuration?.p99 || 0,
      max_response_time: httpDuration?.max || 0,
      http_2xx_count: status2xx?.count || 0,
      http_5xx_count: status5xx?.count || 0,
      http_5xx_rate: status5xx?.rate || 0,
      timeout_count: timeouts?.count || 0,
      timeout_rate: timeouts?.rate || 0,
      api_success_rate: apiSuccess?.value || 0,
      api_error_count: apiErrors?.count || 0,
      api_error_rate: apiErrors?.rate || 0,
      check_pass_rate: checks?.value || 0,
      checks_passed: checks?.passes || 0,
      checks_failed: checks?.fails || 0,
    },
    group_breakdown: groups,
    endpoint_latency: endpointMetrics,
    business_metrics: businessMetrics,
    raw_metrics: Object.fromEntries(
      Object.entries(metrics)
        .filter(([k]) => !k.includes("{"))
        .map(([k, v]) => [k, v.values || v])
    ),
  };

  return report;
}

function generateTextSummary(report) {
  const L = [];
  const s = report.executive_summary;
  const sep = "═".repeat(70);
  const dash = "─".repeat(70);

  L.push(sep);
  L.push("          HADHA.CO PERFORMANCE BENCHMARK REPORT");
  L.push(`          Generated: ${report.generated_at}`);
  L.push(sep);
  L.push("");

  // Executive Summary
  L.push(`─── EXECUTIVE SUMMARY ${dash.slice(22)}`);
  L.push(`  Total Requests:         ${s.total_requests}`);
  L.push(`  Requests/sec:           ${s.requests_per_sec.toFixed(2)}`);
  L.push(`  Total Iterations:       ${s.total_iterations}`);
  L.push(`  Iterations/sec:         ${s.iteration_rate.toFixed(2)}`);
  L.push(`  Avg Response Time:      ${fmt(s.avg_response_time)}`);
  L.push(`  P90 Response Time:      ${fmt(s.p90_response_time)}`);
  L.push(`  P95 Response Time:      ${fmt(s.p95_response_time)}`);
  L.push(`  P99 Response Time:      ${fmt(s.p99_response_time)}`);
  L.push(`  Max Response Time:      ${fmt(s.max_response_time)}`);
  L.push(`  HTTP 2xx Count:         ${s.http_2xx_count}`);
  L.push(`  HTTP 5xx Count:         ${s.http_5xx_count}`);
  L.push(`  Timeout Count:          ${s.timeout_count} (${(s.timeout_rate * 100).toFixed(1)}%)`);
  L.push(`  API Success Rate:       ${pct(s.api_success_rate)}`);
  L.push(`  API Error Count:        ${s.api_error_count}`);
  L.push(`  Check Pass Rate:        ${pct(s.check_pass_rate)}`);
  L.push(`  Checks Passed:          ${s.checks_passed}`);
  L.push(`  Checks Failed:          ${s.checks_failed}`);
  L.push("");

  // Group Breakdown
  const groups = report.group_breakdown;
  if (Object.keys(groups).length > 0) {
    L.push(`─── GROUP BREAKDOWN ${dash.slice(20)}`);
    L.push(`  ${"Group".padEnd(35)} ${"Passed".padEnd(8)} ${"Failed".padEnd(8)} ${"Rate".padEnd(8)}`);
    L.push(`  ${"─".repeat(59)}`);
    for (const [name, g] of Object.entries(groups)) {
      const rate = g.checks_total > 0 ? ((g.checks_passed / g.checks_total) * 100).toFixed(1) : "0.0";
      L.push(`  ${name.padEnd(35)} ${String(g.checks_passed).padEnd(8)} ${String(g.checks_failed).padEnd(8)} ${rate}%`);
    }
    L.push("");
  }

  // Endpoint Latency
  const endpoints = report.endpoint_latency;
  if (Object.keys(endpoints).length > 0) {
    L.push(`─── ENDPOINT LATENCY (p95) ${dash.slice(27)}`);
    L.push(`  ${"Endpoint".padEnd(35)} ${"Avg".padEnd(10)} ${"P95".padEnd(10)} ${"Max".padEnd(10)}`);
    L.push(`  ${"─".repeat(65)}`);
    const sorted = Object.entries(endpoints).sort((a, b) => (b[1]?.p95 || 0) - (a[1]?.p95 || 0));
    for (const [name, e] of sorted) {
      const label = name.replace("endpoint_", "");
      L.push(`  ${label.padEnd(35)} ${fmt(e.avg).padEnd(10)} ${fmt(e.p95).padEnd(10)} ${fmt(e.max).padEnd(10)}`);
    }
    L.push("");
  }

  // Business Metrics
  const biz = report.business_metrics;
  if (Object.keys(biz).length > 0) {
    L.push(`─── BUSINESS METRICS ${dash.slice(21)}`);
    for (const [name, b] of Object.entries(biz)) {
      const label = name.replace("business_", "");
      const rate = b.value !== undefined ? pct(b.value) : "N/A";
      const detail = b.passes !== undefined ? ` (${b.passes} pass, ${b.fails} fail)` : "";
      L.push(`  ${label.padEnd(35)} ${rate}${detail}`);
    }
    L.push("");
  }

  // Bottleneck Indicators
  L.push(`─── BOTTLENECK INDICATORS ${dash.slice(26)}`);
  if (s.timeout_count > 0) {
    L.push(`  ⚠  ${s.timeout_count} request timeouts (${(s.timeout_rate * 100).toFixed(1)}%) — connection pool or DB saturation likely`);
  }
  if (s.http_5xx_count > 0) {
    L.push(`  ⚠  ${s.http_5xx_count} server errors (5xx) — backend degradation under load`);
  }
  if (s.p95_response_time > 5000) {
    L.push(`  ⚠  P95 latency ${fmt(s.p95_response_time)} exceeds 5s — poor user experience`);
  }
  if (s.avg_response_time > 2000) {
    L.push(`  ⚠  Average latency ${fmt(s.avg_response_time)} exceeds 2s — system bottleneck`);
  }
  if (s.timeout_count === 0 && s.http_5xx_count === 0 && s.p95_response_time < 2000) {
    L.push(`  ✅  No critical bottlenecks detected`);
  }
  L.push("");

  L.push(sep);
  L.push("  Thresholds: See k6 output for pass/fail status");
  L.push(sep);

  return L.join("\n");
}

// Main
try {
  const summary = loadSummary(inputFile);
  const report = generateReport(summary);
  const textSummary = generateTextSummary(report);

  const jsonOut = path.join(outputDir, "report.json");
  const txtOut = path.join(outputDir, "report-summary.txt");

  fs.writeFileSync(jsonOut, JSON.stringify(report, null, 2));
  fs.writeFileSync(txtOut, textSummary);

  console.log(textSummary);
  console.log(`\nJSON report: ${jsonOut}`);
  console.log(`Text report: ${txtOut}`);
} catch (err) {
  console.error("Report generation failed:", err.message);
  process.exit(1);
}
