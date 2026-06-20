import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import type { AuthUser } from '../services/api'
import { UsersRoute } from './Users'

const adminUser: AuthUser = {
  id: 'U-ADMIN',
  email: 'admin@plant.local',
  display_name: 'Admin User',
  role: 'admin',
  is_active: true,
  created_at: '2026-06-18T10:00:00+05:30',
  updated_at: '2026-06-18T10:00:00+05:30',
}

const operatorUser: AuthUser = {
  id: 'U-OPERATOR',
  email: 'operator@plant.local',
  display_name: 'Jan',
  role: 'operator',
  is_active: true,
  created_at: '2026-06-18T10:00:00+05:30',
  updated_at: '2026-06-18T10:00:00+05:30',
}

function renderMockedUsers(overrides: Record<string, unknown> = {}) {
  const props = {
    closeResetPassword: vi.fn(),
    createNewUser: vi.fn().mockResolvedValue(true),
    newUserEmail: '',
    newUserName: '',
    newUserPassword: '',
    newUserRole: 'operator',
    notificationCleanupLoading: false,
    notificationCleanupResult: null,
    notificationCleanupRetentionDays: 7,
    openResetPassword: vi.fn(),
    previewNotificationCleanup: vi.fn(),
    resetPassword: vi.fn(),
    resetPasswordValue: '',
    resetUser: null,
    runNotificationCleanup: vi.fn(),
    setNotificationCleanupRetentionDays: vi.fn(),
    setNewUserEmail: vi.fn(),
    setNewUserName: vi.fn(),
    setNewUserPassword: vi.fn(),
    setNewUserRole: vi.fn(),
    setResetPasswordValue: vi.fn(),
    toggleUserActive: vi.fn(),
    users: [adminUser, operatorUser],
    ...overrides,
  }
  render(<UsersRoute {...props} />)
  return props
}

afterEach(() => cleanup())

it('opens the create user dialog and routes entered fields through callbacks', async () => {
  const props = renderMockedUsers()

  expect(screen.queryByRole('dialog', { name: 'Create User' })).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Create User' }))

  const dialog = screen.getByRole('dialog', { name: 'Create User' })
  fireEvent.change(within(dialog).getByLabelText('Email'), { target: { value: 'new.operator@plant.local' } })
  fireEvent.change(within(dialog).getByLabelText('Name'), { target: { value: 'New Operator' } })
  fireEvent.change(within(dialog).getByLabelText('Password'), { target: { value: 'NewOperator123!' } })
  fireEvent.change(within(dialog).getByLabelText('Role'), { target: { value: 'maintenance_technician' } })
  fireEvent.click(within(dialog).getByRole('button', { name: 'Create' }))

  expect(props.setNewUserEmail).toHaveBeenCalledWith('new.operator@plant.local')
  expect(props.setNewUserName).toHaveBeenCalledWith('New Operator')
  expect(props.setNewUserPassword).toHaveBeenCalledWith('NewOperator123!')
  expect(props.setNewUserRole).toHaveBeenCalledWith('maintenance_technician')
  expect(props.createNewUser).toHaveBeenCalled()
  expect(await screen.findByRole('heading', { name: 'Users' })).toBeInTheDocument()
  expect(screen.queryByRole('dialog', { name: 'Create User' })).not.toBeInTheDocument()
})

it('keeps the create user dialog open when creation fails', async () => {
  renderMockedUsers({ createNewUser: vi.fn().mockResolvedValue(false) })

  fireEvent.click(screen.getByRole('button', { name: 'Create User' }))
  fireEvent.click(within(screen.getByRole('dialog', { name: 'Create User' })).getByRole('button', { name: 'Create' }))

  expect(await screen.findByRole('dialog', { name: 'Create User' })).toBeInTheDocument()
})

it('opens password reset in a dialog instead of inline user rows', () => {
  const props = renderMockedUsers()

  expect(screen.queryByLabelText('New Password')).not.toBeInTheDocument()
  fireEvent.click(screen.getAllByRole('button', { name: 'Reset' })[0])
  expect(props.openResetPassword).toHaveBeenCalledWith(adminUser)
})

it('routes password reset dialog input and cancel actions', () => {
  const props = renderMockedUsers({ resetUser: operatorUser })

  const dialog = screen.getByRole('dialog', { name: 'Reset Password' })
  expect(within(dialog).getByText('Jan')).toBeInTheDocument()
  expect(within(dialog).getByLabelText('New Password')).toBeInTheDocument()

  fireEvent.change(within(dialog).getByLabelText('New Password'), { target: { value: 'Replacement123!' } })
  expect(props.setResetPasswordValue).toHaveBeenCalledWith('Replacement123!')

  fireEvent.click(within(dialog).getByRole('button', { name: 'Reset' }))
  expect(props.resetPassword).toHaveBeenCalled()

  fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }))
  expect(props.closeResetPassword).toHaveBeenCalled()
})

it('routes notification cleanup preview and delete actions', () => {
  const props = renderMockedUsers({
    notificationCleanupResult: {
      dry_run: true,
      dismissed_retention_days: 7,
      delete_superseded_assignments: true,
      delete_dismissed_direct_notifications: true,
      candidate_count: 2,
      deleted_count: 0,
      candidates: [],
      deleted_ids: [],
      vector_index_result: null,
    },
  })

  fireEvent.change(screen.getByLabelText('Dismissed retention days'), { target: { value: '14' } })
  fireEvent.click(screen.getByRole('button', { name: 'Preview' }))
  fireEvent.click(screen.getByRole('button', { name: 'Delete candidates' }))

  expect(props.setNotificationCleanupRetentionDays).toHaveBeenCalledWith(14)
  expect(props.previewNotificationCleanup).toHaveBeenCalled()
  expect(props.runNotificationCleanup).toHaveBeenCalled()
  expect(screen.getByText('2')).toBeInTheDocument()
  expect(screen.getByText('candidates')).toBeInTheDocument()
})
