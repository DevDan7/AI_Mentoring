// URL base del API Gateway para el bootstrap de configuración.
// En hosting estático (Amplify) no hay templating: el navegador resuelve
// rutas relativas contra el dominio del frontend (404), por lo que /config
// debe apuntarse explícitamente al API Gateway.
const API_GATEWAY_URL = "https://9ftb5bwpk7.execute-api.us-east-1.amazonaws.com";

// Configuración global de la aplicación, cargada dinámicamente desde GET /config.
const CONFIG = {
    apiUrl: "",
    cognitoRegion: "us-east-1",
    userPoolId: "",
    clientId: ""
};

// Carga la configuración dinámica antes de cualquier otra llamada a la API.
// Debe invocarse como primer paso en <script> de todas las páginas.
async function loadConfig() {
    try {
        const response = await fetch(`${API_GATEWAY_URL}/config`);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status} ao obter /config`);
        }
        const data = await response.json();
        CONFIG.apiUrl = data.apiUrl;
        CONFIG.userPoolId = data.userPoolId;
        CONFIG.clientId = data.clientId;

        if (!CONFIG.apiUrl || !CONFIG.userPoolId || !CONFIG.clientId) {
            throw new Error("Configuração incompleta desde /config");
        }
        return CONFIG;
    } catch (err) {
        const errorEl = document.getElementById('errorMsg');
        if (errorEl) {
            errorEl.textContent = "Não foi possível carregar a configuração. Verifique sua conexão com a internet.";
            errorEl.style.display = 'block';
        }
        throw err;
    }
}