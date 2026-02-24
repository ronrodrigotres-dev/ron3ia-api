const API_BASE = import.meta.env.VITE_RON3IA_API_URL;

export async function analyzeWebsite(url: string) {
    const response = await fetch(`${API_BASE}/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url }),
    });
    if (!response.ok) throw new Error(`Error de conexión: ${response.statusText}`);
    return response.json();
}

export async function createCheckoutSession(params: { email: string; report_id: string }) {
    const response = await fetch(`${API_BASE}/create-checkout-session`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(params),
    });
    if (!response.ok) throw new Error(`Checkout error: ${response.statusText}`);
    return response.json() as Promise<{ checkout_url: string }>;
}
