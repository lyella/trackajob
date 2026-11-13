import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'

export type Theme = 'light' | 'dark'

const STORAGE_KEY = 'trackajob-theme'

/** Light is the default for everyone. We deliberately do NOT follow the OS
 * preference automatically: a job tracker is a document tool, and a user who
 * has never chosen should get the light "paper" look. Their explicit choice
 * is remembered and wins from then on. */
function readStored(): Theme | null {
  try {
    const value = localStorage.getItem(STORAGE_KEY)
    return value === 'dark' || value === 'light' ? value : null
  } catch {
    return null
  }
}

function apply(theme: Theme) {
  const root = document.documentElement
  root.dataset.theme = theme
  root.style.colorScheme = theme
  const meta = document.querySelector('meta[name="theme-color"]')
  if (meta) meta.setAttribute('content', theme === 'dark' ? '#14140f' : '#f7f4ec')
}

const ThemeContext = createContext<{ theme: Theme; toggle: () => void; setTheme: (t: Theme) => void }>(
  { theme: 'light', toggle: () => {}, setTheme: () => {} }
)

export function useTheme() {
  return useContext(ThemeContext)
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(() => readStored() ?? 'light')

  useEffect(() => {
    apply(theme)
  }, [theme])

  const setTheme = useCallback((next: Theme) => {
    setThemeState(next)
    try {
      localStorage.setItem(STORAGE_KEY, next)
    } catch {
      /* private mode: the choice just does not persist */
    }
  }, [])

  const toggle = useCallback(() => {
    setThemeState((current) => {
      const next: Theme = current === 'light' ? 'dark' : 'light'
      try {
        localStorage.setItem(STORAGE_KEY, next)
      } catch {
        /* ignore */
      }
      return next
    })
  }, [])

  return (
    <ThemeContext.Provider value={{ theme, toggle, setTheme }}>{children}</ThemeContext.Provider>
  )
}

export function ThemeToggle() {
  const { theme, toggle } = useTheme()
  const isDark = theme === 'dark'
  return (
    <button
      type="button"
      className="theme-toggle"
      onClick={toggle}
      aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
      aria-pressed={isDark}
      title={isDark ? 'Light mode' : 'Dark mode'}
    >
      <span className="theme-toggle-track" aria-hidden="true">
        <span className="theme-toggle-thumb">{isDark ? '☾' : '☀'}</span>
      </span>
    </button>
  )
}
