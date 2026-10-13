import { expect, test } from "@playwright/test";

test("redirects to a locale-prefixed page and switches locale and theme", async ({ page }) => {
  await page.goto("/");

  await expect(page).toHaveURL(/\/en\/?$/);
  await expect(
    page.getByRole("heading", { name: "Rescue good food. Save money. Waste less." }),
  ).toBeVisible();

  await page.getByRole("button", { name: "Toggle theme" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.getByRole("button", { name: "Toggle theme" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");

  await page.getByRole("button", { name: "Change language: Español" }).click();
  await expect(page).toHaveURL(/\/es\/?$/);
  await expect(page.locator("html")).toHaveAttribute("lang", "es");
  await expect(
    page.getByRole("heading", { name: "Rescata comida. Ahorra y evita desperdicios." }),
  ).toBeVisible();
});

test("renders the Spanish storefront directly", async ({ page }) => {
  await page.goto("/es");

  await expect(page.locator("html")).toHaveAttribute("lang", "es");
  await expect(page.getByRole("link", { name: "Ir a la vitrina" })).toBeVisible();
});
