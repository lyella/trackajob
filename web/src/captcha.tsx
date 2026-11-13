import { useEffect, useRef, useState } from 'react'
import { api } from './types'

/** Cloudflare Turnstile widget.
 *
 * Loads the Cloudflare script once, renders the widget into a div, and hands
 * the token up. When captcha is not configured the component renders nothing
 * and the caller sends no token, which the API accepts outside production.
 *
 * The token is single-use, so every failed submit must reset the widget,
 * otherwise the user retries with a spent token and sees a confusing error.
 */

type TurnstileApi = {
  render: (
    el: HTMLElement,
    opts: {
      sitekey: string
      callback: (token: string) => void
      'expired-callback'?: () => void
      'error-callback'?: () => void
      theme?: 'light' | 'dark' | 'auto'
      appearance?: 'always' | 'execute' | 'interaction-only'
    }
  ) => string
  reset: (id?: string) => void
  remove: (id?: string) => void
}

declare global {
  interface Window {
    turnstile?: TurnstileApi
  }
}

let scriptPromise: Promise<void> | null = null

function loadScript(): Promise<void> {
  if (window.turnstile) return Promise.resolve()
  if (scriptPromise) return scriptPromise
  scriptPromise = new Promise<void>((resolve, reject) => {
    const script = document.createElement('script')
    script.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit'
    script.async = true
    script.defer = true
    script.onload = () => resolve()
    script.onerror = () => reject(new Error('Could not load the bot check.'))
    document.head.appendChild(script)
  })
  return scriptPromise
}

export function useCaptchaConfig() {
  const [config, setConfig] = useState<{ enabled: boolean; siteKey: string } | null>(null)
  useEffect(() => {
    api<{ captcha_enabled: boolean; captcha_site_key: string }>('/api/auth/config')
      .then((c) => setConfig({ enabled: c.captcha_enabled, siteKey: c.captcha_site_key }))
      .catch(() => setConfig({ enabled: false, siteKey: '' }))
  }, [])
  return config
}

export function Captcha({
  siteKey,
  onToken,
  theme,
}: {
  siteKey: string
  onToken: (token: string | null) => void
  theme: 'light' | 'dark'
}) {
  const ref = useRef<HTMLDivElement>(null)
  const widgetId = useRef<string | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    loadScript()
      .then(() => {
        if (cancelled || !ref.current || !window.turnstile) return
        widgetId.current = window.turnstile.render(ref.current, {
          sitekey: siteKey,
          theme,
          callback: (token) => onToken(token),
          'expired-callback': () => onToken(null),
          'error-callback': () => {
            onToken(null)
            setError('The bot check could not load. Refresh the page and try again.')
          },
        })
      })
      .catch(() => setError('The bot check could not load. Refresh the page and try again.'))

    return () => {
      cancelled = true
      if (widgetId.current && window.turnstile) {
        window.turnstile.remove(widgetId.current)
        widgetId.current = null
      }
    }
    // The widget is rendered once per mount; token changes flow up via callback.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [siteKey, theme])

  return (
    <div className="captcha">
      <div ref={ref} />
      {error && <p className="field-error">{error}</p>}
    </div>
  )
}

/** Resets a widget after a failed submit so the next attempt has a fresh token. */
export function resetCaptcha(onToken: (t: string | null) => void) {
  if (window.turnstile) window.turnstile.reset()
  onToken(null)
}
