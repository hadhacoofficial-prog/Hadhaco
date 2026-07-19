const { io } = require("socket.io-client");

const socket = io("http://hadha-uptime-kuma:3001", { 
  transports: ["polling", "websocket"],
  reconnection: false
});

function makeMonitor(name, url, interval) {
  return {
    type: "http",
    name,
    url,
    interval: interval || 60,
    retryInterval: 30,
    maxretries: 3,
    accepted_statuscodes: ["200-299"],
    notificationIDList: [],
    conditions: [],
    active: true,
  };
}

const monitors = [
  makeMonitor("Hadha Storefront", "http://hadha-storefront:8080", 60),
  makeMonitor("Hadha Admin Panel", "http://hadha-admin:8081", 60),
  makeMonitor("Hadha API", "http://hadha-backend:8000/docs", 60),
  makeMonitor("Hadha API Health", "http://hadha-backend:8000/api/v1/health", 60),
  makeMonitor("Grafana Dashboard", "http://hadha-grafana:3000/api/health", 120),
  makeMonitor("Redis Commander", "http://hadha-redis-commander:8081", 120),
  makeMonitor("Prometheus", "http://hadha-prometheus:9090/-/healthy", 120),
  makeMonitor("GlitchTip", "http://hadha-glitchtip:8000/_health/", 120),
];

socket.on("connect", () => {
  console.log("Connected!");
  socket.emit("login", { username: "admin-uptime", password: "hadha2026@admin-uptime" }, (res) => {
    if (res.ok) {
      console.log("Logged in! Adding monitors...");
      addMonitors();
    } else {
      console.error("Login failed:", res.msg);
      process.exit(1);
    }
  });
});

function addMonitors() {
  let pending = monitors.length;
  monitors.forEach((monitor, i) => {
    setTimeout(() => {
      console.log(`Adding ${i + 1}/${monitors.length}: ${monitor.name}`);
      socket.emit("add", monitor, (res) => {
        console.log(`  ok=${res.ok} msg=${res.msg || ""} id=${res.monitorID || ""}`);
        pending--;
        if (pending === 0) {
          console.log("\nAll submitted! Waiting for checks...");
          setTimeout(() => process.exit(0), 5000);
        }
      });
    }, i * 2000);
  });
}

socket.on("connect_error", (err) => console.error("Error:", err.message));
setTimeout(() => { console.log("Timeout"); process.exit(1); }, 60000);
