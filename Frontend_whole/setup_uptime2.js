const { io } = require("socket.io-client");

console.log("Connecting...");
const socket = io("http://hadha-uptime-kuma:3001", { 
  transports: ["polling", "websocket"],
  reconnection: false
});

socket.onAny((eventName, ...args) => {
  console.log(`EVENT: ${eventName}`, JSON.stringify(args).substring(0, 300));
});

socket.on("connect", () => {
  console.log("Connected! ID:", socket.id);
  console.log("Emitting login...");
  socket.emit("login", { username: "admin-uptime", password: "hadha2026@admin-uptime" });
});

socket.on("connect_error", (err) => {
  console.error("Connection error:", err.message);
});

socket.on("disconnect", (reason) => {
  console.log("Disconnected:", reason);
});

setTimeout(() => {
  console.log("Timeout, exiting");
  process.exit(0);
}, 15000);
