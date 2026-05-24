/** @type {import('next').NextConfig} */
const nextConfig = {
  // Silence the anonymous telemetry banner in CI / new installs
  env: {
    NEXT_TELEMETRY_DISABLED: "1",
  },
};

export default nextConfig;
