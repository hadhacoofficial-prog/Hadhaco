// Master runner — Executes all k6 test suites and generates a unified report
// Usage: node reports/run-all.js [--suite smoke|feature|performance|stress|all]

const { execSync } = require("child_process");
const fs = require("fs");
const path = require("path");

const K6 = process.platform === "win32"
  ? "C:\\Users\\Admin\\AppData\\Local\\Temp\\k6.exe"
  : "k6";

const BASE_DIR = path.resolve(__dirname, "..");
const RESULTS_DIR = path.join(BASE_DIR, "results");

const SUITES = {
  smoke: [
    { name: "smoke-full-suite", file: "smoke/full-suite.js", vus: 2, duration: "1m" },
  ],
  feature: [
    { name: "catalog-products", file: "catalog/products.js", vus: 5, duration: "2m" },
    { name: "catalog-variants", file: "catalog/product-variants.js", vus: 5, duration: "2m" },
    { name: "search", file: "search/search.js", vus: 5, duration: "2m" },
    { name: "cart", file: "cart/cart.js", vus: 5, duration: "2m" },
    { name: "cart-complete", file: "cart/cart-complete.js", vus: 5, duration: "2m" },
    { name: "checkout", file: "checkout/checkout.js", vus: 3, duration: "2m" },
    { name: "checkout-complete", file: "checkout/checkout-complete.js", vus: 3, duration: "2m" },
    { name: "auth-complete", file: "auth/auth-complete.js", vus: 3, duration: "2m" },
    { name: "orders-complete", file: "orders/orders-complete.js", vus: 3, duration: "2m" },
    { name: "coupons", file: "coupons/coupons.js", vus: 5, duration: "2m" },
    { name: "inventory-management", file: "inventory/inventory-management.js", vus: 5, duration: "2m" },
    { name: "notifications", file: "notifications/notifications.js", vus: 2, duration: "1m" },
  ],
  performance: [
    { name: "benchmark", file: "performance/benchmark.js", vus: 0, duration: "" },
  ],
  stress: [
    { name: "stress-full", file: "stress/full-suite.js", vus: 0, duration: "" },
    { name: "spike-flash", file: "spike/flash-sale.js", vus: 0, duration: "" },
  ],
  journeys: [
    { name: "full-purchase", file: "journeys/full-purchase.js", vus: 3, duration: "3m" },
  ],
};

function runSuite(suiteName) {
  const suite = SUITES[suiteName];
  if (!suite) {
    console.error(`Unknown suite: ${suiteName}`);
    console.log(`Available: ${Object.keys(SUITES).join(", ")}, all`);
    process.exit(1);
  }

  const results = [];

  for (const test of suite) {
    const outFile = path.join(RESULTS_DIR, `${test.name}-summary.json`);
    const outFileFlag = `--summary-export=${outFile}`;
    let cmd = `"${K6}" run ${outFileFlag}`;

    if (test.vus > 0) cmd += ` --vus ${test.vus}`;
    if (test.duration) cmd += ` --duration ${test.duration}`;

    cmd += ` "${path.join(BASE_DIR, test.file)}"`;

    console.log(`\n▶ Running: ${test.name}`);
    console.log(`  Command: ${cmd}`);

    try {
      const output = execSync(cmd, {
        encoding: "utf-8",
        timeout: 30 * 60 * 1000,
        cwd: BASE_DIR,
        stdio: ["pipe", "pipe", "pipe"],
      });

      results.push({ name: test.name, status: "PASS", output: output.slice(-2000) });
      console.log(`  ✅ ${test.name} — PASS`);
    } catch (err) {
      const output = err.stdout ? err.stdout.slice(-2000) : err.message;
      results.push({ name: test.name, status: "FAIL", output });
      console.log(`  ❌ ${test.name} — FAIL (exit code ${err.status})`);
    }
  }

  return results;
}

function generateUnifiedReport(allResults) {
  const lines = [];
  lines.push("═══════════════════════════════════════════════════════════════");
  lines.push("          HADHA.CO — COMPLETE TEST SUITE RESULTS");
  lines.push(`          Generated: ${new Date().toISOString()}`);
  lines.push("═══════════════════════════════════════════════════════════════\n");

  let totalPass = 0;
  let totalFail = 0;

  for (const [suiteName, results] of Object.entries(allResults)) {
    lines.push(`─── ${suiteName.toUpperCase()} ───────────────────────────────────────`);
    for (const r of results) {
      const icon = r.status === "PASS" ? "✅" : "❌";
      lines.push(`  ${icon} ${r.name.padEnd(30)} ${r.status}`);
      if (r.status === "PASS") totalPass++;
      else totalFail++;
    }
    lines.push("");
  }

  lines.push("═══════════════════════════════════════════════════════════════");
  lines.push(`  TOTAL: ${totalPass + totalFail} suites | ✅ ${totalPass} passed | ❌ ${totalFail} failed`);
  lines.push("═══════════════════════════════════════════════════════════════");

  return lines.join("\n");
}

// Main
const suiteArg = process.argv[2] || "all";

if (!fs.existsSync(RESULTS_DIR)) {
  fs.mkdirSync(RESULTS_DIR, { recursive: true });
}

const allResults = {};
if (suiteArg === "all") {
  for (const suiteName of Object.keys(SUITES)) {
    allResults[suiteName] = runSuite(suiteName);
  }
} else {
  allResults[suiteArg] = runSuite(suiteArg);
}

const report = generateUnifiedReport(allResults);
console.log("\n" + report);

const reportFile = path.join(RESULTS_DIR, "full-run-report.txt");
fs.writeFileSync(reportFile, report);
console.log(`\nReport saved: ${reportFile}`);
