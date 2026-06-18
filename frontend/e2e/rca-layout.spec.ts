import { expect, test, type Page } from '@playwright/test'
import { expectNoDocumentHorizontalOverflow, primaryNavButton, signInAs } from './maintenance-fixtures'

async function expectFitsViewport(page: Page, selector: string) {
  const metrics = await page.locator(selector).evaluate((element) => {
    const rect = element.getBoundingClientRect()
    const elementRight = rect.right
    const overflowers = Array.from(element.querySelectorAll('*'))
      .map((child) => {
        const childRect = child.getBoundingClientRect()
        return {
          className: child.getAttribute('class') ?? '',
          tagName: child.tagName.toLowerCase(),
          text: (child.textContent ?? '').trim().slice(0, 80),
          overBy: Math.round(childRect.right - elementRight),
        }
      })
      .filter((item) => item.overBy > 2)
      .slice(0, 8)
    return {
      clientWidth: element.clientWidth,
      right: rect.right,
      scrollWidth: element.scrollWidth,
      viewportWidth: window.innerWidth,
      overflowers,
    }
  })

  expect(metrics.right).toBeLessThanOrEqual(metrics.viewportWidth + 2)
  expect(
    metrics.scrollWidth - metrics.clientWidth,
    `${selector} overflowers: ${JSON.stringify(metrics.overflowers)}`,
  ).toBeLessThanOrEqual(2)
}

test('RCA workspace stays within the desktop content column and streams Morpheus drafts', async ({ page }) => {
  await signInAs(page, 'reliability')

  await primaryNavButton(page, 'Reliability').click()
  await expect(page.getByRole('heading', { name: 'RCA Workspace' })).toBeVisible()
  await expect(page.locator('.rcaCaseTitle strong', { hasText: 'Drive-end vibration root cause review' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Evidence Timeline' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Learning and Tuning' })).toHaveCount(0)
  await page.getByRole('button', { name: 'Morpheus draft selected RCA' }).click()
  await expect(page.getByRole('heading', { name: 'Morpheus live draft' })).toBeVisible()
  await expect(page.getByLabel('Morpheus RCA draft stream')).toContainText('Drive-end bearing looseness remains the leading candidate.')

  await expectNoDocumentHorizontalOverflow(page)
  await expectFitsViewport(page, '.reliabilityRouteStack')
  await expectFitsViewport(page, '.rcaWorkspace')
  await expect(
    page.getByRole('complementary', { name: 'Maintenance navigation' }).getByRole('button', { name: 'Learning and Tuning' }),
  ).toHaveCount(0)
})
