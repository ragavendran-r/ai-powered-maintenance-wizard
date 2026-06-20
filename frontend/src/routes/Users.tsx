import { useState } from 'react'
import { Bell, KeyRound, Trash2, UserPlus, Users } from 'lucide-react'
import type { AuthUser, NotificationCleanupResult, UserRole } from '../services/api'
import { roleLabels, roleOptions } from '../appModel'

export function UsersRoute({
  closeResetPassword,
  createNewUser,
  newUserEmail,
  newUserName,
  newUserPassword,
  newUserRole,
  notificationCleanupLoading,
  notificationCleanupResult,
  notificationCleanupRetentionDays,
  openResetPassword,
  previewNotificationCleanup,
  resetPassword,
  resetPasswordValue,
  resetUser,
  runNotificationCleanup,
  setNotificationCleanupRetentionDays,
  setNewUserEmail,
  setNewUserName,
  setNewUserPassword,
  setNewUserRole,
  setResetPasswordValue,
  toggleUserActive,
  users,
}: {
  closeResetPassword: () => void
  createNewUser: () => Promise<boolean>
  newUserEmail: string
  newUserName: string
  newUserPassword: string
  newUserRole: UserRole
  notificationCleanupLoading: boolean
  notificationCleanupResult: NotificationCleanupResult | null
  notificationCleanupRetentionDays: number
  openResetPassword: (user: AuthUser) => void
  previewNotificationCleanup: () => void
  resetPassword: () => void
  resetPasswordValue: string
  resetUser: AuthUser | null
  runNotificationCleanup: () => void
  setNotificationCleanupRetentionDays: (value: number) => void
  setNewUserEmail: (value: string) => void
  setNewUserName: (value: string) => void
  setNewUserPassword: (value: string) => void
  setNewUserRole: (value: UserRole) => void
  setResetPasswordValue: (value: string) => void
  toggleUserActive: (user: AuthUser) => void
  users: AuthUser[]
}) {
  const [isCreateUserOpen, setIsCreateUserOpen] = useState(false)

  function closeCreateUser() {
    setIsCreateUserOpen(false)
    setNewUserEmail('')
    setNewUserName('')
    setNewUserRole('operator')
    setNewUserPassword('')
  }

  async function submitCreateUser() {
    const created = await createNewUser()
    if (created) setIsCreateUserOpen(false)
  }

  return (
    <section className="detailPanel usersView">
      <div className="sectionHeader userManagementHeader">
        <span className="sectionTitleGroup">
          <Users size={18} />
          <h2>Users</h2>
        </span>
        <button className="iconTextButton" onClick={() => setIsCreateUserOpen(true)} title="Create user">
          <UserPlus size={16} />
          Create User
        </button>
      </div>
      <div className="userList" aria-label="Application users">
        {users.map((user) => (
          <div className="userRow" key={user.id}>
            <span>
              <strong>{user.display_name}</strong>
              <small>{user.email}</small>
            </span>
            <span className="rolePill">{roleLabels[user.role]}</span>
            <span className={`activePill ${user.is_active ? 'active' : 'inactive'}`}>
              {user.is_active ? 'Active' : 'Inactive'}
            </span>
            <button className="textButton subtleButton" onClick={() => toggleUserActive(user)}>
              {user.is_active ? 'Deactivate' : 'Activate'}
            </button>
            <button className="iconTextButton" onClick={() => openResetPassword(user)} title="Reset password">
              <KeyRound size={16} />
              Reset
            </button>
          </div>
        ))}
      </div>
      <section className="adminMaintenancePanel" aria-label="Notification cleanup">
        <div className="sectionHeader compactHeader">
          <span className="sectionTitleGroup">
            <Bell size={18} />
            <h3>Notification cleanup</h3>
          </span>
        </div>
        <div className="notificationCleanupGrid">
          <label className="field">
            <span>Dismissed retention days</span>
            <input
              min={0}
              max={365}
              type="number"
              value={notificationCleanupRetentionDays}
              onChange={(event) => setNotificationCleanupRetentionDays(Number(event.target.value))}
            />
          </label>
          <div className="cleanupActionRow">
            <button
              className="outlineButton"
              disabled={notificationCleanupLoading}
              onClick={previewNotificationCleanup}
              type="button"
            >
              Preview
            </button>
            <button
              className="iconTextButton dangerButton"
              disabled={notificationCleanupLoading || !notificationCleanupResult?.candidate_count}
              onClick={runNotificationCleanup}
              type="button"
            >
              <Trash2 size={16} />
              Delete candidates
            </button>
          </div>
        </div>
        {notificationCleanupResult && (
          <div className="cleanupResultPanel">
            <span>
              <strong>{notificationCleanupResult.candidate_count}</strong>
              <small>candidates</small>
            </span>
            <span>
              <strong>{notificationCleanupResult.deleted_count}</strong>
              <small>deleted</small>
            </span>
            <span>
              <strong>{notificationCleanupResult.dry_run ? 'Preview' : 'Applied'}</strong>
              <small>mode</small>
            </span>
          </div>
        )}
      </section>
      {isCreateUserOpen && (
        <div className="modalOverlay" role="presentation">
          <section className="modalPanel" role="dialog" aria-modal="true" aria-labelledby="create-user-title">
            <div className="sectionHeader compactHeader">
              <UserPlus size={18} />
              <h2 id="create-user-title">Create User</h2>
            </div>
            <div className="userDialogGrid">
              <label className="field">
                <span>Email</span>
                <input
                  autoFocus
                  value={newUserEmail}
                  onChange={(event) => setNewUserEmail(event.target.value)}
                />
              </label>
              <label className="field">
                <span>Name</span>
                <input value={newUserName} onChange={(event) => setNewUserName(event.target.value)} />
              </label>
              <label className="field">
                <span>Role</span>
                <select value={newUserRole} onChange={(event) => setNewUserRole(event.target.value as UserRole)}>
                  {roleOptions.map((role) => (
                    <option value={role} key={role}>
                      {roleLabels[role]}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span>Password</span>
                <input
                  type="password"
                  value={newUserPassword}
                  onChange={(event) => setNewUserPassword(event.target.value)}
                />
              </label>
            </div>
            <div className="modalActions">
              <button className="outlineButton" onClick={closeCreateUser}>
                Cancel
              </button>
              <button className="iconTextButton" onClick={submitCreateUser}>
                <UserPlus size={16} />
                Create
              </button>
            </div>
          </section>
        </div>
      )}
      {resetUser && (
        <div className="modalOverlay" role="presentation">
          <section className="modalPanel" role="dialog" aria-modal="true" aria-labelledby="reset-password-title">
            <div className="sectionHeader compactHeader">
              <KeyRound size={18} />
              <h2 id="reset-password-title">Reset Password</h2>
            </div>
            <p className="modalContext">
              {resetUser.display_name}
              <small>{resetUser.email}</small>
            </p>
            <label className="field">
              <span>New Password</span>
              <input
                autoFocus
                type="password"
                value={resetPasswordValue}
                onChange={(event) => setResetPasswordValue(event.target.value)}
              />
            </label>
            <div className="modalActions">
              <button className="outlineButton" onClick={closeResetPassword}>
                Cancel
              </button>
              <button className="iconTextButton" onClick={resetPassword}>
                <KeyRound size={16} />
                Reset
              </button>
            </div>
          </section>
        </div>
      )}
    </section>
  )
}
