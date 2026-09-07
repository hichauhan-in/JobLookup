import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test.describe.configure({ mode: "serial" });

test("matches explain fit, uncertainty, and exclusions", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/#/matches");
  await expect(
    page.getByRole("heading", { name: "Your matches", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".job-card")).toHaveCount(4);
  await expect(
    page.getByRole("button", { name: /Needs review 1/ }),
  ).toBeVisible();
  await page
    .locator(".job-card")
    .filter({ hasText: "Northstar" })
    .getByRole("button", { name: "View match" })
    .click();
  await page.getByRole("button", { name: "Fit evidence", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Your fit breakdown" }),
  ).toBeVisible();
  await expect(page.locator(".criterion")).toHaveCount(5);
  await expect(page.locator(".evidence-item")).toHaveCount(5);
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.getByRole("button", { name: /Needs review 1/ }).click();
  await expect(page.locator(".job-card")).toHaveCount(1);
  await expect(page.locator(".job-card")).toContainText("Fieldwork");
  await page.getByRole("button", { name: /All postings 7/ }).click();
  await expect(page.locator(".job-card")).toHaveCount(7);
  await expect(
    page.locator(".job-card").filter({ hasText: "Meridian" }),
  ).toContainText("Outside preferences");
  await expect(
    page.locator(".job-card").filter({ hasText: "Ledger" }),
  ).toContainText("Outside preferences");
  expect(errors).toEqual([]);
});

test("search and filters have stable results", async ({ page }) => {
  await page.goto("/#/matches");
  await expect(page.locator(".job-card")).toHaveCount(4);
  await page.getByRole("textbox", { name: "Search matches" }).fill("Cloudline");
  await expect(page.locator(".job-card")).toHaveCount(1);
  await page.getByRole("button", { name: "Clear search" }).click();
  await expect(page.locator(".job-card")).toHaveCount(4);
  await page
    .getByRole("combobox", { name: "Work arrangement" })
    .selectOption("hybrid");
  await expect(page.locator(".job-card")).toHaveCount(1);
  await expect(page.locator(".job-card")).toContainText("Cloudline");
});

test("save, change status, add notes, and remove without deleting a posting", async ({
  page,
}) => {
  await page.goto("/#/matches");
  const orbit = page.locator(".job-card").filter({ hasText: "Orbit" });
  await orbit
    .getByRole("button", { name: "Save Customer Success Engineer" })
    .click();
  await page.getByRole("link", { name: /^Applications/ }).click();
  const application = page
    .locator(".application-row")
    .filter({ hasText: "Orbit" });
  await expect(application).toBeVisible();
  await application.getByRole("combobox").selectOption("considering");
  await expect(application.getByRole("combobox")).toHaveValue("considering");
  await application
    .getByRole("button", { name: "Notes for Customer Success Engineer" })
    .click();
  await page
    .getByRole("textbox", { name: "Notes", exact: true })
    .fill("Check the support rotation before applying.");
  await page.getByRole("button", { name: "Save notes" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await application
    .getByRole("button", { name: "Notes for Customer Success Engineer" })
    .click();
  await expect(
    page.getByRole("textbox", { name: "Notes", exact: true }),
  ).toHaveValue("Check the support rotation before applying.");
  await page.keyboard.press("Escape");
  await application
    .getByRole("button", {
      name: "Remove Customer Success Engineer",
      exact: true,
    })
    .click();
  await page
    .getByRole("button", { name: "Remove application", exact: true })
    .click();
  await expect(application).toHaveCount(0);
  await page.getByRole("link", { name: "Matches", exact: true }).click();
  await expect(
    page.locator(".job-card").filter({ hasText: "Orbit" }),
  ).toBeVisible();
});

test("hidden jobs can be restored", async ({ page }) => {
  await page.goto("/#/matches");
  const bright = page.locator(".job-card").filter({ hasText: "Brightside" });
  await bright
    .getByRole("button", { name: "Hide Technical Support Engineer" })
    .click();
  await expect(bright).toHaveCount(0);
  await page.getByRole("button", { name: "Hidden jobs", exact: true }).click();
  await expect(bright).toBeVisible();
  await bright
    .getByRole("button", { name: "Restore Technical Support Engineer" })
    .click();
  await expect(bright).toHaveCount(0);
});

test("manual profile works without an AI connection", async ({ page }) => {
  await page.goto("/#/profile");
  await page
    .getByRole("textbox", { name: "Professional headline", exact: true })
    .fill("Enterprise Support Engineer");
  await page
    .getByRole("button", { name: "Save profile", exact: true })
    .first()
    .click();
  await expect(
    page.getByRole("textbox", { name: "Professional headline", exact: true }),
  ).toHaveValue("Enterprise Support Engineer");
  await page.reload();
  await expect(
    page.getByRole("textbox", { name: "Professional headline", exact: true }),
  ).toHaveValue("Enterprise Support Engineer");
  await page
    .getByRole("textbox", { name: "Target roles", exact: true })
    .fill("Cloud Support Engineer");
  await page
    .getByRole("textbox", { name: "Target roles", exact: true })
    .press("Enter");
  await page
    .getByRole("button", { name: "Save profile", exact: true })
    .first()
    .click();
  await expect(
    page.getByRole("button", { name: "Remove Cloud Support Engineer" }),
  ).toBeVisible();
});

test("resume upload extracts locally and can be removed", async ({ page }) => {
  await page.goto("/#/profile");
  await page.getByLabel("Upload resume or portfolio").setInputFiles({
    name: "test-resume.txt",
    mimeType: "text/plain",
    buffer: Buffer.from(
      "Alex Morgan\nTechnical Support Engineer\n5 years of experience with Python, Microsoft 365, SharePoint, Azure, and Networking.\nExperienced in enterprise troubleshooting and customer support.\nResolved cloud incidents, documented root causes, and automated repetitive support tasks for enterprise customers.",
    ),
  });
  await expect(
    page.locator(".document-item").filter({ hasText: "test-resume" }),
  ).toBeVisible();
  await expect(
    page.locator(".document-item").filter({ hasText: "test-resume" }),
  ).toContainText("Ready", { timeout: 15000 });
  await page
    .getByRole("button", { name: "Remove test-resume", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Remove document", exact: true })
    .click();
  await expect(page.locator(".document-item")).toHaveCount(0);
});

test("profile navigation protects unsaved edits", async ({ page }) => {
  await page.goto("/#/profile");
  await page
    .getByRole("textbox", { name: "Professional headline", exact: true })
    .fill("An unsaved edit");
  await page.getByRole("link", { name: "Matches", exact: true }).click();
  await expect(
    page.getByRole("dialog", { name: "Discard unsaved changes?" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(
    page.getByRole("textbox", { name: "Professional headline", exact: true }),
  ).toHaveValue("An unsaved edit");
  await page.getByRole("link", { name: "Matches", exact: true }).click();
  await page
    .getByRole("button", { name: "Discard changes", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Your matches", exact: true }),
  ).toBeVisible();
});

test("public-source settings and history are usable", async ({ page }) => {
  await page.goto("/#/settings?tab=sources");
  await expect(
    page.getByRole("heading", { name: "Job sources", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("textbox", { name: "Search sources" })
    .fill("Greenhouse");
  await expect(page.locator(".source-row")).toHaveCount(1);
  await page.getByRole("button", { name: /Configure Greenhouse/ }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(
    page.getByRole("textbox", { name: "Companies to watch" }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  await page
    .getByRole("button", { name: "Search history", exact: true })
    .click();
  await expect(page.locator(".history-entry")).toHaveCount(1);
  await page.getByText("Source report", { exact: true }).click();
  await expect(page.locator(".run-source-grid")).toContainText("4 postings");
});

test("connection setup is explicit and accepts custom API details", async ({
  page,
}) => {
  await page.goto("/#/settings?tab=connection");
  await page
    .getByRole("combobox", { name: "Connection", exact: true })
    .selectOption("custom");
  await expect(
    page.getByRole("textbox", { name: "API endpoint", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("textbox", { name: "API endpoint", exact: true })
    .fill("https://example.org/v1");
  await page
    .getByRole("combobox", { name: "Model", exact: true })
    .fill("example-model");
  await expect(page.getByRole("button", { name: "Save & test" })).toBeEnabled();
  await expect(page.getByText("Local evidence engine active")).toBeVisible();
});

test("desktop and mobile layouts do not overflow", async ({
  page,
}, testInfo) => {
  for (const viewport of [
    { width: 1440, height: 1000 },
    { width: 390, height: 844 },
  ]) {
    await page.setViewportSize(viewport);
    for (const route of [
      "matches",
      "applications",
      "profile",
      "settings?tab=connection",
      "settings?tab=sources",
    ]) {
      await page.goto(`/#/${route}`);
      await expect(page.locator("main h1")).toBeVisible();
      await page
        .locator(".skeleton-card")
        .first()
        .waitFor({ state: "detached" });
      await page.evaluate(async () => {
        await document.fonts.ready;
        await Promise.all(
          document
            .getAnimations()
            .filter(
              (animation) =>
                animation.effect?.getTiming().iterations !== Infinity,
            )
            .map((animation) => animation.finished.catch(() => undefined)),
        );
      });
      const width = await page.evaluate(() => ({
        actual: document.documentElement.scrollWidth,
        viewport: innerWidth,
      }));
      expect(
        width.actual,
        `${route} horizontal overflow at ${viewport.width}`,
      ).toBeLessThanOrEqual(width.viewport);
      if (route === "matches")
        await page.screenshot({
          path: testInfo.outputPath(`matches-${viewport.width}.png`),
          fullPage: true,
        });
    }
    if (viewport.width === 390) {
      await page.getByRole("button", { name: "Open navigation" }).click();
      await page.getByRole("link", { name: "Matches", exact: true }).click();
      await expect(
        page.getByRole("heading", { name: "Your matches", exact: true }),
      ).toBeVisible();
    }
  }
});

test("matches and profile pass accessibility checks", async ({ page }) => {
  const violations: unknown[] = [];
  for (const route of ["matches", "profile", "settings?tab=connection"]) {
    await page.goto(`/#/${route}`);
    await expect(page.locator("main h1")).toBeVisible();
    await page.locator(".skeleton-card").first().waitFor({ state: "detached" });
    await page.evaluate(async () => {
      await document.fonts.ready;
      await Promise.all(
        document
          .getAnimations()
          .filter(
            (animation) =>
              animation.effect?.getTiming().iterations !== Infinity,
          )
          .map((animation) => animation.finished.catch(() => undefined)),
      );
    });
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
      .analyze();
    violations.push(
      ...results.violations.map((violation) => ({
        route,
        id: violation.id,
        impact: violation.impact,
        targets: violation.nodes.map((node) => ({
          target: node.target,
          detail: node.failureSummary,
        })),
      })),
    );
  }
  expect(violations).toEqual([]);
});

test("clear matches preserves applications", async ({ page }) => {
  await page.goto("/#/matches");
  await page.getByRole("button", { name: "Clear stored matches" }).click();
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(page.locator(".job-card")).toHaveCount(4);
  await page.getByRole("button", { name: "Clear stored matches" }).click();
  await page
    .getByRole("button", { name: "Clear matches", exact: true })
    .click();
  await expect(page.locator(".job-card")).toHaveCount(1);
  await expect(page.locator(".job-card")).toContainText("Northstar");
  await page.getByRole("link", { name: /^Applications/ }).click();
  await expect(page.locator(".application-row")).toHaveCount(1);
});
