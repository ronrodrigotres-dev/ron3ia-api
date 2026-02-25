import React from 'react'
import { BrowserRouter, Link, Route, Routes, useParams, useSearchParams } from 'react-router-dom'
import {
  createCheckoutSession,
  createRepairCheckoutSession,
  emitVerdict,
  getReport,
  getReportStatus,
  type AnalyzeResult,
} from '../lib/api'

const MODULES = [
  'Intelligence',
  'Conversion',
  'SEO',
  'Growth',
  'Commerce',
  'Expansion',
  'GEO',
] as const

function DiagnosticPage() {
  const [dominio, setDominio] = React.useState('')
  const [nombre, setNombre] = React.useState('')
  const [email, setEmail] = React.useState('')
  const [selectedModules, setSelectedModules] = React.useState<string[]>([])
  const [loading, setLoading] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [result, setResult] = React.useState<AnalyzeResult | null>(null)
  const [checkingOut, setCheckingOut] = React.useState(false)

  function toggleModule(m: string) {
    setSelectedModules((prev) => (prev.includes(m) ? prev.filter((x) => x !== m) : [...prev, m]))
  }

  async function emitirVeredicto() {
    setError(null)
    setResult(null)
    setLoading(true)
    try {
      const data = await emitVerdict({
        dominio: dominio.trim(),
        nombre: nombre.trim(),
        email: email.trim(),
        selectedModules,
      })
      setResult(data.result)
    } catch (e: any) {
      setError(e?.message ?? 'Error inesperado')
    } finally {
      setLoading(false)
    }
  }

  async function handleStripeCheckout() {
    if (!result?.report_id) return
    setError(null)
    setCheckingOut(true)
    try {
      const { checkout_url } = await createCheckoutSession(result.report_id, email.trim())
      window.location.href = checkout_url
    } catch (e: any) {
      setError(e?.message ?? 'No se pudo iniciar el checkout')
      setCheckingOut(false)
    }
  }

  const hasResult = Boolean(result)
  const totalUsd = selectedModules.length * 29

  return (
    <div className="ron3ia-wrap">
      <div className="ron3ia-header">
        <div>
          <h1 className="ron3ia-title">RON3IA</h1>
          <p className="ron3ia-subtitle">Diagnóstico gratuito → Veredicto premium → Reparación automática</p>
        </div>
        <div className="ron3ia-subtitle">
          <Link className="link" to="/repair">
            Repair
          </Link>
        </div>
      </div>

      <div className="panel">
        <div className="modules">
          {MODULES.map((m) => {
            const active = selectedModules.includes(m)
            return (
              <button
                key={m}
                type="button"
                className={active ? 'module module--active' : 'module'}
                onClick={() => toggleModule(m)}
              >
                {m}
              </button>
            )
          })}
        </div>

        <div className="row" style={{ marginTop: 12 }}>
          <input className="input" placeholder="Dominio (ej: ronrodrigo3.com)" value={dominio} onChange={(e) => setDominio(e.target.value)} />
          <input className="input" placeholder="Nombre" value={nombre} onChange={(e) => setNombre(e.target.value)} />
          <input className="input" placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} />
        </div>

        <div className="row" style={{ marginTop: 12 }}>
          <button
            className="btn btn--primary"
            disabled={loading || !dominio.trim() || !nombre.trim() || !email.trim() || selectedModules.length === 0}
            onClick={emitirVeredicto}
          >
            {loading ? 'Analizando…' : 'EMITIR VEREDICTO'}
          </button>
          <div className="price">
            Total dinámico: <strong>${totalUsd} USD</strong>
          </div>
        </div>

        {error && <div className="result">{error}</div>}

        {hasResult && (
          <>
            <div className="result">
              <strong>Resumen básico (GRATIS)</strong>
              {'\n'}
              {result?.resumen_tecnico}
              {'\n\n'}
              <strong>Problemas detectados</strong>
              {'\n'}
              {result.problemas_detectados.map((p) => `- ${p}`).join('\n')}
              {'\n\n'}
              <strong>Módulos bloqueados</strong>
              {'\n'}
              {result.modulos_bloqueados.map((m) => `- 🔒 ${m}`).join('\n')}
              {'\n\n'}
              Report ID: {result.report_id}
            </div>

            <button className="glass-button" onClick={handleStripeCheckout} disabled={checkingOut}>
              {checkingOut ? 'Abriendo checkout…' : 'ACCEDER AL VEREDICTO'}
            </button>
            <div className="premium-hint">
              El análisis ya está listo. Solo falta desbloquearlo.
            </div>
          </>
        )}
      </div>
    </div>
  )
}

function RepairPage() {
  const [params] = useSearchParams()
  const report_id = (params.get('report_id') ?? '').trim()
  const [loading, setLoading] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [report, setReport] = React.useState<any | null>(null)
  const [checkingOut, setCheckingOut] = React.useState(false)

  React.useEffect(() => {
    if (!report_id) return
    setLoading(true)
    setError(null)
    getReport(report_id)
      .then((r) => setReport(r.report))
      .catch((e: any) => setError(e?.message ?? 'No se pudo cargar el reporte'))
      .finally(() => setLoading(false))
  }, [report_id])

  async function handleRepairCheckout() {
    if (!report_id) return
    setError(null)
    setCheckingOut(true)
    try {
      const { checkout_url } = await createRepairCheckoutSession(report_id)
      window.location.href = checkout_url
    } catch (e: any) {
      setError(e?.message ?? 'No se pudo iniciar el checkout de reparación')
      setCheckingOut(false)
    }
  }

  return (
    <div className="ron3ia-wrap">
      <div className="ron3ia-header">
        <div>
          <h1 className="ron3ia-title">REPAIR — RON3IA</h1>
          <p className="ron3ia-subtitle">Reparación automática (2º pago)</p>
        </div>
        <div className="ron3ia-subtitle">
          <Link className="link" to="/">
            Volver
          </Link>
        </div>
      </div>

      <div className="panel">
        {!report_id && (
          <div className="result">
            Falta <strong>report_id</strong> en la URL. Ej: <code>/repair?report_id=xxx</code>
          </div>
        )}
        {loading && <div className="result">Cargando reporte…</div>}
        {error && <div className="result">{error}</div>}

        {report && (
          <>
            <div className="result">
              <strong>Problemas detectados</strong>
              {'\n'}
              {(report.problemas_detectados ?? []).map((p: string) => `- ${p}`).join('\n')}
              {'\n\n'}
              <strong>Acciones sugeridas</strong>
              {'\n'}
              {(report.suggested_actions ?? []).map((a: string) => `- ${a}`).join('\n')}
            </div>

            <button className="glass-button" onClick={handleRepairCheckout} disabled={checkingOut}>
              {checkingOut ? 'Abriendo checkout…' : 'EJECUTAR REPARACIÓN'}
            </button>
            <div className="premium-hint">
              Esto iniciará el flujo de reparación automática para tu reporte.
            </div>
          </>
        )}
      </div>
    </div>
  )
}

function ReportPage() {
  const { report_id = '' } = useParams()
  const rid = (report_id ?? '').trim()
  const [loading, setLoading] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [status, setStatus] = React.useState<'locked' | 'unlocked' | string>('locked')
  const [basic, setBasic] = React.useState<any | null>(null)
  const [full, setFull] = React.useState<any | null>(null)
  const [email, setEmail] = React.useState('')
  const [checkingOut, setCheckingOut] = React.useState(false)

  React.useEffect(() => {
    if (!rid) return
    setLoading(true)
    setError(null)
    getReportStatus(rid)
      .then((r) => {
        setStatus(r.status)
        setBasic(r.basic)
        setFull(r.full)
      })
      .catch((e: any) => setError(e?.message ?? 'No se pudo cargar el estado del reporte'))
      .finally(() => setLoading(false))
  }, [rid])

  async function handleCheckout() {
    if (!rid) return
    setError(null)
    setCheckingOut(true)
    try {
      const { checkout_url } = await createCheckoutSession(rid, email.trim())
      window.location.href = checkout_url
    } catch (e: any) {
      setError(e?.message ?? 'No se pudo iniciar el checkout')
      setCheckingOut(false)
    }
  }

  return (
    <div className="ron3ia-wrap">
      <div className="ron3ia-header">
        <div>
          <h1 className="ron3ia-title">REPORTE — RON3IA</h1>
          <p className="ron3ia-subtitle">Estado: {status}</p>
        </div>
        <div className="ron3ia-subtitle">
          <Link className="link" to="/">
            Volver
          </Link>
        </div>
      </div>

      <div className="panel">
        {!rid && <div className="result">Falta report_id en la ruta.</div>}
        {loading && <div className="result">Cargando…</div>}
        {error && <div className="result">{error}</div>}

        {rid && !loading && !error && status === 'locked' && (
          <>
            <div className="result">
              <strong>Resumen básico (GRATIS)</strong>
              {'\n'}
              {basic ? JSON.stringify(basic, null, 2) : '(sin datos)'}
              {'\n\n'}
              <strong>Veredicto Premium</strong>
              {'\n'}
              Bloqueado 🔒 — Desbloquéalo para ver el informe completo.
            </div>

            <div className="row" style={{ marginTop: 12 }}>
              <input
                className="input"
                placeholder="Email (para Stripe Checkout)"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>

            <button className="glass-button" onClick={handleCheckout} disabled={checkingOut || !email.trim()}>
              {checkingOut ? 'Abriendo checkout…' : 'ACCEDER AL VEREDICTO'}
            </button>
            <div className="premium-hint">El análisis ya está listo. Solo falta desbloquearlo.</div>
          </>
        )}

        {rid && !loading && !error && status === 'unlocked' && (
          <>
            <div className="result">
              <strong>Informe completo (Premium)</strong>
              {'\n'}
              {full ? JSON.stringify(full, null, 2) : '(sin datos)'}
            </div>
            <div className="premium-hint">
              Puedes iniciar la reparación automática desde la sección Repair.
            </div>
          </>
        )}
      </div>
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<DiagnosticPage />} />
        <Route path="/report/:report_id" element={<ReportPage />} />
        <Route path="/repair" element={<RepairPage />} />
      </Routes>
    </BrowserRouter>
  )
}

