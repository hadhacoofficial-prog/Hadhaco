const { io } = require("socket.io-client");

const socket = io("http://hadha-uptime-kuma:3001", { transports: ["websocket", "polling"] });

const monitors = [
  { type: "http", name: "Hadha Storefront", url: "http://hadha-storefront:8080", interval: 60, retryInterval: 30, maxretries: 3, accepted_statuscodes: ["200-299", "300-399"] },
  { type: "http", name: "Hadha Admin Panel", url: "http://hadha-admin:8081", interval: 60, retryInterval: 30, maxretries: 3, accepted_statuscodes: ["200-299", "300-399"] },
  { type: "http", name: "Hadha API", url: "http://hadha-backend:8000/docs", interval: 60, retryInterval: 30, maxretries: 3, accepted_statuscodes: ["200-299"] },
  { type: "http", name: "Hadha API Health", url: "http://hadha-backend:8000/api/v1/health", interval: 60, retryInterval: 30, maxretries: 3, accepted_statuscodes: ["200-299"] },
  { type: "http", name: "Grafana Dashboard", url: "http://hadha-grafana:3000/api/health", interval: 120, retryInterval: 60, maxretries: 3, accepted_statuscodes: ["200-299"] },
  { type: "http", name: "Redis Commander", url: "http://hadha-redis-commander:8081", interval: 120, retryInterval: 60, maxretries: 3, accepted_statuscodes: ["200-399"] },
  { type: "http", name: "Prometheus", url: "http://hadha-prometheus:9090/-/healthy", interval: 120, retryInterval: 60, maxretries: 3, accepted_statuscodes: ["200-299"] },
  { type: "http", name: "GlitchTip", url: "http://hadha-glitchtip:8000/_health/", interval: 120, retryInterval: 60, maxretries: 3, accepted_statuscodes: ["200-299"] },
];

let added = 0;

socket.on("connect", () => {
  console.log("Connected to Uptime Kuma");
  socket.emit("login", { username: "admin-uptime", password: "hadha2026@admin-uptime" });
});

socket.on("login", (data) => {
  if (data.ok) {
    console.log("Logged in! Adding monitors...");
    addNext(0);
  } else {
    console.log("Login failed:", data.msg);
    process.exit(1);
  }
});

socket.on("add", (data) => {
  if (data.ok) {
    added++;
    console.log(`  [${added}/${monitors.length}] Added: ${data.monitor?.name || "unknown"} (id: ${data.monitorID})`);
  } else {
    console.log(`  Add failed: ${data.msg}`);
  }
});

socket.on("connect_error", (err) => {
  console.error("Connection error:", err.message);
});

function addNext(index) {
  if (index >= monitors.length) {
    console.log(`\nAll ${monitors.length} monitors submitted. Waiting for confirmations...`);
    setTimeout(() => {
      console.log(`Confirmed: ${added}/${monitors.length}`);
      socket.emit("getMonitorList");
      setTimeout(() => process.exit(0), 3000);
    }, 5000);
    return;
  }
  console.log(`Adding ${index + 1}/${monitors.length}: ${monitors[index].name}`);
  socket.emit("add", { monitor: monitors[index], type: "http" });
  setTimeout(() => addNext(index + 1), 1500);
}

socket.on("getMonitorList", (data) => {
  if (data && data.monitorList) {
    const list = Object.values(data.monitorList);
    console.log(`\nMonitors in Uptime Kuma: ${list.length}`);
    list.forEach((m) => console.log(`  - ${m.name} | ${m.url} | status: ${m.status}`));
  }
});

setTimeout(() => {
  console.log("Timeout reached, exiting...");
  process.exit(1);
}, 30000);
