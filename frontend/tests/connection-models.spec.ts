import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import type { BridgeModels, Connection } from "../src/types";

const supported: BridgeModels = {
  models: ["claude-sonnet-4.6", "gpt-5-mini"],
  default_model: "gpt-5-mini",
  available: true,
  detail: "Connected to VS Code",
};

async function connectionFixture(page: Page, model = "", provider = "vscode") {
  const saved: Connection = {
    provider,
    model,
    preset: "custom",
    base_url: "",
    key_set: false,
    presets: [
      {
        key: "custom",
        label: "Custom API",
        provider: "openai_compat",
        base_url: "",
        suggested_models: [],
        needs_paid_key: true,
        needs_base_url: true,
      },
    ],
    local_matching: true,
  };
  const writes: { provider: string; model: string }[] = [];
  await page.route("**/api/connections", async (route) => {
    if (route.request().method() === "PUT") {
      const body = route.request().postDataJSON();
      writes.push(body);
      saved.model = body.model;
      saved.provider = body.provider;
    }
    await route.fulfill({ json: saved });
  });
  return writes;
}

test("bridge dropdown lists live names and saves the exact selected value", async ({
  page,
}) => {
  const writes = await connectionFixture(page, "gpt-5-mini");
  await page.route("**/api/connections/vscode/models", (route) =>
    route.fulfill({ json: supported }),
  );
  await page.goto("/#/settings?tab=connection");
  const picker = page.getByRole("combobox", { name: "Model", exact: true });
  await expect(picker).toBeEnabled();
  await expect(page.locator("input#model-name")).toHaveCount(0);
  await expect(picker.locator("option")).toHaveText([
    "Automatic (gpt-5-mini)",
    "claude-sonnet-4.6",
    "gpt-5-mini",
  ]);
  await expect(picker).toHaveValue("gpt-5-mini");
  await picker.selectOption("claude-sonnet-4.6");
  await page
    .getByRole("button", { name: "Save connection", exact: true })
    .click();
  await expect.poll(() => writes.at(-1)?.model).toBe("claude-sonnet-4.6");
  await page.reload();
  await expect(picker).toHaveValue("claude-sonnet-4.6");
  await picker.selectOption("");
  await page
    .getByRole("button", { name: "Save connection", exact: true })
    .click();
  await expect.poll(() => writes.at(-1)?.model).toBe("");
});

test("a stale saved model is visible but cannot be saved again", async ({
  page,
}) => {
  await connectionFixture(page, "retired-model");
  await page.route("**/api/connections/vscode/models", (route) =>
    route.fulfill({ json: supported }),
  );
  await page.goto("/#/settings?tab=connection");
  const picker = page.getByRole("combobox", { name: "Model", exact: true });
  await expect(picker).toBeEnabled();
  await expect(picker.locator('option[value="retired-model"]')).toBeDisabled();
  await expect(
    page.getByText(
      "The selected model is no longer available from this bridge.",
    ),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Save connection", exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "Save & test" }),
  ).toBeDisabled();
  await picker.selectOption("gpt-5-mini");
  await expect(
    page.getByRole("button", { name: "Save connection", exact: true }),
  ).toBeEnabled();
});

test("disconnected bridge has no invented choices and refresh recovers", async ({
  page,
}) => {
  await connectionFixture(page);
  let available = false;
  await page.route("**/api/connections/vscode/models", (route) =>
    route.fulfill({
      json: available
        ? supported
        : {
            models: [],
            default_model: "",
            available: false,
            detail: "No reachable VS Code bridge.",
          },
    }),
  );
  await page.goto("/#/settings?tab=connection");
  const picker = page.getByRole("combobox", { name: "Model", exact: true });
  await expect(picker.locator("option")).toHaveText(["No models available"]);
  await expect(picker).toBeDisabled();
  await expect(page.getByText("No reachable VS Code bridge.")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Save & test" }),
  ).toBeDisabled();
  available = true;
  await page.getByRole("button", { name: "Refresh bridge models" }).click();
  await expect(picker).toBeEnabled();
  await expect(picker.locator("option")).toHaveCount(3);
});

test("models can be chosen before consent without hiding the consent message", async ({
  page,
}) => {
  await connectionFixture(page);
  await page.route("**/api/connections/vscode/models", (route) =>
    route.fulfill({
      json: {
        ...supported,
        available: false,
        detail: "Waiting for Copilot consent.",
      },
    }),
  );
  await page.goto("/#/settings?tab=connection");
  await expect(
    page.getByRole("combobox", { name: "Model", exact: true }),
  ).toBeEnabled();
  await expect(page.getByText("Waiting for Copilot consent.")).toBeVisible();
});

test("model discovery only runs for the bridge and other providers keep their input", async ({
  page,
}) => {
  await connectionFixture(page, "custom-model", "openai_compat");
  let discoveries = 0;
  await page.route("**/api/connections/vscode/models", (route) => {
    discoveries += 1;
    return route.fulfill({ json: supported });
  });
  await page.goto("/#/settings?tab=connection");
  await expect(page.locator("input#model-name")).toHaveValue("custom-model");
  expect(discoveries).toBe(0);
  await page
    .getByRole("combobox", { name: "Connection", exact: true })
    .selectOption("vscode");
  await expect(page.locator("select#model-name")).toBeEnabled();
  expect(discoveries).toBe(1);
  await page
    .getByRole("combobox", { name: "Connection", exact: true })
    .selectOption("custom");
  await expect(page.locator("input#model-name")).toBeVisible();
  await page.locator("input#model-name").fill("my-deployment");
  await expect(page.locator("input#model-name")).toHaveValue("my-deployment");
});

test("loading and HTTP errors cannot submit a model and retry is available", async ({
  page,
}) => {
  await connectionFixture(page);
  let finish: (() => void) | undefined;
  const pending = new Promise<void>((resolve) => {
    finish = resolve;
  });
  await page.route("**/api/connections/vscode/models", async (route) => {
    await pending;
    await route.fulfill({
      status: 503,
      json: { detail: "Model discovery temporarily unavailable." },
    });
  });
  await page.goto("/#/settings?tab=connection");
  await expect(page.locator("select#model-name option")).toHaveText([
    "Loading models...",
  ]);
  await expect(
    page.getByRole("button", { name: "Save connection", exact: true }),
  ).toBeDisabled();
  finish?.();
  await expect(
    page.getByText("Model discovery temporarily unavailable."),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Retry", exact: true }),
  ).toBeVisible();
});

test("bridge picker fits desktop and mobile and remains accessible", async ({
  page,
}, testInfo) => {
  await connectionFixture(page, "claude-sonnet-4.6");
  await page.route("**/api/connections/vscode/models", (route) =>
    route.fulfill({ json: supported }),
  );
  await page.emulateMedia({ reducedMotion: "reduce" });
  for (const viewport of [
    { width: 1440, height: 1000 },
    { width: 390, height: 844 },
  ]) {
    await page.setViewportSize(viewport);
    await page.goto("/#/settings?tab=connection");
    await expect(page.locator("select#model-name")).toBeEnabled();
    await page.evaluate(() => document.fonts.ready);
    const layout = await page.locator(".model-picker").evaluate((element) => {
      const picker = element.getBoundingClientRect();
      const select = element.querySelector("select")!.getBoundingClientRect();
      const refresh = element.querySelector("button")!.getBoundingClientRect();
      return {
        inside: picker.left >= 0 && picker.right <= innerWidth,
        separate: select.right <= refresh.left,
        pageFits: document.documentElement.scrollWidth <= innerWidth,
      };
    });
    expect(layout).toEqual({ inside: true, separate: true, pageFits: true });
    const accessibility = await new AxeBuilder({ page })
      .include(".connection-form")
      .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
      .analyze();
    expect(accessibility.violations).toEqual([]);
    await page.screenshot({
      path: testInfo.outputPath(`bridge-models-${viewport.width}.png`),
      fullPage: true,
    });
  }
});
