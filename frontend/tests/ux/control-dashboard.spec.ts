import { expect, test } from '@playwright/test';

const ONE_PIXEL_PNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII=',
  'base64',
);

test.beforeEach(async ({ page }) => {
  let ringRequestCount = 0;

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

    if (devices === 'ring') {
      ringRequestCount += 1;
      await route.fulfill({
        contentType: 'application/json',
        json: {
          ring: {
            configured: true,
            locations: [
              {
                name: 'Home',
                devices: [
                  { name: ringRequestCount > 1 ? 'Fresh Back Door' : 'Back Door', device_type: 'contact_sensor', faulted: false, battery_level: 91 },
                  { name: ringRequestCount > 1 ? 'Fresh Hall Motion' : 'Hall Motion', device_type: 'motion_sensor', faulted: true, battery_level: 88 },
                ],
              },
            ],
          },
        },
      });
      return;
    }

    await route.fulfill({
      contentType: 'application/json',
      json: {
        hue: { name: 'Baby room', is_on: true, brightness: 128 },
        rinnai: { is_online: true, set_temperature: 120, outlet_temp: 118, inlet_temp: 65, recirculation_enabled: false },
        garage: {
          door_count: 2,
          available: true,
          doors: [
            { index: 1, label: 'Garage Door Black' },
            { index: 2, label: 'Garage Door White' },
          ],
        },
        ring: {
          configured: true,
          locations: [
            {
              name: 'Home',
              devices: [
                { name: 'Back Door', device_type: 'contact_sensor', faulted: false, battery_level: 91 },
                { name: 'Hall Motion', device_type: 'motion_sensor', faulted: true, battery_level: 88 },
              ],
            },
          ],
        },
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

  await expect(page.getByRole('button', { name: 'Garage Door Black' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Garage Door White' })).toBeVisible();
  await expect(page.getByRole('img', { name: 'Garage' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Garage' }).first()).toHaveAttribute('href', '/api/cameras/snapshot/garage');

  await expect(page.getByRole('heading', { name: /contact sensors/i })).toBeVisible();
  await expect(page.getByText('Back Door')).toBeVisible();
  await expect(page.getByText('Hall Motion')).not.toBeVisible();

  await expect(page.getByText('Loading switches...')).toBeVisible();
  await expect(page.getByText('Coffee maker')).toBeVisible();
});

test('ring tab renders all Ring sensors', async ({ page }) => {
  await page.goto('/ring');

  await expect(page.getByRole('heading', { name: /ring sensors/i })).toBeVisible();
  await expect(page.getByText('Back Door')).toBeVisible();
  await expect(page.getByText('Hall Motion')).toBeVisible();
});

test('ring tab reuses cached sensors and manual refresh updates them', async ({ page }) => {
  await page.goto('/control');
  await expect(page.getByText('Back Door')).toBeVisible();

  await page.getByRole('button', { name: /ring/i }).click();

  await expect(page.getByText('Back Door')).toBeVisible();
  await expect(page.getByText('Hall Motion')).toBeVisible();

  await page.getByRole('button', { name: 'Refresh' }).click();

  await expect(page.getByText('Fresh Back Door')).toBeVisible();
  await expect(page.getByText('Fresh Hall Motion')).toBeVisible();
});

test('mobile tab navigation wraps without horizontal overflow', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/control');

  const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
  const clientWidth = await page.evaluate(() => document.documentElement.clientWidth);
  expect(scrollWidth).toBeLessThanOrEqual(clientWidth);
  await expect(page.getByRole('button', { name: /history/i })).toBeVisible();
});
