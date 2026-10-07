// ========== INICIALIZACIÓN DEL DASHBOARD ==========

async function initTeacherDashboard() {
    try {
        await loadConfig();
    } catch (err) {
        return;
    }

    const token = await checkAuth();
    if (!token) {
        window.location.href = "index.html";
        return;
    }
    
    // Check if user is teacher early and show appropriate message
    if (!isTeacher()) {
        showError(t("teacher.err.onlyTeachers"));
        setTimeout(() => {
            window.location.href = "dashboard.html";
        }, 3000);
        return;
    }
    
    await loadCohorts();
    await loadStudents();
    loadKPIs();
    setupEvents();
}

// ========== CARGA DE ESTUDIANTES ==========

async function loadStudents() {
    try {
        const response = await apiCall("GET", "/students");
        if (!response || !response.students) {
            allStudents = [];
            totalStudents = 0;
            showError(t("teacher.err.loadStudents"));
            return;
        }
        allStudents = response.students;
        totalStudents = response.total || allStudents.length;
        renderStudentTable(allStudents);
        renderCohortFilter();
        loadKPIs();
    } catch (err) {
        if (err.message.includes("403") || err.message.includes("Only teachers can list students")) {
            showError(t("teacher.err.forbidden"));
            // Redirect to dashboard after 3 seconds
            setTimeout(() => {
                window.location.href = "dashboard.html";
            }, 3000);
        } else {
            showError(t("teacher.err.loadStudentsDetail") + err.message);
        }
    }
}

function renderStudentTable(students) {
    const tbody = document.getElementById("studentTable");
    if (!tbody) return;
    tbody.innerHTML = "";
    students.forEach(student => {
        const failed = (student.failed_attempts || {});
        const failedFinalExam = failed.final_exam || 0;
        const releaseDate = student.final_exam_release_date
            ? new Date(student.final_exam_release_date).toLocaleDateString(getLocale())
            : t("teacher.notConfigured");
        const finalExamStatus = failedFinalExam > 0
            ? `${releaseDate} · ${t("teacher.attempts", { count: failedFinalExam })}`
            : releaseDate;
        const access = studentAccess(student);
        const blocked = student.access_status === 'blocked';
        const cycleTag = student.cycle > 1
            ? `<span class="cycle-tag">${esc(t("teacher.cycleN", { n: student.cycle }))}</span>`
            : '';
        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td>${esc(student.name)}</td>
            <td>${esc(student.email)}</td>
            <td>${esc(student.cohort_id)}</td>
            <td><span class="phase-badge" data-phase="${esc(student.current_phase || 'initial')}">${esc(tEnum('phase', student.current_phase || 'initial'))}</span>${cycleTag}</td>
            <td>${esc(finalExamStatus)}</td>
            <td><span class="access-badge" data-access="${esc(access.state)}">${esc(access.label)}</span></td>
            <td>
                <select class="student-actions" data-student="${esc(student.student_id)}" data-name="${esc(student.name)}" aria-label="${esc(t("teacher.col.actions"))}">
                    <option value="">${esc(t("teacher.actionsPlaceholder"))}</option>
                    <option value="history">${esc(t("teacher.btn.history"))}</option>
                    <option value="set-exam">${esc(t("teacher.btn.setExam"))}</option>
                    <option value="reset-exam">${esc(t("teacher.btn.resetExam"))}</option>
                    <option value="${blocked ? 'unblock' : 'block'}">${esc(t(blocked ? "teacher.btn.unblock" : "teacher.btn.block"))}</option>
                    <option value="extend">${esc(t("teacher.btn.extend"))}</option>
                    <option value="restart">${esc(t("teacher.btn.restart"))}</option>
                </select>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

// Estado de acceso efectivo, con la misma precedencia que evaluate_access() del backend:
// bloqueo individual > extensión individual > turma encerrada > ativo.
function studentAccess(student) {
    const fmt = (iso) => new Date(iso).toLocaleDateString(getLocale());
    if (student.access_status === 'blocked') {
        return { state: 'blocked', label: t("teacher.access.blocked") };
    }
    if (student.access_status === 'open') {
        if (!student.access_until) {
            return { state: 'open', label: t("teacher.access.open") };
        }
        if (new Date(student.access_until) > new Date()) {
            return { state: 'open', label: t("teacher.access.openUntil", { date: fmt(student.access_until) }) };
        }
    }
    const cohort = allCohorts.find(c => c.cohort_id === student.cohort_id);
    if (cohort && cohort.status === 'closed') {
        return { state: 'cohort_closed', label: t("teacher.access.cohortClosed") };
    }
    return { state: 'active', label: t("teacher.access.active") };
}

// ========== CARGA DE KPIS ==========

function loadKPIs() {
    const el = (id, value) => {
        const node = document.getElementById(id);
        if (node) node.textContent = value;
    };
    el('kpiTotal', totalStudents);
    el('kpiInitial', allStudents.filter(s => s.current_phase === 'initial').length);
    el('kpiFreePractice', allStudents.filter(s => s.current_phase === 'free_practice').length);
    el('kpiFinalExam', allStudents.filter(s => s.current_phase === 'final_exam').length);
}

// ========== FILTROS ==========

function renderCohortFilter() {
    const cohortSelect = document.getElementById('cohortFilter');
    if (!cohortSelect) return;

    const cohorts = [...new Set(allStudents.map(s => s.cohort_id).filter(Boolean))];
    cohortSelect.innerHTML = `<option value="">${esc(t("teacher.allCohorts"))}</option>`;
    cohorts.forEach(cohort => {
        const option = document.createElement('option');
        option.value = cohort;
        option.textContent = cohort;
        cohortSelect.appendChild(option);
    });
}

// Puebla el filtro de turmas con las cohortes activas (Req. 12.3).
async function loadCohorts() {
    try {
        const response = await apiCall("GET", "/cohorts");
        if (!response || !response.cohorts) {
            allCohorts = [];
            return;
        }
        allCohorts = response.cohorts;
        renderCohortFilter();
        const tbody = document.getElementById('cohortsTable');
        if (!tbody) return;
        tbody.innerHTML = "";
        response.cohorts.forEach(cohort => {
            const isGuests = cohort.type === 'convidados';
            const closed = cohort.status === 'closed';
            let statusLabel;
            let action = '';
            if (isGuests) {
                // Convidados no tienen ciclo: el acceso se maneja alumno por alumno
                statusLabel = t("teacher.cohort.guests");
            } else if (closed) {
                const date = cohort.closed_at ? new Date(cohort.closed_at).toLocaleDateString(getLocale()) : '';
                statusLabel = t("teacher.cohort.closedOn", { date });
                action = `<button class="btn-cohort-status secondary outline" data-cohort="${esc(cohort.cohort_id)}" data-status="active">${esc(t("teacher.btn.reopenCycle"))}</button>`;
            } else {
                statusLabel = t("teacher.cohort.open");
                action = `<button class="btn-cohort-status" data-cohort="${esc(cohort.cohort_id)}" data-status="closed">${esc(t("teacher.btn.closeCycle"))}</button>`;
            }
            const tr = document.createElement('tr');
            tr.innerHTML = `<td>${esc(cohort.cohort_id)}</td><td>${esc(cohort.name || '')}</td><td>${cohort.current_count}</td><td>${isGuests ? '-' : cohort.max_students}</td><td>${esc(statusLabel)}</td><td>${action}</td>`;
            tbody.appendChild(tr);
        });
    } catch (err) {
        if (err.message.includes("403") || err.message.includes("Only teachers can list cohorts")) {
            // Don't show duplicate error message since loadStudents already showed it
            console.log("Teacher permission required for cohorts endpoint");
        } else {
            showError(t("teacher.err.loadCohorts") + err.message);
        }
    }
}

function filterStudents() {
    const cohortEl = document.getElementById('cohortFilter');
    const searchEl = document.getElementById('searchInput');
    const cohortVal = cohortEl ? cohortEl.value : '';
    const searchVal = searchEl ? searchEl.value.toLowerCase() : '';
    let filtered = allStudents.filter(student => {
        const matchesCohort = !cohortVal || student.cohort_id === cohortVal;
        const matchesSearch = (student.name || '').toLowerCase().includes(searchVal) || (student.email || '').toLowerCase().includes(searchVal);
        return matchesCohort && matchesSearch;
    });
    renderStudentTable(filtered);
}

// ========== HISTORIAL DEL ALUMNO ==========

// Muestra la sección historySection y carga los quizzes del alumno (Req. 12.6).
async function selectStudent(studentId) {
    const section = document.getElementById('historySection');
    if (section) {
        section.style.display = 'block';
    }
    await loadStudentQuizzes(studentId);
}

async function loadStudentQuizzes(studentId) {
    try {
        const response = await getStudentQuizzes(studentId);
        const tbody = document.getElementById('historyTable');
        if (!tbody) return;

        tbody.innerHTML = "";
        if (!response || !response.quizzes || response.quizzes.length === 0) {
            tbody.innerHTML = `<tr><td colspan='6'>${esc(t("teacher.noQuizzes"))}</td></tr>`;
            return;
        }

        response.quizzes.forEach(function(q, index) {
            const status = esc(q.status || 'completed');
            const score = q.score_percentage !== null && q.score_percentage !== undefined ? q.score_percentage + '%' : '0%';
            const tr = document.createElement('tr');
            tr.innerHTML = `<td>${index + 1}</td>
                <td>${esc(tEnum('quizType', q.quiz_type))} - ${esc(q.topic || '-')}${q.cycle > 1 ? `<span class="cycle-tag">${esc(t("teacher.cycleN", { n: q.cycle }))}</span>` : ''}</td>
                <td><span class="${status}">${esc(tEnum('status', q.status || 'completed'))}</span></td>
                <td>${esc(score)}</td>
                <td>${esc(q.created_at ? new Date(q.created_at).toLocaleDateString(getLocale()) : '-')}</td>
                <td><a href="results.html?quizId=${encodeURIComponent(q.quiz_id)}" target="_blank" rel="noopener">${esc(t("teacher.viewDetails"))}</a></td>`;
            tbody.appendChild(tr);
        });
    } catch (err) {
        showError(t("teacher.err.loadHistory") + err.message);
    }
}

// ========== GESTIÓN DEL EXAMEN FINAL ==========

async function setFinalExamRelease(studentId, date) {
    try {
        await apiCall("PUT", "/students/" + studentId + "/final-exam-release", { release_date: date });
        await loadStudents();
    } catch (err) {
        showError(t("teacher.err.setDate") + err.message);
    }
}

async function resetFinalExamAttempt(studentId) {
    try {
        await apiCall("DELETE", "/students/" + studentId + "/final-exam-attempt");
        await loadStudents();
    } catch (err) {
        showError(t("teacher.err.reset") + err.message);
    }
}

// ========== CICLO DE VIDA: ACCESO, REINTENTO Y TURMAS ==========

async function setStudentAccess(studentId, body) {
    try {
        await apiCall("PUT", "/students/" + studentId + "/access", body);
        await loadStudents();
    } catch (err) {
        showError(t("teacher.err.access") + err.message);
    }
}

async function restartStudentCycle(studentId) {
    try {
        await apiCall("POST", "/students/" + studentId + "/restart");
        await loadStudents();
    } catch (err) {
        showError(t("teacher.err.restart") + err.message);
    }
}

async function setCohortStatus(cohortId, status) {
    try {
        await apiCall("PUT", "/cohorts/" + encodeURIComponent(cohortId) + "/status", { status });
        await loadCohorts();
        renderStudentTable(allStudents);
    } catch (err) {
        showError(t("teacher.err.cohortStatus") + err.message);
    }
}

function runStudentAction(action, studentId, name) {
    if (action === 'history') {
        selectStudent(studentId);
    } else if (action === 'set-exam') {
        const raw = prompt(t("teacher.promptDate"));
        if (raw !== null) {
            const iso = normalizeReleaseDate(raw.trim());
            if (iso) {
                setFinalExamRelease(studentId, iso);
            } else {
                showError(t("teacher.err.invalidDate"));
            }
        }
    } else if (action === 'reset-exam') {
        if (confirm(t("teacher.confirmReset"))) {
            resetFinalExamAttempt(studentId);
        }
    } else if (action === 'block' || action === 'unblock') {
        setStudentAccess(studentId, { action });
    } else if (action === 'extend') {
        // Vacío = acceso liberado sin fecha límite
        const raw = prompt(t("teacher.promptExtend"));
        if (raw === null) return;
        const value = raw.trim();
        if (!value) {
            setStudentAccess(studentId, { action: 'open' });
            return;
        }
        const iso = normalizeReleaseDate(value);
        if (iso) {
            setStudentAccess(studentId, { action: 'open', until: iso });
        } else {
            showError(t("teacher.err.invalidDate"));
        }
    } else if (action === 'restart') {
        if (confirm(t("teacher.confirmRestart", { name }))) {
            restartStudentCycle(studentId);
        }
    }
}

// ========== EVENTOS ==========

function setupEvents() {
    const searchInput = document.getElementById('searchInput');
    if (searchInput) searchInput.addEventListener('input', filterStudents);

    const cohortFilter = document.getElementById('cohortFilter');
    if (cohortFilter) cohortFilter.addEventListener('change', filterStudents);

    const studentTableBody = document.getElementById('studentTable');
    if (studentTableBody) {
        studentTableBody.addEventListener('change', function(e) {
            const select = e.target;
            if (!select.classList.contains('student-actions') || !select.value) return;
            const action = select.value;
            const studentId = select.dataset.student;
            select.value = "";   // el selector vuelve a "Ações…" tras cada acción
            runStudentAction(action, studentId, select.dataset.name);
        });
    }

    const cohortsTableBody = document.getElementById('cohortsTable');
    if (cohortsTableBody) {
        cohortsTableBody.addEventListener('click', function(e) {
            if (!e.target.classList.contains('btn-cohort-status')) return;
            const cohortId = e.target.dataset.cohort;
            const status = e.target.dataset.status;
            const key = status === 'closed' ? "teacher.confirmCloseCycle" : "teacher.confirmReopenCycle";
            if (confirm(t(key, { cohort: cohortId }))) {
                setCohortStatus(cohortId, status);
            }
        });
    }

    const closeHistoryBtn = document.getElementById('closeHistoryBtn');
    if (closeHistoryBtn) {
        closeHistoryBtn.addEventListener('click', function() {
            const section = document.getElementById('historySection');
            if (section) {
                section.style.display = 'none';
            }
        });
    }
}

// ========== HERRAMIENTAS ==========

// Escribe el mensaje de error en <div id="errorMsg"> y lo hace visible.
// Nunca usa alert() como único canal de notificación (Req. 2.7).
function showError(message) {
    const errorEl = document.getElementById('errorMsg');
    if (errorEl) {
        errorEl.textContent = message;
        errorEl.style.display = 'block';
    }
}

// Normaliza la entrada del prompt a ISO-8601 con offset local.
// Acepta "YYYY-MM-DD" (asume 00:00) o "YYYY-MM-DDTHH:MM"; la hora se interpreta
// como local y se le agrega el offset del navegador. Devuelve null si no parsea.
function normalizeReleaseDate(input) {
    let s = input;
    if (/^\d{4}-\d{2}-\d{2}$/.test(s)) {
        s += "T00:00";
    }
    if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?$/.test(s)) {
        return null;
    }
    const d = new Date(s);
    if (isNaN(d.getTime())) {
        return null;
    }
    const tzMin = -d.getTimezoneOffset();
    const sign = tzMin >= 0 ? "+" : "-";
    const abs = Math.abs(tzMin);
    const pad = (n) => String(n).padStart(2, "0");
    return `${s}${sign}${pad(Math.floor(abs / 60))}:${pad(abs % 60)}`;
}

function esc(value) {
    return String(value === undefined || value === null ? '' : value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

// Estado global
var allStudents = [];
var allCohorts = [];
var totalStudents = 0;

// Inicialización automática al cargar el DOM
document.addEventListener("DOMContentLoaded", () => {
    initTeacherDashboard();
});