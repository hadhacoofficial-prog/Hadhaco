const { io } = require("socket.io-client");

const socket = io("http://hadha-uptime-kuma:3001", { 
  transports: ["polling", "websocket"],
  reconnection: false
});

const monitors = [
  { type: "http", name: "Hadha Storefront", url: "http://hadha-storefront:8080", interval: 60, retryInterval: 30, maxretries: 3, accepted_statuscodes: ["200-299", "300-399"], notificationIDList: [] },
  { type: "http", name: "Hadha Admin Panel", url: "http://hadha-admin:8081", interval: 60, retryInterval: 30, maxretries: 3, accepted_statuscodes: ["200-299", "300-399"], notificationIDList: [] },
  { type: "http", name: "Hadha API", url: "http://hadha-backend:8000/docs", interval: 60, retryInterval: 30, maxretries: 3, accepted_statuscodes: ["200-299"], notificationIDList: [] },
  { type: "http", name: "Hadha API Health", url: "http://hadha-backend:8000/api/v1/health", interval: 60, retryInterval: 30, maxretries: 3, accepted_statuscodes: ["200-299"], notificationIDList: [] },
  { type: "http", name: "Grafana Dashboard", url: "http://hadha-grafana:3000/api/health", interval: 120, retryInterval: 60, maxretries: 3, accepted_statuscodes: ["200-299"], notificationIDList: [] },
  { type: "http", name: "Redis Commander", url: "http://hadha-redis-commander:8081", interval: 120, retryInterval: 60, maxretries: 3, accepted_statuscodes: ["200-399"], notificationIDList: [] },
  { type: "http", name: "Prometheus", url: "http://hadha-prometheus:9090/-/healthy", interval: 120, retryInterval: 60, maxretries: 3, accepted_statuscodes: ["200-299"], notificationIDList: [] },
  { type: "http", name: "GlitchTip", url: "http://hadha-glitchtip:8000/_health/", interval: 120, retryInterval: 60, maxretries: 3, accepted_statuscodes: ["200-299"], notificationIDList: [] },
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
      socket.emit("add", { monitor }, (res) => {
        console.log(`  ok=${res.ok} msg=${res.msg || ""} id=${res.monitorID || ""}`);
        pending--;
        if (pending === 0) {
          console.log("\nDone! Getting final monitor list...");
          setTimeout(() => {
            socket.emit("getMonitorList", {}, (list) => {
              if (list && list.monitorList) {
                const ml = Object.values(list.monitorList);
                console.log(`\n=== ${ml.length} Monitors in Uptime Kuma ===`);
                ml.forEach(m => console.log(`  - ${m.name} | ${m.url} | status: ${m.status}`));
              }
              process.exit(0);
            });
          }, 3000);
        }
      });
    }, i * 2000);
  });
}

socket.on("connect_error", (err) => console.error("Error:", err.message));

setTimeout(() => { console.log("Timeout"); process.exit(1); }, 60000);
