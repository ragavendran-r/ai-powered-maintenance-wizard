import type { FormEvent } from 'react'
import { Database, LogIn, LogOut, ShieldAlert } from 'lucide-react'
import type { AuthUser } from '../services/api'

export function AuthLoadingRoute() {
  return (
    <main className="loginShell">
      <section className="loginPanel">
        <div className="sectionHeader">
          <ShieldAlert size={20} />
          <h1>Maintenance Wizard</h1>
        </div>
        <p className="emptyState">Checking session...</p>
      </section>
    </main>
  )
}

export function LoginRoute({
  authMessage,
  loginEmail,
  loginPassword,
  onLogin,
  setLoginEmail,
  setLoginPassword,
}: {
  authMessage: string
  loginEmail: string
  loginPassword: string
  onLogin: (event: FormEvent<HTMLFormElement>) => void
  setLoginEmail: (value: string) => void
  setLoginPassword: (value: string) => void
}) {
  return (
    <main className="loginShell">
      <form className="loginPanel" onSubmit={onLogin}>
        <div className="sectionHeader">
          <ShieldAlert size={20} />
          <h1>Maintenance Wizard</h1>
        </div>
        <p className="eyebrow">Steel Plant Maintenance</p>
        <label className="field">
          <span>Email</span>
          <input value={loginEmail} onChange={(event) => setLoginEmail(event.target.value)} />
        </label>
        <label className="field">
          <span>Password</span>
          <input type="password" value={loginPassword} onChange={(event) => setLoginPassword(event.target.value)} />
        </label>
        <button className="loginButton" type="submit">
          <LogIn size={18} />
          Sign In
        </button>
        <p className="demoHint">Demo users use password DemoPass123!</p>
        {authMessage && <p className="inlineStatus errorText">{authMessage}</p>}
      </form>
    </main>
  )
}

export function ApiOnlyRoute({
  currentUser,
  onLogout,
}: {
  currentUser: AuthUser
  onLogout: () => void
}) {
  return (
    <main className="appShell">
      <header className="topBar">
        <div>
          <p className="eyebrow">Steel Plant Maintenance</p>
          <h1>Maintenance Wizard</h1>
        </div>
        <button className="logoutButton" onClick={onLogout}>
          <LogOut size={16} />
          Logout
        </button>
      </header>
      <section className="detailPanel apiOnlyPanel">
        <div className="sectionHeader">
          <Database size={18} />
          <h2>{currentUser.display_name}</h2>
        </div>
        <p className="emptyState">This account is enabled for API ingestion and does not have application navigation.</p>
      </section>
    </main>
  )
}
