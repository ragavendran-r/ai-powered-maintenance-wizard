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
    name: 'admin ingestion',
    open: async (page) => {
      await primaryNavButton(page, 'Admin').click()
    },
    visible: async (page) => {
      await expect(page.getByRole('heading', { name: 'Ingestion' })).toBeVisible()
      await expect(page.getByLabel('Ingestion JSON')).toBeVisible()
      await expect(page.getByRole('button', { name: 'Upload' })).toBeVisible()
      await expect(page.getByRole('button', { name: 'Import JSON' })).toBeVisible()
    },
  },
  {
    name: 'learning review',
    open: async (page) => {
      await primaryNavButton(page, 'Learning and Tuning').click()
    },
    visible: async (page) => {
      await expect(page.getByRole('heading', { name: 'Learning and Tuning' })).toBeVisible()
      await expect(page.getByText('RAG vector DB')).toBeVisible()
      await expect(page.getByRole('heading', { name: 'Approved Controls' })).toBeVisible()
      await expect(page.getByRole('heading', { name: 'Model and Prompt Versions' })).toBeVisible()
      const learningPanelOverlapArea = await page.evaluate(() => {
        const panels = Array.from(document.querySelectorAll('.learningGrid .learningPanel')).slice(0, 2)
        if (panels.length < 2) return 0
        const [leftPanel, rightPanel] = panels.map((panel) => panel.getBoundingClientRect())
        const overlapWidth = Math.max(0, Math.min(leftPanel.right, rightPanel.right) - Math.max(leftPanel.left, rightPanel.left))
        const overlapHeight = Math.max(0, Math.min(leftPanel.bottom, rightPanel.bottom) - Math.max(leftPanel.top, rightPanel.top))
        return overlapWidth * overlapHeight
      })
      expect(learningPanelOverlapArea).toBe(0)
      const maxExampleCardOverflow = await page.evaluate(() => {
        return Math.max(
          0,
          ...Array.from(document.querySelectorAll('.learningExample')).map((example) => {
            const panel = example.closest('.learningPanel')
            if (!panel) return 0
            const exampleBounds = example.getBoundingClientRect()
            const panelBounds = panel.getBoundingClientRect()
            return Math.max(0, exampleBounds.right - panelBounds.right, panelBounds.left - exampleBounds.left)
          }),
        )
      })
      expect(maxExampleCardOverflow).toBeLessThanOrEqual(1)
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
