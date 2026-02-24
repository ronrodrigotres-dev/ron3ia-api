import React from 'react'
import { analyzeWebsite, createCheckoutSession } from '../lib/api'

type BasicResult = {
  summary?: string
  errors_detected?: string[]
  preview?: Record<string, unknown>
  report_id?: string
}

export default function App() {
  const [url, setUrl] = React.useState('')
  const [email, setEmail] = React.useState('')
  const [loading, setLoading] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [result, setResult] = React.useState<BasicResult | null>(null)
  const [reportId, setReportId] = React.useState<string | null>(null)
  const [checkingOut, setCheckingOut] = React.useState(false)

  async function runDiagnostic() {
    setError(null)
    setResult(null)
    setReportId(null)
    setLoading(true)
    try {
      const data = await analyzeWebsite(url.trim())
      const r = data?.result ?? data
      setResult(r)
      setReportId(data?.report_id ?? r?.report_id ?? null)
    } catch (e: any) {
      setError(e?.message ?? 'Error inesperado')
    } finally {
      setLoading(false)
    }
  }

  async function handleStripeCheckout() {
    setError(null)
    setCheckingOut(true)
    try {
      if (!reportId) throw new Error('Falta report_id. Ejecuta el diagnóstico primero.')
      const { checkout_url } = await createCheckoutSession({ email: email.trim(), report_id: reportId })
      window.location.href = checkout_url
    } catch (e: any) {
      setError(e?.message ?? 'No se pudo iniciar el checkout')
      setCheckingOut(false)
    }
  }

  const hasResult = Boolean(result)
  const emailOk = /^\S+@\S+\.\S+$/.test(email.trim())

  return (
    <div className="ron3ia-wrap">
      <div className="ron3ia-header">
        <div>
          <h1 className="ron3ia-title">RON3IA</h1>
          <p className="ron3ia-subtitle">Diagnóstico gratuito → Veredicto premium</p>
        </div>
      </div>

      <div className="panel">
        <div className="row">
          <input
            className="input"
            placeholder="Pega tu URL (https://...)"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
          />
          <button className="btn" disabled={loading || !url.trim()} onClick={runDiagnostic}>
            {loading ? 'Analizando…' : 'EMITIR VEREDICTO'}
          </button>
        </div>

        {error && <div className="result">{error}</div>}

        {hasResult && (
          <>
            <div className="result">
              {result?.summary ? `${result.summary}\n\n` : ''}
              {Array.isArray(result?.errors_detected) && result.errors_detected.length > 0
                ? `Errores detectados:\n- ${result.errors_detected.join('\n- ')}\n\n`
                : 'Errores detectados: (no se detectaron en el básico)\n\n'}
              {result?.preview ? `Resumen técnico:\n${JSON.stringify(result.preview, null, 2)}` : ''}
            </div>

            <div className="row" style={{ marginTop: 12 }}>
              <input
                className="input"
                placeholder="Tu email (para recibir el veredicto)"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>

            {/* Paywall CTA */}
            <button
              className="glass-button"
              onClick={handleStripeCheckout}
              disabled={checkingOut || !emailOk || !reportId}
            >
              {checkingOut ? 'Abriendo checkout…' : 'ACCEDER AL VEREDICTO'}
            </button>
            <div className="premium-hint">
              El análisis ya está listo. Solo falta desbloquear el veredicto premium.
            </div>
          </>
        )}
      </div>
    </div>
  )
}

