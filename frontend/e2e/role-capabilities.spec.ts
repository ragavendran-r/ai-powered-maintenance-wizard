import { expect, test, type Page } from '@playwright/test'
import {
  openAssetDetail,
  primaryNavButton,
  roleUsers,
  signInAs,
  type RoleKey,
} from './maintenance-fixtures'

async function expectPrimaryNav(page: Page, visible: string[], hidden: string[]) {
  for (const label of visible) {
    await expect(primaryNavButton(page, label)).toBeVisible()
  }
  for (const label of hidden) {
    await expect(primaryNavButton(page, label)).toHaveCount(0)
  }
}

test.describe('role capability rendering', () => {
  test('operator keeps read-only navigation and hides action surfaces', async ({ page }) => {
    await signInAs(page, 'operator')

    await expectPrimaryNav(page, ['Command Center', 'Assets'], ['Work Execution', 'Planning', 'Reports', 'Reliability', 'Learning and Tuning', 'Admin'])
    await expect(page.getByRole('button', { name: 'Create work order' })).toHaveCount(0)
    await expect(page.getByRole('button', { name: 'Review follow-ups' })).toHaveCount(0)
    await expect(page.getByLabel('Technician execution workflow')).toHaveCount(0)
    await expect(page.getByRole('button', { name: /^Approve WO-/ })).toHaveCount(0)
  })

  test('technician sees assigned execution workflow and technician assistant only', async ({ page }) => {
    await signInAs(page, 'technician')

    await expectPrimaryNav(page, ['Command Center', 'Assets', 'Work Execution'], ['Planning', 'Reports', 'Reliability', 'Learning and Tuning', 'Admin'])
    await expect(page.getByRole('button', { name: 'Create work order' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Review follow-ups' })).toHaveCount(0)

    await primaryNavButton(page, 'Work Execution').click()
    await expect(page.getByLabel('Technician execution workflow')).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Technician Execution' })).toBeVisible()
    await expect(page.getByLabel('Technician observation')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Start work' })).toBeEnabled()
    await expect(page.getByLabel('Supervisor question')).toHaveCount(0)
    await expect(page.getByRole('button', { name: /^Approve WO-/ })).toHaveCount(0)
  })

  test('supervisor sees review, assignment, and approval controls', async ({ page }) => {
    await signInAs(page, 'supervisor')

    await expectPrimaryNav(page, ['Command Center', 'Assets', 'Work Execution', 'Planning', 'Reports'], ['Reliability', 'Learning and Tuning', 'Admin'])
    await expect(page.getByRole('button', { name: 'Create work order' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Review follow-ups' })).toBeVisible()

    await primaryNavButton(page, 'Work Execution').click()
    await expect(page.getByLabel('Supervisor question')).toBeVisible()
    await expect(page.getByLabel('Technician observation')).toHaveCount(0)
    await expect(page.getByRole('button', { name: 'Approve WO-8311' })).toBeVisible()
    await expect(page.getByLabel('Technician execution workflow')).toHaveCount(0)

    await primaryNavButton(page, 'Planning').click()
    await expect(page.getByLabel('Assign WO-8304')).toBeVisible()
  })

  test('engineer sees decision support without admin learning or user management', async ({ page }) => {
    await signInAs(page, 'engineer')

    await expectPrimaryNav(page, ['Command Center', 'Assets', 'Reports', 'Reliability'], ['Work Execution', 'Planning', 'Learning and Tuning', 'Admin'])
    await expect(page.getByRole('button', { name: 'Create work order' })).toBeVisible()

    await openAssetDetail(page)
    await expect(page.getByRole('button', { name: 'Run Morpheus' })).toBeVisible()
    await expect(page.locator('.summaryActions').getByRole('button', { name: 'Create work order' })).toBeVisible()
  })

  test('reliability engineer sees reliability decision support without admin learning controls', async ({ page }) => {
    await signInAs(page, 'reliability')

    await expectPrimaryNav(page, ['Command Center', 'Assets', 'Reports', 'Reliability'], ['Work Execution', 'Planning', 'Learning and Tuning', 'Admin'])
    await openAssetDetail(page)
    await expect(page.getByRole('button', { name: 'Run Morpheus' })).toBeVisible()
    await page.getByRole('tablist', { name: 'Asset detail tabs' }).getByRole('tab', { name: 'Reliability' }).click()
    const predictionEvidence = page.getByLabel('Prediction model evidence')
    await expect(predictionEvidence).toBeVisible()
    await expect(predictionEvidence.getByText(/Maintenance Wizard RUL Risk Model/)).toBeVisible()
    await expect(predictionEvidence.getByText(/precision.*recall/)).toBeVisible()
    await expect(predictionEvidence.getByText(/probability/)).toBeVisible()

    await primaryNavButton(page, 'Reliability').click()
    await expect(page.getByRole('heading', { name: 'RCA Workspace' })).toBeVisible()
  })

  test('planner sees scheduling and dispatch controls without assistant panels', async ({ page }) => {
    await signInAs(page, 'planner')

    await expectPrimaryNav(page, ['Command Center', 'Assets', 'Work Execution', 'Planning', 'Reports'], ['Reliability', 'Learning and Tuning', 'Admin'])
    await expect(page.getByRole('button', { name: 'Create work order' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Review follow-ups' })).toHaveCount(0)

    await primaryNavButton(page, 'Planning').click()
    await expect(page.getByLabel('Preventive maintenance planning')).toBeVisible()
    await expect(page.getByLabel('Work order right pane')).toHaveCount(0)
    await expect(page.getByRole('heading', { name: 'Preventive Maintenance Plans' })).toBeVisible()
    await page.getByRole('button', { name: 'Morpheus PM draft' }).click()
    await expect(page.getByRole('heading', { name: 'Morpheus PM live draft' })).toBeVisible()
    await expect(page.getByText(/opening the PM draft stream/i)).toHaveCount(0)
    await expect(page.getByText(/PM context is ready/i)).toHaveCount(0)
    await expect(page.getByText('Monitoring Thresholds').first()).toBeVisible()
    await expect(page.getByText('Main drive proactive PM plan').first()).toBeVisible()
    await expect(page.getByText('Confirm LOTO and permits.')).toBeVisible()
    if (await page.getByLabel('PM plans pagination').count()) {
      await expect(page.getByLabel('PM plans pagination')).toContainText(/Rows 1-5 of \d+/)
    }
    await page.getByRole('tab', { name: 'Schedule & dispatch' }).click()
    await expect(page.getByLabel('Maintenance planning and dispatch board')).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Planning, Scheduling & Dispatch' })).toBeVisible()
    await page.getByLabel('Select work order for planning').selectOption('WO-8304')
    await expect(page.getByLabel('WO-8304 planner card')).toBeVisible()
    await expect(page.getByLabel('WO-8311 planner card')).toHaveCount(0)
    await expect(page.getByLabel('Planned start WO-8304')).toHaveAttribute('type', 'datetime-local')
    await expect(page.getByRole('button', { name: 'Dispatch' }).first()).toBeEnabled()
    await expect(page.getByLabel('Technician observation')).toHaveCount(0)
    await expect(page.getByLabel('Supervisor question')).toHaveCount(0)
  })

  test('planner opens structured maintenance reports', async ({ page }) => {
    await signInAs(page, 'planner')

    await primaryNavButton(page, 'Reports').click()

    await expect(page.getByRole('heading', { name: 'Structured Maintenance Insights and Reports' })).toBeVisible()
    await expect(page.getByText(/LLM-dependent report content is limited to recommendation Markdown exports/)).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Structured Maintenance Reports' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Abnormal Alert Reports' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Engineer Maintenance Decision Summary' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Supervisor Maintenance Decision Summary' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Equipment Digital Maintenance Log Entries' })).toBeVisible()
    await expect(page.getByText('Hot Strip Mill Main Drive Motor is at critical risk with 18% health')).toBeVisible()
    await expect(page.getByText('Escalate for same-shift maintenance review.')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Export Markdown' })).toBeEnabled()

    const downloadPromise = page.waitForEvent('download')
    await page.getByRole('button', { name: 'Export Markdown' }).click()
    const download = await downloadPromise
    expect(download.suggestedFilename()).toBe('plant-maintenance-insights.md')
    await expect(page.getByText('Structured maintenance insights downloaded')).toBeVisible()
  })

  test('admin sees administration surfaces and global review routes', async ({ page }) => {
    await signInAs(page, 'admin')

    await expectPrimaryNav(page, ['Command Center', 'Assets', 'Work Execution', 'Planning', 'Reports', 'Reliability', 'Admin'], ['Learning and Tuning'])
    await primaryNavButton(page, 'Admin').click()
    await expect(page.getByRole('heading', { name: 'Ingestion' })).toBeVisible()
    await expect(page.getByRole('tab', { name: 'Learning and Tuning' })).toBeVisible()
    await page.getByRole('tab', { name: 'User management' }).click()
    await expect(page.getByRole('heading', { name: 'Users' })).toBeVisible()
    await expect(page.getByLabel('Application users')).toContainText(roleUsers.operator.display_name)
    await expect(page.getByTitle('Create user')).toBeVisible()
  })

  test('covers all requested role personas', async () => {
    const requestedRoles: RoleKey[] = ['operator', 'technician', 'supervisor', 'engineer', 'reliability', 'planner', 'admin']
    expect(requestedRoles.map((role) => roleUsers[role].role)).toEqual([
      'operator',
      'maintenance_technician',
      'maintenance_supervisor',
      'maintenance_engineer',
      'reliability_engineer',
      'planner',
      'admin',
    ])
  })
})
