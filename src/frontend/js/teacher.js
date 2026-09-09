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
        showError("Esta página é apenas para professores. Você será redirecionado para o painel do aluno.");
        setTimeout(() => {
            window.location.href = "dashboard.html";
        }, 3000);
        return;
    }
    
    await loadStudents();
    await loadCohorts();
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
            showError("Erro ao carregar alunos.");
            return;
        }
        allStudents = response.students;
        totalStudents = response.total || allStudents.length;
        renderStudentTable(allStudents);
        renderCohortFilter();
        loadKPIs();
    } catch (err) {
        if (err.message.includes("403") || err.message.includes("Only teachers can list students")) {
            showError("Acesso negado: Você precisa ser um professor para acessar esta página. Faça login com uma conta de professor.");
            // Redirect to dashboard after 3 seconds
            setTimeout(() => {
                window.location.href = "dashboard.html";
            }, 3000);
        } else {
            showError("Erro ao carregar alunos: " + err.message);
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
            ? new Date(student.final_exam_release_date).toLocaleDateString("pt-BR")
            : "Não configurada";
        const finalExamStatus = failedFinalExam > 0
            ? `${releaseDate} · ${failedFinalExam} tentativa(s)` 
            : releaseDate;
        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td>${esc(student.name)}</td>
            <td>${esc(student.email)}</td>
            <td>${esc(student.cohort_id)}</td>
            <td><span class="phase-badge" data-phase="${esc(student.current_phase || 'initial')}">${esc(student.current_phase || 'initial')}</span></td>
            <td>${esc(finalExamStatus)}</td>
            <td>
                <button class="btn-history" data-student="${esc(student.student_id)}">Historial</button>
                <button class="btn-set-exam" data-student="${esc(student.student_id)}">Configurar data</button>
                <button class="btn-reset-exam" data-student="${esc(student.student_id)}">Resetar tentativa</button>
            </td>
        `;
        tbody.appendChild(tr);
    });
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
    cohortSelect.innerHTML = '<option value="">Todas as turmas</option>';
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
            const percentage = cohort.max_students > 0 ? Math.round((cohort.current_count / cohort.max_students) * 100) : 0;
            const tr = document.createElement('tr');
            tr.innerHTML = `<td>${esc(cohort.cohort_id)}</td><td>${esc(cohort.name || '')}</td><td>${cohort.current_count}</td><td>${cohort.max_students}</td><td>${percentage}%</td>`;
            tbody.appendChild(tr);
        });
    } catch (err) {
        if (err.message.includes("403") || err.message.includes("Only teachers can list cohorts")) {
            // Don't show duplicate error message since loadStudents already showed it
            console.log("Teacher permission required for cohorts endpoint");
        } else {
            showError("Erro ao carregar turmas: " + err.message);
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
        const response = await apiCall("GET", "/students/" + studentId + "/quizzes");
        const tbody = document.getElementById('historyTable');
        if (!tbody) return;

        tbody.innerHTML = "";
        if (!response || !response.quizzes || response.quizzes.length === 0) {
            tbody.innerHTML = "<tr><td colspan='5'>Nenhum quiz realizado ainda.</td></tr>";
            return;
        }

        response.quizzes.forEach(function(q, index) {
            const status = esc(q.status || 'completed');
            const score = q.score_percentage !== null && q.score_percentage !== undefined ? q.score_percentage + '%' : '0%';
            const tr = document.createElement('tr');
            tr.innerHTML = `<td>${index + 1}</td>
                <td>${esc(q.quiz_type || '')} - ${esc(q.topic || '-')}</td>
                <td><span class="${status}">${status}</span></td>
                <td>${esc(score)}</td>
                <td>${esc(q.created_at ? new Date(q.created_at).toLocaleDateString('pt-BR') : '-')}</td>`;
            tbody.appendChild(tr);
        });
    } catch (err) {
        showError("Erro ao carregar histórico: " + err.message);
    }
}

// ========== GESTIÓN DEL EXAMEN FINAL ==========

async function setFinalExamRelease(studentId, date) {
    try {
        await apiCall("PUT", "/students/" + studentId + "/final-exam-release", { release_date: date });
        await loadStudents();
    } catch (err) {
        showError("Erro ao configurar data: " + err.message);
    }
}

async function resetFinalExamAttempt(studentId) {
    try {
        await apiCall("DELETE", "/students/" + studentId + "/final-exam-attempt");
        await loadStudents();
    } catch (err) {
        showError("Erro ao resetar tentativa: " + err.message);
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
        studentTableBody.addEventListener('click', function(e) {
            if (e.target.classList.contains('btn-history')) {
                selectStudent(e.target.dataset.student);
            }
            if (e.target.classList.contains('btn-set-exam')) {
                const studentId = e.target.dataset.student;
                const raw = prompt("Data de liberação do exame final (YYYY-MM-DD ou YYYY-MM-DDTHH:MM, hora local):");
                if (raw !== null) {
                    const iso = normalizeReleaseDate(raw.trim());
                    if (iso) {
                        setFinalExamRelease(studentId, iso);
                    } else {
                        showError("Data inválida. Use YYYY-MM-DD ou YYYY-MM-DDTHH:MM.");
                    }
                }
            }
            if (e.target.classList.contains('btn-reset-exam')) {
                const studentId = e.target.dataset.student;
                if (confirm("Resetar a tentativa do exame final deste aluno?")) {
                    resetFinalExamAttempt(studentId);
                }
            }
        });
    }

    const logoutBtn = document.getElementById('logoutBtn');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', function(e) {
            e.preventDefault();
            logout();
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