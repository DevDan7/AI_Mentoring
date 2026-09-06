// ========== INICIALIZACIÓN DEL DASHBOARD ==========

async function initTeacherDashboard() {
    const token = checkAuth();
    if (!token) {
        window.location.href = "index.html";
        return;
    }
    if (!isTeacher()) {
        window.location.href = "dashboard.html";
        return;
    }
    await loadStudents();
    await loadCohorts();
    loadKPIs();
    setupEvents();
}

// ========== CARGA DE ESTUDIANTES ==========

async function loadStudents() {
    const response = await apiCall("GET", "/students");
    if (!response || !response.students) {
        showToast("Error al cargar alunos", "error");
        return;
    }
    allStudents = response.students;
    totalStudents = response.total || allStudents.length;
    renderStudentTable(allStudents);
    renderCohortFilter();
    setupStudentEvents();
}

function renderStudentTable(students) {
    const tbody = document.getElementById("studentTable");
    if (!tbody) return;

    tbody.innerHTML = "";
    students.forEach(student => {
        const failed = student.failed_attempts || {};
        const failedCount = (failed.phase_1 || 0) + (failed.phase_2 || 0) + (failed.final_exam || 0);
        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td>${student.name || '-'}</td>
            <td>${student.email || '-'}</td>
            <td>${student.cohort_id || '-'}</td>
            <td><span class="phase-badge" data-phase="${student.current_phase || 'initial'}">${student.current_phase || 'initial'}</span></td>
            <td>${failedCount}</td>
            <td>
                <select class="phase-select" data-student="${student.student_id}" disabled>
                    <option value="initial">Initial</option>
                    <option value="phase_1">Phase 1</option>
                    <option value="phase_2">Phase 2</option>
                    <option value="final_exam">Final Exam</option>
                    <option value="free_practice">Free Practice</option>
                </select>
                <button class="btn-save-phase" data-student="${student.student_id}" disabled>Guardar</button>
                <button class="btn-history" data-student="${student.student_id}">Historial</button>
            </td>
        `;
        tbody.appendChild(tr);
    });
    setupPhaseSelects();
}

function setupPhaseSelects() {
    document.querySelectorAll('.phase-select').forEach(select => {
        const studentId = select.dataset.student;
        const currentPhase = allStudents.find(s => s.student_id === studentId)?.current_phase || 'initial';
        select.value = currentPhase;
        select.disabled = false;
        const saveBtn = select.nextElementSibling;
        if (saveBtn) {
            saveBtn.disabled = false;
        }
    });
}

function renderCohortFilter() {
    const select = document.getElementById('cohortFilter');
    if (!select) return;

    const currentValue = select.value;
    const cohortIds = [...new Set(allStudents.map(student => student.cohort_id).filter(Boolean))].sort();

    select.innerHTML = '<option value="">Todos</option>';
    cohortIds.forEach(cohortId => {
        const option = document.createElement('option');
        option.value = cohortId;
        option.textContent = cohortId;
        select.appendChild(option);
    });

    if (cohortIds.includes(currentValue)) {
        select.value = currentValue;
    } else {
        select.value = "";
    }
}

function setupStudentEvents() {
    document.querySelectorAll('.btn-history').forEach(function(btn) {
        btn.onclick = function() {
            openStudentHistoryModal(btn.dataset.student);
        };
    });

    document.querySelectorAll('.phase-select').forEach(function(select) {
        select.onchange = function(e) {
            updateStudentPhase(e.target.dataset.student, e.target.value);
        };
    });

    document.querySelectorAll('.btn-save-phase').forEach(function(btn) {
        btn.onclick = function(e) {
            const select = e.target.previousElementSibling;
            if (select) {
                updateStudentPhase(e.target.dataset.student, select.value);
            }
        };
    });
}

// ========== CARGA DE KPIs ==========

function loadKPIs() {
    const total = document.getElementById('kpiTotal');
    const phase1 = document.getElementById('kpiPhase1');
    const phase2 = document.getElementById('kpiPhase2');
    const finalExam = document.getElementById('kpiFinalExam');
    const bloqueados = document.getElementById('kpiBloqueados');

    if (total) total.textContent = totalStudents;
    if (phase1) phase1.textContent = allStudents.filter(s => s.current_phase === 'phase_1').length;
    if (phase2) phase2.textContent = allStudents.filter(s => s.current_phase === 'phase_2').length;
    if (finalExam) finalExam.textContent = allStudents.filter(s => s.current_phase === 'final_exam').length;
    if (bloqueados) {
        bloqueados.textContent = allStudents.filter(s => {
            const fa = s.failed_attempts || {};
            return (fa.phase_1 || 0) >= 3 || (fa.phase_2 || 0) >= 3 || (fa.final_exam || 0) >= 1;
        }).length;
    }
}

// ========== FILTROS ==========

function filterStudents() {
    const cohortFilter = document.getElementById('cohortFilter');
    const phaseFilter = document.getElementById('phaseFilter');
    const searchInput = document.getElementById('searchInput');

    if (!cohortFilter || !phaseFilter || !searchInput) return;

    const cohortVal = cohortFilter.value;
    const phaseVal = phaseFilter.value;
    const searchVal = searchInput.value.toLowerCase();

    const filtered = allStudents.filter(student => {
        const studentName = (student.name || '').toLowerCase();
        const studentEmail = (student.email || '').toLowerCase();
        const matchesCohort = !cohortVal || student.cohort_id === cohortVal;
        const matchesPhase = !phaseVal || student.current_phase === phaseVal;
        const matchesSearch = studentName.includes(searchVal) || studentEmail.includes(searchVal);
        return matchesCohort && matchesPhase && matchesSearch;
    });

    renderStudentTable(filtered);
}

function setupFilters() {
    const cohortFilter = document.getElementById('cohortFilter');
    const phaseFilter = document.getElementById('phaseFilter');
    const searchInput = document.getElementById('searchInput');

    if (cohortFilter) cohortFilter.addEventListener('change', filterStudents);
    if (phaseFilter) phaseFilter.addEventListener('change', filterStudents);
    if (searchInput) searchInput.addEventListener('input', filterStudents);
}

// ========== GESTIÓN DE FASES ==========

function updateStudentPhase(studentId, newPhase) {
    const student = allStudents.find(s => s.student_id === studentId);
    if (!student) return;

    if (!confirm("Promover al aluno " + student.name + " a " + newPhase + "?")) {
        return;
    }

    const select = document.querySelector('.phase-select[data-student="' + studentId + '"]');
    if (!select) return;

    const saveBtn = select.nextElementSibling;
    if (saveBtn) saveBtn.disabled = true;
    select.disabled = true;

    apiCall("PUT", "/students/" + studentId + "/phase", { phase: newPhase }).then(response => {
        if (response && response.new_phase) {
            showToast("Fase atualizada de " + response.previous_phase + " a " + response.new_phase, "success");
            loadStudents();
        } else {
            showToast("Erro na resposta", "error");
        }
    }).catch(err => {
        showToast("Erro: " + err.message, "error");
    }).finally(() => {
        select.disabled = false;
        if (saveBtn) saveBtn.disabled = false;
    });
}

// ========== MODAL DE HISTORIAL ==========

async function openStudentHistoryModal(studentId) {
    const student = allStudents.find(s => s.student_id === studentId);
    if (!student) return;

    const studentsSection = document.getElementById('studentsSection');
    const historySection = document.getElementById('historySection');
    if (studentsSection) studentsSection.style.display = 'none';
    if (historySection) historySection.style.display = 'block';

    const title = document.getElementById('historyTitle');
    if (title) title.textContent = "Historico de " + student.name;

    const studentInfo = document.getElementById('studentInfo');
    if (studentInfo) {
        studentInfo.innerHTML = "<p><strong>Email:</strong> " + student.email + "</p><p><strong>Cohorte:</strong> " + (student.cohort_id || 'Nenhum') + "</p><p><strong>Fase Atual:</strong> " + (student.current_phase || 'initial') + "</p>";
    }

    const response = await apiCall("GET", "/students/" + studentId + "/quizzes");
    const tbody = document.getElementById('historyTable');
    if (!tbody) return;

    tbody.innerHTML = "";

    if (!response || !response.quizzes || response.quizzes.length === 0) {
        tbody.innerHTML = "<tr><td colspan='5'>Nenhum quiz realizado ainda.</td></tr>";
        return;
    }

    response.quizzes.forEach(function(q, index) {
        const tr = document.createElement('tr');
        const status = q.status || 'completed';
        const score = q.score_percentage !== null ? q.score_percentage + '%' : '0%';
        tr.innerHTML = "<td>" + (index + 1) + "</td><td>" + (q.topic || '-') + "</td><td><span class='" + status.toLowerCase() + "'>" + status + "</span></td><td>" + score + "</td><td>" + (q.created_at ? new Date(q.created_at).toLocaleDateString('pt-BR') : '-') + "</td>";
        tbody.appendChild(tr);
    });
}

function closeStudentHistory() {
    const studentsSection = document.getElementById('studentsSection');
    const historySection = document.getElementById('historySection');
    if (studentsSection) studentsSection.style.display = 'block';
    if (historySection) historySection.style.display = 'none';
}

// ========== CARGA DE COHORTES ==========

async function loadCohorts() {
    const response = await apiCall("GET", "/cohorts");
    if (!response || !response.cohorts) return;
    const tbody = document.getElementById('cohortsTable');
    if (!tbody) return;

    tbody.innerHTML = "";
    response.cohorts.forEach(function(cohort) {
        var percentage = cohort.max_students > 0 ? Math.round((cohort.current_count / cohort.max_students) * 100) : 0;
        var tr = document.createElement('tr');
        tr.innerHTML = "<td>" + cohort.cohort_id + "</td><td>" + cohort.current_count + "</td><td>" + cohort.max_students + "</td><td>" + percentage + "%</td>";
        tbody.appendChild(tr);
    });
}

// ========== EVENTOS ==========

function setupEvents() {
    setupFilters();

    const closeBtn = document.getElementById('closeHistoryBtn');
    if (closeBtn) {
        closeBtn.addEventListener('click', closeStudentHistory);
    }

    const logoutBtn = document.getElementById('logoutBtn');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', function(e) {
            e.preventDefault();
            logout();
        });
    }
}

// ========== HERRAMIENTAS ==========

function showToast(message, type) {
    alert((type === 'success' ? 'Sucesso' : 'Erro') + ": " + message);
}

function logout() {
    localStorage.clear();
    window.location.href = "index.html";
}

// Estado global
var allStudents = [];
var totalStudents = 0;

// Inicialización automática al cargar el DOM
document.addEventListener("DOMContentLoaded", () => {
    initTeacherDashboard();
});
