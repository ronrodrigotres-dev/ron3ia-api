const API_BASE = import.meta.env.VITE_RON3IA_API_URL;

export type AnalyzePayload = {
  dominio: string
  nombre: string
  email: string
  selectedModules: string[]
}

export type AnalyzeResult = {
  report_id: string
  resumen_tecnico: string
  problemas_detectados: string[]
  modulos_bloqueados: string[]
  total_usd: number
}

export async function emitVerdict(payload: AnalyzePayload) {
  const response = await fetch(`${API_BASE}/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  const data = await response.json().catch(() => null)
  if (!response.ok) throw new Error(data?.detail ?? `Error de conexión: ${response.statusText}`)
  return data as { ok: boolean; result: AnalyzeResult }
}

export async function createCheckoutSession(report_id: string) {
  const response = await fetch(`${API_BASE}/create-checkout-session`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ report_id }),
  })
  const data = await response.json().catch(() => null)
  if (!response.ok) throw new Error(data?.detail ?? `Checkout error: ${response.statusText}`)
  return data as { ok: boolean; url: string }
}

export async function createRepairCheckoutSession(report_id: string) {
  const response = await fetch(`${API_BASE}/create-repair-checkout-session`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ report_id }),
  })
  const data = await response.json().catch(() => null)
  if (!response.ok) throw new Error(data?.detail ?? `Repair checkout error: ${response.statusText}`)
  return data as { ok: boolean; url: string }
}

export async function getReport(report_id: string) {
  const response = await fetch(`${API_BASE}/report/${encodeURIComponent(report_id)}`)
  const data = await response.json().catch(() => null)
  if (!response.ok) throw new Error(data?.detail ?? `Report error: ${response.statusText}`)
  return data as {
    ok: boolean
    report: {
      report_id: string
      dominio: string
      modules: string[]
      problemas_detectados: string[]
      suggested_actions: string[]
      paid: boolean
      repair_active: boolean
      full_report: any | null
    }
  }
}
