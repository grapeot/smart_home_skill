import { expect, test } from '@playwright/test';

const ONE_PIXEL_PNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII=',
  'base64',
);

test.beforeEach(async ({ page }) => {
  await page.route('**/api/status**', async route => {
    const url = new URL(route.request().url());
    const devices = url.searchParams.get('devices');

    if (devices === 'wemo') {
      await new Promise(resolve => setTimeout(resolve, 500));
      await route.fulfill({
        contentType: 'application/json',
        json: { wemo: { coffee: { name: 'coffee', is_on: true } } },
      });
      return;
    }

    await route.fulfill({
      contentType: 'application/json',
      json: {
        hue: { name: 'Baby room', is_on: true, brightness: 128 },
        rinnai: { is_online: true, set_temperature: 120, outlet_temp: 118, inlet_temp: 65, recirculation_enabled: false },
        garage: { door_count: 2, available: true },
      },
    });
  });

  await page.route('**/api/cameras', route => route.fulfill({
    contentType: 'application/json',
    json: { cameras: [{ id: 'garage', name: 'Garage' }] },
  }));

  await page.route('**/api/cameras/snapshot/garage**', route => route.fulfill({
    contentType: 'image/png',
    body: ONE_PIXEL_PNG,
  }));
});

test('control dashboard renders garage camera without blocking on Wemo', async ({ page }) => {
  await page.goto('/control');

  await expect(page.getByRole('heading', { name: /garage doors/i })).toBeVisible();
  await expect(page.getByRole('heading', { name: /water heater/i })).toBeVisible();

  const garageBox = await page.getByRole('heading', { name: /garage doors/i }).boundingBox();
  const waterHeaterBox = await page.getByRole('heading', { name: /water heater/i }).boundingBox();
  expect(garageBox?.y).toBeLessThan(waterHeaterBox?.y ?? Number.POSITIVE_INFINITY);

  await expect(page.getByRole('button', { name: 'Garage door 1' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Garage door 2' })).toBeVisible();
  await expect(page.getByRole('img', { name: 'Garage' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Garage' }).first()).toHaveAttribute('href', '/api/cameras/snapshot/garage');

  await expect(page.getByText('Loading switches...')).toBeVisible();
  await expect(page.getByText('Coffee maker')).toBeVisible();
});
