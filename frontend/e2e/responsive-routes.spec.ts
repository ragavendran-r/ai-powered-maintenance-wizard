import { expect, test, type Page } from '@playwright/test'
import {
  expectNoDocumentHorizontalOverflow,
  openAssetDetail,
  primaryNavButton,
  signInAs,
} from './maintenance-fixtures'

type ViewportCase = {
  name: string
  width: number
  height: number
}

type RouteCase = {
  name: string
  open: (page: Page) => Promise<void>
  visible: (page: Page) => Promise<void>
}

const viewports: ViewportCase[] = [
  { name: 'desktop', width: 1280, height: 720 },
  { name: 'tablet', width: 820, height: 900 },
  { name: 'mobile', width: 390, height: 844 },
]

const routeCases: RouteCase[] = [
  {
    name: 'dashboard',
    open: async () => {},
    visible: async (page) => {
      await expect(page.getByLabel('Dashboard KPI summary')).toBeVisible()
      await expect(page.getByLabel('Neo dashboard assistant')).toBeVisible()
      await expect(page.getByText('Health score (%)')).toBeVisible()
      await expect(page.getByText('Equipment group')).toBeVisible()
      await expect(page.getByText('SLA compliance (%)')).toBeVisible()
      await expect(page.getByText('Incident priority', { exact: true })).toBeVisible()
      const equipmentChart = page.locator('.dashboardEfficiency')
      const slaChart = page.locator('.slaPanel')
      await expect(equipmentChart).not.toHaveCSS('position', 'sticky')
      await slaChart.scrollIntoViewIfNeeded()
      const overlapArea = await page.evaluate(() => {
        const equipment = document.querySelector('.dashboardEfficiency')?.getBoundingClientRect()
        const sla = document.querySelector('.slaPanel')?.getBoundingClientRect()
        if (!equipment || !sla) return 0
        const overlapWidth = Math.max(0, Math.min(equipment.right, sla.right) - Math.max(equipment.left, sla.left))
        const overlapHeight = Math.max(0, Math.min(equipment.bottom, sla.bottom) - Math.max(equipment.top, sla.top))
        return overlapWidth * overlapHeight
      })
      expect(overlapArea).toBe(0)
    },
  },
  {
    name: 'asset detail',
    open: openAssetDetail,
    visible: async (page) => {
      await expect(page.getByRole('heading', { name: 'Asset profile' })).toBeVisible()
      await expect(page.getByRole('heading', { name: 'Diagnosis and recommendation' })).toBeVisible()
    },
  },
  {
    name: 'work orders',
    open: async (page) => {
      await primaryNavButton(page, 'Work Orders').click()
    },
    visible: async (page) => {
      await expect(page.getByRole('heading', { name: 'WOs with follow up actions' })).toBeVisible()
      await expect(page.getByRole('heading', { name: /Work Order/ })).toBeVisible()
    },
  },
  {
    name: 'ingestion',
    open: async (page) => {
      await primaryNavButton(page, 'Ingestion').click()
    },
    visible: async (page) => {
      await expect(page.getByRole('heading', { name: 'Ingestion' })).toBeVisible()
      await expect(page.getByLabel('Ingestion JSON')).toBeVisible()
    },
  },
  {
    name: 'learning review',
    open: async (page) => {
      await primaryNavButton(page, 'Learning').click()
    },
    visible: async (page) => {
      await expect(page.getByRole('heading', { name: 'Learning and Tuning' })).toBeVisible()
      await expect(page.getByText('RAG vector DB')).toBeVisible()
    },
  },
]

for (const viewport of viewports) {
  test.describe(`${viewport.name} responsive routes`, () => {
    test.use({ viewport: { width: viewport.width, height: viewport.height } })

    for (const routeCase of routeCases) {
      test(`${routeCase.name} remains usable without document overflow`, async ({ page }) => {
        await signInAs(page, 'admin')

        await routeCase.open(page)
        await routeCase.visible(page)
        await expect(page.locator('.appShell')).toBeVisible()
        await expectNoDocumentHorizontalOverflow(page)
      })
    }
  })
}
