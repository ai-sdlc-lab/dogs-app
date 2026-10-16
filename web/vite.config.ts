import { defineConfig } from "vite";

// `npm run dev` proxies the API to a local uvicorn (make run-api).
export default defineConfig({
  server: { proxy: { "/api": "http://127.0.0.1:8080" } },
});
