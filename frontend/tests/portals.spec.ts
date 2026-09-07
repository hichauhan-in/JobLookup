import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import type { Portal, Portals } from "../src/types";

const linkedin: Portal = {
  key: "linkedin",
  name: "LinkedIn",
  tier: "b",
  enabled: false,
  ready: false,
  requires_key: false,
  blocked_reason: "Sign in to LinkedIn to verify a browser session.",
  homepage: "https://www.linkedin.com",
  login_url: "https://www.linkedin.com/login",
  search_url:
    "https://www.linkedin.com/jobs/search/?keywords=Python&location=India",
  description: "Job portal",
  last_status: "",
  last_error: "",
  last_count: 0,
  last_run_at: "",
  config: {},
  fields: [],
  guide: {},
  risk_ack: false,
  access_mode: "session",
  public_supported: true,
  session: { authenticated: false },
};

async function mockPortals(
  page: Page,
  options: {
    enabled?: boolean;
    browserReady?: boolean;
    authenticated?: boolean;
  } = {},
) {
  const payload: Portals = {
    portals: [
      { ...linkedin, session: { authenticated: !!options.authenticated } },
    ],
    enabled: !!options.enabled,
    local_only: true,
    browser: {
      installed: true,
      browser_ready: options.browserReady ?? true,
      detail: "Chromium is not installed.",
    },
    risk_notice:
      "LinkedIn restricts automated access. Signing in does not grant permission to automate. Session cookies remain on this device.",
  };
  const writes: { path: string; body: Record<string, unknown> }[] = [];
  const signins: string[] = [];
  await page.route("**/api/portals", async (route) => {
    if (route.request().method() === "PUT") {
      const body = route.request().postDataJSON();
      writes.push({ path: "/portals", body });
      payload.enabled = body.enabled;
      await route.fulfill({ json: { enabled: payload.enabled } });
    } else await route.fulfill({ json: payload });
  });
  await page.route("**/api/portals/linkedin", async (route) => {
    const body = route.request().postDataJSON();
    writes.push({ path: "/portals/linkedin", body });
    payload.portals[0] = {
      ...payload.portals[0],
      enabled: body.enabled,
      risk_ack: body.acknowledged,
      access_mode: body.access_mode,
      ready: body.access_mode === "public" || !!options.authenticated,
    };
    await route.fulfill({
      json: { enabled: body.enabled, access_mode: body.access_mode },
    });
  });
  await page.route("**/api/sources/linkedin/signin", async (route) => {
    signins.push(route.request().method());
    await route.fulfill({ json: { task: { id: "portal-signin-test" } } });
  });
  await page.route("**/api/tasks/portal-signin-test", (route) =>
    route.fulfill({
      json: {
        task: {
          id: "portal-signin-test",
          kind: "sign-in",
          status: "running",
          label: "Sign in to LinkedIn",
          message: "Opening sign-in",
        },
        result: {},
        error: "",
      },
    }),
  );
  return { payload, writes, signins };
}

async function showPortals(page: Page) {
  await page.goto("/#/settings?tab=sources");
  await page
    .getByRole("combobox", { name: "Source type" })
    .selectOption("portals");
  await expect(
    page.getByRole("heading", { name: "Job portals", exact: true }),
  ).toBeVisible();
}

test("all portal connectors are visible without starting a browser", async ({
  page,
}) => {
  await showPortals(page);
  await expect(page.locator(".portal-row")).toHaveCount(9);
  await expect(
    page.getByRole("heading", { name: "LinkedIn", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Naukri", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("switch", { name: "Enable portal access", exact: true }),
  ).not.toBeChecked();
  await expect(
    page
      .locator(".portal-row")
      .filter({ hasText: "LinkedIn" })
      .getByRole("button", { name: "Sign in", exact: true }),
  ).toBeDisabled();
});

test("portal enable and sign-in require explicit consent", async ({ page }) => {
  const fixture = await mockPortals(page);
  await showPortals(page);
  await page
    .getByRole("switch", { name: "Enable portal access", exact: true })
    .click();
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  expect(fixture.writes).toHaveLength(0);
  await page
    .getByRole("switch", { name: "Enable portal access", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Enable portal access", exact: true })
    .click();
  await expect(
    page.getByRole("switch", { name: "Enable portal access", exact: true }),
  ).toBeChecked();
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Save & sign in" }),
  ).toBeDisabled();
  await expect(page.locator("input[type=password]")).toHaveCount(0);
  await page
    .getByRole("checkbox", { name: /I understand the restrictions/ })
    .check();
  await page.getByRole("button", { name: "Save & sign in" }).click();
  await expect.poll(() => fixture.signins.length).toBe(1);
  expect(fixture.writes.at(-1)?.body).toMatchObject({
    access_mode: "session",
    acknowledged: true,
    enabled: true,
  });
  await expect(
    page.getByText(/Complete sign-in and any verification/),
  ).toBeVisible();
});

test("public mode enables without launching sign-in", async ({ page }) => {
  const fixture = await mockPortals(page, {
    enabled: true,
    browserReady: false,
  });
  await showPortals(page);
  await page.getByRole("button", { name: "Try without sign-in" }).click();
  await expect(page.getByRole("combobox", { name: "Access mode" })).toHaveValue(
    "public",
  );
  await page
    .getByRole("checkbox", { name: /I understand the restrictions/ })
    .check();
  await page
    .getByRole("button", { name: "Enable public access", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  expect(fixture.signins).toHaveLength(0);
  expect(fixture.writes.at(-1)?.body).toMatchObject({
    access_mode: "public",
    acknowledged: true,
  });
  await expect(page.getByText("Public listings · best effort")).toBeVisible();
});

test("missing browser support has an explicit setup action", async ({
  page,
}) => {
  await mockPortals(page, { enabled: true, browserReady: false });
  await showPortals(page);
  await expect(
    page.getByRole("button", { name: "Install browser support" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page
    .getByRole("checkbox", { name: /I understand the restrictions/ })
    .check();
  await expect(
    page.getByRole("button", { name: "Save & sign in" }),
  ).toBeDisabled();
});

test("manual portal import works with portal access off", async ({ page }) => {
  await showPortals(page);
  await page
    .locator(".portal-row")
    .filter({ hasText: "LinkedIn" })
    .getByRole("button", { name: "Import job", exact: true })
    .click();
  await page
    .getByRole("textbox", { name: "Original posting URL" })
    .fill("https://www.linkedin.com/jobs/view/987654321");
  await page
    .getByRole("textbox", { name: "Job title", exact: true })
    .fill("Technical Support Engineer");
  await page
    .getByRole("textbox", { name: "Company", exact: true })
    .fill("Portal Import Fixture");
  await page
    .getByRole("textbox", { name: "Job description" })
    .fill(
      "Support Microsoft 365, SharePoint and Azure customers. Use Python and Networking to troubleshoot complex enterprise incidents and document the resolutions.",
    );
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Import job", exact: true })
    .click();
  await expect(page.getByText("Job imported", { exact: true })).toBeVisible();
  await page.getByRole("link", { name: "View match", exact: true }).click();
  await expect(
    page.getByRole("dialog", { name: "Opportunity details" }),
  ).toContainText("Portal Import Fixture");
  await expect(page.getByRole("dialog")).toContainText("Needs review");
  const response = await page.request.get(
    "/api/opportunities?view=all&query=Portal%20Import%20Fixture",
  );
  const payload = await response.json();
  expect(payload.items[0].source_keys).toContain("linkedin");
  await page.keyboard.press("Escape");
  await page.request.post(`/api/jobs/${payload.items[0].id}/hide?hidden=true`);
});

test("disconnect clears the local session with confirmation", async ({
  page,
}) => {
  await mockPortals(page, { enabled: true, authenticated: true });
  let deleted = false;
  await page.route("**/api/portals/linkedin/session", async (route) => {
    deleted = route.request().method() === "DELETE";
    await route.fulfill({ json: { disconnected: true } });
  });
  await showPortals(page);
  await page.getByRole("button", { name: "Disconnect LinkedIn" }).click();
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  expect(deleted).toBe(false);
  await page.getByRole("button", { name: "Disconnect LinkedIn" }).click();
  await page.getByRole("button", { name: "Disconnect", exact: true }).click();
  await expect.poll(() => deleted).toBe(true);
});

test("portal controls and sign-in dialog are responsive and accessible", async ({
  page,
}, testInfo) => {
  await mockPortals(page, { enabled: true });
  await page.emulateMedia({ reducedMotion: "reduce" });
  for (const viewport of [
    { width: 1440, height: 1000 },
    { width: 390, height: 844 },
  ]) {
    await page.setViewportSize(viewport);
    await showPortals(page);
    await page.evaluate(() => document.fonts.ready);
    const report = await new AxeBuilder({ page })
      .include(".portal-section")
      .withTags(["wcag2a", "wcag2aa"])
      .analyze();
    expect(report.violations).toEqual([]);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    const dialog = await new AxeBuilder({ page })
      .include("dialog")
      .withTags(["wcag2a", "wcag2aa"])
      .analyze();
    expect(dialog.violations).toEqual([]);
    await page.screenshot({
      path: testInfo.outputPath(`portal-signin-${viewport.width}.png`),
    });
    await page.keyboard.press("Escape");
  }
});
