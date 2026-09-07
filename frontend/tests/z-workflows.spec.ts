import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import type { APIRequestContext, Page } from "@playwright/test";

test.describe.configure({ mode: "serial" });

async function seed(request: APIRequestContext, company: string) {
  const payload = {
    title: "Technical Support Engineer",
    company,
    location: "Pune, India",
    work_mode: "remote",
    employment: "full-time",
    posted_at: new Date().toISOString(),
    url: `https://example.org/jobs/${encodeURIComponent(company)}`,
    description:
      "Troubleshoot Microsoft 365, SharePoint, Azure and Networking incidents. Automate repetitive support work with Python. Collaborate with engineering and document solutions for enterprise customers. Python is required; Java is nice to have.",
  };
  const response = await request.post("/api/capture/import", { data: payload });
  expect(response.ok()).toBeTruthy();
  return { ...(await response.json()), payload };
}

async function settled(page: Page) {
  await page.evaluate(async () => {
    await document.fonts.ready;
    await Promise.all(
      document
        .getAnimations()
        .filter((animation) =>
          Number.isFinite(
            Number(animation.effect?.getComputedTiming().iterations),
          ),
        )
        .map((animation) => animation.finished.catch(() => {})),
    );
  });
}

test("saved search tracks persist and do not modify the main profile", async ({
  page,
  request,
}) => {
  await seed(request, "Track Test");
  const profile = (await (await request.get("/api/workspace")).json()).profile;
  await page.goto("/#/matches");
  await page.getByRole("button", { name: "Create search track" }).click();
  await page.getByLabel("Track name", { exact: true }).fill("Cloud focus");
  await page.getByRole("button", { name: "Save track", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  const trackId = Number(
    await page.getByLabel("Search track", { exact: true }).inputValue(),
  );
  expect(trackId).toBeGreaterThan(0);
  await page.reload();
  await expect(page.getByLabel("Search track", { exact: true })).toHaveValue(
    String(trackId),
  );
  expect((await (await request.get("/api/workspace")).json()).profile).toEqual(
    profile,
  );
  await page.getByRole("button", { name: "Edit search track" }).click();
  await page.getByLabel("Track name", { exact: true }).fill("Support focus");
  await page.getByRole("button", { name: "Save track", exact: true }).click();
  await expect(
    page.getByLabel("Search track", { exact: true }).locator("option:checked"),
  ).toHaveText("Support focus");
  await request.delete(`/api/tracks/${trackId}`);
});

test("inbox acknowledges a posting and resurfaces changed content", async ({
  page,
  request,
}) => {
  const { job_id: jobId, payload } = await seed(request, "Inbox Test");
  const track = await (
    await request.post("/api/tracks", {
      data: {
        name: "Inbox test",
        preferences: {
          target_titles: ["Technical Support Engineer"],
          locations: ["India"],
        },
      },
    })
  ).json();
  await page.goto(`/#/matches?view=inbox&track=${track.id}&q=Inbox%20Test`);
  await expect(page.locator(".job-card")).toHaveCount(1);
  const acknowledged = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/inbox/seen") &&
      response.request().method() === "POST" &&
      response.ok(),
  );
  await page.getByRole("button", { name: "View match" }).click();
  await expect(
    page.getByRole("dialog", { name: "Opportunity details" }),
  ).toBeVisible();
  await acknowledged;
  await page.keyboard.press("Escape");
  await expect(
    page.getByRole("heading", { name: "You're up to date" }),
  ).toBeVisible();
  await request.post("/api/capture/import", {
    data: {
      ...payload,
      description:
        payload.description +
        " Updated responsibilities include on-call triage.",
    },
  });
  await page.reload();
  await expect(page.locator(".job-card")).toHaveCount(1);
  await page
    .getByRole("button", { name: "Mark this page as reviewed" })
    .click();
  await expect(page.locator(".job-card")).toHaveCount(0);
  expect(
    (await (await request.get(`/api/opportunities/${jobId}`)).json()).job,
  ).toBeTruthy();
  await request.delete(`/api/tracks/${track.id}`);
});

test("relevance feedback is reflected in the labeled benchmark", async ({
  page,
  request,
}) => {
  const { job_id: jobId } = await seed(request, "Feedback Test");
  await page.goto(`/#/matches?view=all&job=${jobId}`);
  await page.getByText("Your relevance label", { exact: true }).click();
  await page.getByRole("radio", { name: "Relevant", exact: true }).check();
  await page
    .getByRole("combobox", { name: "Reason Optional", exact: true })
    .selectOption("good_fit");
  await page.getByRole("button", { name: "Save feedback" }).click();
  await expect(
    page.getByText("Your relevance label: relevant", { exact: true }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  await page.goto("/#/settings?tab=data");
  await expect(
    page.getByRole("heading", { name: "Relevance benchmark" }),
  ).toBeVisible();
  await expect(
    page.locator(".workflow-table").filter({ hasText: "Your label" }),
  ).toContainText("Relevant");
  await request.delete(`/api/opportunities/${jobId}/feedback`);
});

test("application follow-ups, recruiter details, and timeline survive reload", async ({
  page,
  request,
}) => {
  const { job_id: jobId } = await seed(request, "Followup Test");
  await request.post(`/api/jobs/${jobId}/application`, {
    data: { status: "applied" },
  });
  await page.goto("/#/applications");
  await page
    .locator(".application-row")
    .filter({ hasText: "Followup Test" })
    .getByRole("button", { name: /Activity for/ })
    .click();
  await page.getByRole("textbox", { name: /^Recruiter name/ }).fill("Taylor");
  await page
    .getByRole("textbox", { name: /^Recruiter email/ })
    .fill("taylor@example.org");
  await page.getByRole("button", { name: "Save details" }).click();
  await page
    .getByLabel("Next action", { exact: true })
    .fill("Discuss support rotation");
  await page.getByLabel("Due at (local time)").fill("2026-09-10T10:30");
  await page
    .getByRole("button", { name: "Add next action", exact: true })
    .click();
  await expect(page.getByRole("dialog").locator(".agenda-row")).toContainText(
    "Discuss support rotation",
  );
  await page.keyboard.press("Escape");
  await expect(page.locator(".agenda-section")).toContainText(
    "Discuss support rotation",
  );
  await page.reload();
  await page
    .getByRole("button", { name: "Discuss support rotation", exact: true })
    .click();
  await expect(
    page.getByRole("textbox", { name: /^Recruiter name/ }),
  ).toHaveValue("Taylor");
  await expect(page.locator(".activity-timeline")).toContainText(
    "Scheduled Discuss support rotation",
  );
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Complete Discuss support rotation" })
    .click();
  await expect(
    page.getByRole("button", { name: "Reopen Discuss support rotation" }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.locator(".agenda-section")).not.toContainText(
    "Discuss support rotation",
  );
  await request.delete(`/api/jobs/${jobId}/application`);
});

test("capture previews pasted content before importing and does not invent a date", async ({
  page,
  request,
}) => {
  await page.goto("/#/capture");
  await page
    .getByRole("textbox", { name: /^Original posting URL/ })
    .fill("https://example.org/captured-job");
  await page
    .getByLabel("Job description, alert email, or browser capture")
    .fill(
      "Technical support role troubleshooting Azure, Microsoft 365, Networking and SharePoint. Build Python automation and collaborate with enterprise support teams to resolve customer issues.",
    );
  await page.getByRole("button", { name: "Preview pasted content" }).click();
  await page
    .getByLabel("Job title", { exact: true })
    .fill("Technical Support Engineer");
  await page.getByLabel("Company", { exact: true }).fill("Captured Employer");
  await page.getByRole("textbox", { name: /^Location/ }).fill("India");
  await page
    .getByLabel("Work arrangement", { exact: true })
    .selectOption("remote");
  await page
    .getByRole("button", { name: "Confirm import", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toContainText("Captured Employer");
  const jobId = new URLSearchParams(page.url().split("?")[1]).get("job");
  const result = await (
    await request.get(`/api/opportunities/${jobId}`)
  ).json();
  expect(result.job.posted_at).toBeNull();
});

test("backup preview and confirmation restore the selected archive", async ({
  page,
  request,
}) => {
  await seed(request, "Backup Test");
  const backup = await request.get("/api/backups/export");
  expect(backup.ok()).toBeTruthy();
  const content = await backup.body();
  await page.goto("/#/settings?tab=data");
  await page
    .getByLabel("Workspace backup", { exact: true })
    .setInputFiles({
      name: "workspace.zip",
      mimeType: "application/zip",
      buffer: content,
    });
  await page
    .getByRole("button", { name: "Preview backup", exact: true })
    .click();
  await expect(page.locator(".backup-summary")).toContainText("Postings");
  await page
    .getByRole("button", { name: "Restore this backup", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Replace workspace", exact: true }),
  ).toBeDisabled();
  await page.getByLabel("Type RESTORE to confirm").fill("RESTORE");
  await page
    .getByRole("button", { name: "Replace workspace", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.locator(".toast")).toContainText("Workspace restored");
});

test("new workflows fit desktop and mobile and pass accessibility checks", async ({
  page,
}, testInfo) => {
  test.setTimeout(90000);
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    for (const route of [
      "matches?view=inbox",
      "applications",
      "capture",
      "settings?tab=data",
    ]) {
      await page.goto(`/#/${route}`);
      await expect(page.locator(".page-head h1")).toBeVisible();
      await settled(page);
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= window.innerWidth,
        ),
      ).toBeTruthy();
      const scan = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
        .analyze();
      expect(scan.violations).toEqual([]);
      await page.screenshot({
        path: testInfo.outputPath(`${route.split("?")[0]}-${width}.png`),
        fullPage: true,
      });
    }
    await page.goto("/#/matches");
    await page.getByRole("button", { name: "Create search track" }).click();
    await settled(page);
    const scan = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
      .analyze();
    expect(scan.violations).toEqual([]);
    await page.screenshot({
      path: testInfo.outputPath(`track-dialog-${width}.png`),
      fullPage: true,
    });
    await page.keyboard.press("Escape");
  }
});
