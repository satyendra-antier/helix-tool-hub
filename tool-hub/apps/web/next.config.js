const path = require("path");

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  outputFileTracingRoot: path.join(__dirname, "../../"),
  transpilePackages: [
    "@tool-hub/shared-types",
    "@tool-hub/video-scraper-frontend",
    "@tool-hub/market-depth-frontend",
    "@tool-hub/lead-intelligence-frontend",
    "@tool-hub/build-readiness-frontend",
    "@tool-hub/growth-pillars-frontend",
    "@tool-hub/outreach-autopilot-frontend",
  ],
};

module.exports = nextConfig;
