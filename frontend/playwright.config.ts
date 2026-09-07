import { defineConfig, devices } from "@playwright/test";

const port = Number(process.env.JOBLOOKUP_UI_PORT || 8801);

export default defineConfig({
  testDir: "./tests",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: {
    command: "..\\.venv\\Scripts\\python.exe ..\\scripts\\serve-ui-fixture.py",
    url: `http://127.0.0.1:${port}/api/workspace`,
    reuseExistingServer: false,
    timeout: 30000,
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1440, height: 1000 },
      },
    },
  ],
});
