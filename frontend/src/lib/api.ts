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
