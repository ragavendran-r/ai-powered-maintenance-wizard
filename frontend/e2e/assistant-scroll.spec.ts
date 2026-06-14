import { expect, test, type Page } from '@playwright/test'
import { installMaintenanceApi } from './maintenance-fixtures'

const repeatedResponse = [
  '### Assessment',
  '- Inspect vibration trend, recent work orders, and retrieved SOP evidence before proceeding.',
  '- Confirm that the visible response remains pinned while the assistant stream grows.',
  '### Next Actions',
  '- Check isolation, PPE, guard condition, bearing temperature, vibration, and operating limits.',
  '- Record abnormal findings and update the work order summary.',
].join('\n')

function sse(event: unknown) {
  return `data: ${JSON.stringify(event)}\n\n`
}

function longAnswer(label: string) {
  return Array.from({ length: 14 }, (_, index) => `${repeatedResponse}\n- ${label} validation chunk ${index + 1}.`).join('\n')
}

async function signIn(page: Page) {
  await page.goto('/')
  if (await page.getByRole('button', { name: 'Sign In' }).isVisible()) {
    await page.getByRole('button', { name: 'Sign In' }).click()
  }
  await expect(page.getByRole('heading', { name: 'Maintenance Wizard' })).toBeVisible()
  await expect(page.locator('.userPill strong', { hasText: 'Plant Admin' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Logout' })).toBeVisible()
}

async function expectPinnedToBottom(page: Page, selector: string) {
  await expect
    .poll(
      () => page.locator(selector).evaluate((element) =>
        Math.abs(element.scrollHeight - element.clientHeight - element.scrollTop),
      ),
      { timeout: 4_000 },
    )
    .toBeLessThanOrEqual(6)

  const metrics = await page.locator(selector).evaluate((element) => ({
    scrollHeight: element.scrollHeight,
    clientHeight: element.clientHeight,
    viewportBottom: element.getBoundingClientRect().bottom,
    windowHeight: window.innerHeight,
  }))

  expect(metrics.scrollHeight).toBeGreaterThan(metrics.clientHeight)
  expect(metrics.viewportBottom).toBeLessThanOrEqual(metrics.windowHeight + 6)
}

test.beforeEach(async ({ page }) => {
  await installMaintenanceApi(page)

  await page.route('**/api/neo/chat/stream', async (route) => {
    const answer = longAnswer('Neo')
    await route.fulfill({
      contentType: 'text/event-stream',
      body: [
        sse({ type: 'meta', provider: 'playwright', used_live_provider: true }),
        sse({ type: 'token', content: answer }),
        sse({
          type: 'done',
          response: {
            answer,
            table: null,
            provider: 'playwright',
            used_live_provider: true,
          },
        }),
      ].join(''),
    })
  })

  await page.route('**/api/diagnose/stream', async (route) => {
    const answer = longAnswer('Morpheus')
    await route.fulfill({
      contentType: 'text/event-stream',
      body: [
        sse({ type: 'meta', provider: 'playwright', used_live_provider: true }),
        sse({ type: 'token', content: answer }),
        sse({
          type: 'done',
          recommendation: {
            id: 'PW-MORPHEUS',
            equipment_id: 'RM-DRIVE-01',
            diagnosis: 'Playwright diagnosis stream completed.',
            probable_root_causes: ['Validation stream'],
            risk_level: 'high',
            urgency: 'high',
            remaining_useful_life_days: 12,
            confidence: 0.82,
            immediate_actions: ['Validate scroll behavior'],
            planned_actions: ['Keep screenshot and video artifacts on failure'],
            spares_strategy: [],
            evidence: [],
            learning_notes: [],
            reasoning_explanation: null,
            used_live_provider: true,
            provider: 'playwright',
            report_summary: 'Playwright validation recommendation.',
          },
        }),
      ].join(''),
    })
  })

  await page.route('**/api/assets/RM-DRIVE-01/reliability/stream', async (route) => {
    const answer = longAnswer('Smith')
    await route.fulfill({
      contentType: 'text/event-stream',
      body: [
        sse({ type: 'meta', provider: 'playwright', used_live_provider: true }),
        sse({ type: 'token', content: answer }),
        sse({
          type: 'done',
          answer,
          prediction: {
            equipment_id: 'RM-DRIVE-01',
            risk_level: 'high',
            failure_probability: 0.72,
            remaining_useful_life_days: 18,
            drivers: ['Playwright stream validation', 'Long response overflow'],
            reasoning_explanation: null,
          },
          provider: 'playwright',
          used_live_provider: true,
        }),
      ].join(''),
    })
  })
})

test('keeps Neo, Morpheus, and Smith streams pinned while the page follows them', async ({ page }) => {
  await signIn(page)
  const primaryNav = page.getByRole('navigation', { name: 'Primary navigation' })

  await primaryNav.getByRole('button', { name: 'Command Center' }).click()
  await page.getByLabel('Ask Neo').fill('how to inspect hot strip mill main drive motor')
  await page.getByRole('button', { name: /^Send$/ }).click()
  await expect(page.getByLabel('Neo chat transcript')).toContainText('Neo validation chunk 14')
  await expectPinnedToBottom(page, '.neoTranscript')

  await page.getByRole('button', { name: /Hot Strip Mill Main Drive Motor/ }).first().click()
  await page.getByRole('button', { name: 'Run Morpheus' }).click()
  await expect(page.locator('.morpheusProgress')).toContainText('Morpheus validation chunk 14')
  await expectPinnedToBottom(page, '.morpheusProgress')

  await page.getByLabel('Asset detail tabs').getByRole('button', { name: 'Reliability' }).click()
  await expect(page.getByRole('heading', { name: 'Smith' })).toBeVisible()
  await expect(page.getByLabel('Smith failure prediction stream')).toContainText('Smith validation chunk 14')
  await expectPinnedToBottom(page, '.reliabilityPredictionStream')
})
