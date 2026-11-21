import { createServer } from "node:http";

const server = createServer((request, response) => {
  if (request.method !== "GET" || request.url !== "/health") {
    response.writeHead(404).end();
    return;
  }

  response.setHeader("Content-Type", "application/json");
  response.end(JSON.stringify({ status: "ok", service: "simulation" }));
});

server.listen(3001, "0.0.0.0", () => {
  console.log("Simulation lauscht auf Port 3001.");
});
