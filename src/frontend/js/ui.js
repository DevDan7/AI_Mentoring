// Componentes de UI compartidos entre las páginas autenticadas:
// menú de usuario (avatar con iniciales + dropdown con "Sair") y botón "volver arriba".
// Requiere i18n.js y auth.js cargados antes.

// Iniciales: primera letra del primer y último nombre ("grediana rojas" -> "GR").
function userInitials(name, email) {
    const parts = String(name || "").trim().split(/\s+/).filter(Boolean);
    if (parts.length >= 2) return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
    if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
    return String(email || "?").slice(0, 1).toUpperCase();
}

// Renderiza el avatar en #userMenu. Sin argumentos usa los claims del id_token.
function renderUserMenu(name, email) {
    const container = document.getElementById("userMenu");
    if (!container) return;

    const claims = parseJwt(localStorage.getItem("id_token")) || {};
    name = name || claims.name || "";
    email = email || claims.email || "";

    container.innerHTML = "";
    container.className = "user-menu";

    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "user-avatar";
    btn.textContent = userInitials(name, email);
    btn.setAttribute("aria-haspopup", "true");
    btn.setAttribute("aria-expanded", "false");
    btn.setAttribute("aria-label", t("common.userMenu"));

    const panel = document.createElement("div");
    panel.className = "user-menu-panel";
    panel.hidden = true;

    const info = document.createElement("div");
    info.className = "user-menu-info";
    const nameEl = document.createElement("strong");
    nameEl.textContent = name || email;
    info.appendChild(nameEl);
    if (name && email) {
        const emailEl = document.createElement("small");
        emailEl.textContent = email;
        info.appendChild(emailEl);
    }

    const logoutBtn = document.createElement("button");
    logoutBtn.type = "button";
    logoutBtn.className = "secondary";
    logoutBtn.textContent = t("common.logout");
    logoutBtn.addEventListener("click", logout);

    panel.append(info, logoutBtn);
    container.append(btn, panel);

    const setOpen = open => {
        panel.hidden = !open;
        btn.setAttribute("aria-expanded", String(open));
    };
    btn.addEventListener("click", e => {
        e.stopPropagation();
        setOpen(panel.hidden);
    });
    document.addEventListener("click", e => {
        if (!container.contains(e.target)) setOpen(false);
    });
    document.addEventListener("keydown", e => {
        if (e.key === "Escape") setOpen(false);
    });
}

// Botón flotante "volver arriba": aparece después de bajar una pantalla.
function initBackToTop() {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "back-to-top";
    btn.textContent = "↑";
    btn.setAttribute("aria-label", t("common.backToTop"));
    btn.title = t("common.backToTop");
    btn.hidden = true;
    btn.addEventListener("click", () => window.scrollTo({ top: 0, behavior: "smooth" }));
    document.body.appendChild(btn);

    const update = () => { btn.hidden = window.scrollY < window.innerHeight; };
    window.addEventListener("scroll", update, { passive: true });
    update();
}

renderUserMenu();
initBackToTop();
