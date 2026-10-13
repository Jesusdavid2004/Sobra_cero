import { expect, test } from "@playwright/test";

test("publishes a lot, reserves it, and confirms pickup across locales", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "light" });
  await page.addInitScript(() => localStorage.setItem("sc_theme", "light"));

  const lot = {
    id: 1,
    shop_id: 5,
    product_id: 8,
    title: "Rescue Bread",
    description: "Freshly baked bread",
    quantity: 10,
    original_price_cents: 1200,
    discount_percent: 50,
    expires_at: "2030-01-01T12:00:00Z",
    image_url: null,
    category: "bakery",
    business_type: "restaurant",
  };
  let reservationStatus = "reserved";
  let pickupCode = "";

  await page.route("http://localhost:8000/api/v1/**", async (route) => {
    const request = route.request();
    const { pathname } = new URL(request.url());
    const method = request.method();
    const body = request.postDataJSON() as Record<string, unknown> | null;
    const token = request.headers().authorization;

    if (pathname === "/api/v1/auth/refresh") {
      await route.fulfill({ status: 401, json: { detail: "No refresh session" } });
    } else if (pathname === "/api/v1/auth/login" && method === "POST") {
      const isBusiness = String(body?.email).startsWith("business");
      await route.fulfill({
        json: { access_token: isBusiness ? "business-token" : "customer-token" },
      });
    } else if (pathname === "/api/v1/auth/me") {
      const isBusiness = token === "Bearer business-token";
      await route.fulfill({
        json: {
          id: isBusiness ? 11 : 12,
          email: isBusiness ? "business@example.com" : "customer@example.com",
          role: isBusiness ? "business" : "customer",
          is_admin: false,
        },
      });
    } else if (pathname === "/api/v1/auth/logout") {
      await route.fulfill({ status: 204 });
    } else if (pathname === "/api/v1/shops") {
      await route.fulfill({
        json: [
          {
            id: 5,
            owner_id: 11,
            name: "Green Bakery",
            business_type: "restaurant",
            description: "Neighborhood bakery",
            latitude: 4.7,
            longitude: -74.07,
          },
        ],
      });
    } else if (pathname === "/api/v1/shops/5/products") {
      await route.fulfill({
        json: [
          {
            id: 8,
            shop_id: 5,
            name: "Bread",
            description: "Fresh bread",
            category: "bakery",
          },
        ],
      });
    } else if (pathname === "/api/v1/shops/5/waste-risk") {
      await route.fulfill({ json: [] });
    } else if (pathname === "/api/v1/lots" && method === "POST") {
      Object.assign(lot, body);
      await route.fulfill({ status: 201, json: lot });
    } else if (pathname === "/api/v1/lots") {
      await route.fulfill({ json: [lot] });
    } else if (pathname === "/api/v1/lots/1/promos") {
      await route.fulfill({ json: [] });
    } else if (pathname === "/api/v1/lots/1/expiry-scans") {
      await route.fulfill({ json: [] });
    } else if (pathname === "/api/v1/lots/1/reserve" && method === "POST") {
      pickupCode = "AB12CD34";
      lot.quantity -= Number(body?.quantity);
      await route.fulfill({
        status: 201,
        json: { id: 42, status: "reserved", quantity: body?.quantity, pickup_code: pickupCode },
      });
    } else if (pathname === "/api/v1/reservations/42/pickup" && method === "POST") {
      expect(body?.pickup_code).toBe(pickupCode);
      reservationStatus = "picked_up";
      await route.fulfill({ json: { id: 42, status: reservationStatus, quantity: 1 } });
    } else if (pathname === "/api/v1/lots/1") {
      await route.fulfill({ json: lot });
    } else {
      await route.fulfill({
        status: 404,
        json: { detail: `Unexpected API request: ${method} ${pathname}` },
      });
    }
  });

  await page.goto("/en");
  await page.getByRole("button", { name: "Toggle theme" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.getByRole("button", { name: "Toggle theme" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.getByRole("button", { name: "Change language: Español" }).click();
  await expect(page.locator("html")).toHaveAttribute("lang", "es");
  await page.getByRole("button", { name: "Cambiar idioma: English" }).click();
  await expect(page.locator("html")).toHaveAttribute("lang", "en");

  await page.goto("/en/login");
  await page.getByLabel("Email").fill("business@example.com");
  await page.getByLabel("Password").fill("test-password");
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page).toHaveURL(/\/en\/shop$/);
  await page.locator('a[href*="/lots/new?shop=5"]').first().click();
  await expect(page).toHaveURL(/\/en\/lots\/new\?shop=5$/);
  await page.getByLabel("Shop").selectOption("5");
  await page.getByLabel("Product").selectOption("8");
  await page.getByPlaceholder("Lot title").fill("Rescue Bread");
  await page.getByPlaceholder("Description").fill("Freshly baked bread");
  await page.getByLabel("Quantity available").fill("10");
  await page.getByLabel("Original price (cents)").fill("1200");
  await page.getByLabel("Discount (%)").fill("50");
  await page.getByLabel("Expires at").fill("2030-01-01T12:00");
  await page.getByRole("button", { name: "Publish lot" }).click();
  await expect(page.getByRole("heading", { name: "Rescue Bread" })).toBeVisible();

  await page.getByRole("button", { name: "Log out" }).click();
  await page.goto("/en/login");
  await page.getByLabel("Email").fill("customer@example.com");
  await page.getByLabel("Password").fill("test-password");
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page).toHaveURL(/\/en\/lots$/);
  await expect(page.getByRole("button", { name: "Log out" })).toBeVisible();
  await page.getByRole("link", { name: "View and reserve" }).click();
  await expect(page).toHaveURL(/\/en\/lots\/1$/);
  await page.getByRole("button", { name: "Confirm reservation" }).click();
  await expect(page.getByText(/Reservation reference: 42/)).toBeVisible();
  await expect(page.getByText(/Your pickup code: AB12CD34/)).toBeVisible();

  await page.getByRole("button", { name: "Log out" }).click();
  await page.goto("/en/login");
  await page.getByLabel("Email").fill("business@example.com");
  await page.getByLabel("Password").fill("test-password");
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page).toHaveURL(/\/en\/shop$/);
  await page.getByLabel("Reservation reference").fill("42");
  await page.getByLabel("Pickup code").fill("AB12CD34");
  await page.getByRole("button", { name: "Confirm pickup" }).click();

  await expect(page.getByRole("status")).toContainText("Pickup confirmed");
  expect(reservationStatus).toBe("picked_up");
});
