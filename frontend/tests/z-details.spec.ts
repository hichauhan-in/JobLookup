import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test("daily brief shows unseen roles and downloads a local digest", async ({ page }) => {
  await page.goto("/#/matches?view=inbox");
  await page.getByRole("button", { name: "Daily brief", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Daily brief" });
  await expect(dialog.getByRole("heading", { name: "Next opportunities" })).toBeVisible();
  await expect(dialog.getByRole("heading", { name: "Due this week" })).toBeVisible();
  const download = page.waitForEvent("download");
  await dialog.getByRole("link", { name: "Download brief" }).click();
  expect((await download).suggestedFilename()).toBe("joblookup-daily-brief.md");
  await dialog.getByRole("button", { name: "Done", exact: true }).click();
  await expect(dialog).toHaveCount(0);
});

test("resume history compares immutable drafts and flags new claims", async ({ page, request }) => {
  const data = await (await request.get("/api/opportunities?view=all")).json();
  const jobId = data.items[0].id;
  await page.route(`**/api/opportunities/${jobId}/versions`, (route) => route.fulfill({ json: { items: [{ id: 71, cv_id: 1, cv_label: "Original resume", created_at: "2026-09-07T10:00:00Z" }] } }));
  await page.route("**/api/resume-versions/71", (route) => route.fulfill({ json: { id: 71, markdown: "Python and Java, 10 years", base_text: "Python, 3 years", diff: "--- Original resume\n+++ Tailored draft\n-Python, 3 years\n+Python and Java, 10 years", checks: { new_skill_mentions: ["Java"], new_numeric_claims: ["10"], requires_review: true } } }));
  await page.goto(`/#/matches?view=all&job=${jobId}`);
  await page.getByRole("button", { name: "Resume", exact: true }).click();
  await page.getByText("Version history & comparison", { exact: false }).click();
  await expect(page.locator(".resume-diff .diff-added")).toContainText(["+++ Tailored draft", "+Python and Java, 10 years"]);
  await expect(page.getByText("New skill mentions: Java", { exact: true })).toBeVisible();
  await expect(page.getByText("New numbers: 10", { exact: true })).toBeVisible();
  await page.getByRole("checkbox", { name: "Compare with original" }).uncheck();
  await expect(page.locator(".version-history .prose")).toContainText("Python and Java, 10 years");
});

test("expanded eligibility controls remain accessible on a narrow screen", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 1000 });
  await page.goto("/#/matches");
  await page.getByRole("button", { name: "Create search track" }).click();
  await page.getByText("Eligibility preferences", { exact: true }).click();
  await page.getByRole("checkbox", { name: "Visa sponsorship required" }).check();
  await page.evaluate(async () => {
    await document.fonts.ready;
    await Promise.all(document.getAnimations().filter((animation) => Number.isFinite(Number(animation.effect?.getComputedTiming().iterations))).map((animation) => animation.finished.catch(() => {})));
  });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze()).violations).toEqual([]);
});