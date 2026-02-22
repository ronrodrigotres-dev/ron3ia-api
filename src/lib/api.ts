const API_BASE = "https://ron3ia-api-819648047297.us-central1.run.app";

export async function analyzeWebsite(url: string) {
    const response = await fetch(`${API_BASE}/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url }),
    });
    if (!response.ok) throw new Error(`Error de conexión: ${response.statusText}`);
    return response.json();
}
