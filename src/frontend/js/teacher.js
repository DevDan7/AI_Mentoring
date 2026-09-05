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
        saveBtn.disabled = false;
    });
}

// ========== CARGA DE KPIs ==========

function loadKPIs() {
    document.getElementById('kpiTotal').textContent = totalStudents;
    document.getElementById('kpiPhase1').textContent = allStudents.filter(s => s.current_phase === 'phase_1').length;
    document.getElementById('kpiPhase2').textContent = allStudents.filter(s => s.current_phase === 'phase_2').length;
    document.getElementById('kpiFinalExam').textContent = allStudents.filter(s => s.current_phase === 'final_exam').length;
    document.getElementById('kpiBloqueados').textContent = allStudents.filter(s => {
        const fa = s.failed_attempts || {};
        return (fa.phase_1 || 0) >= 3 || (fa.phase_2 || 0) >= 3 || (fa.final_exam || 0) >= 1;
    }).length;
}

// ========== FILTROS ==========

function filterStudents() {
    const cohortVal = document.getElementById('cohortFilter').value;
    const phaseVal = document.getElementById('phaseFilter').value;
    const searchVal = document.getElementById('searchInput').value.toLowerCase();
    let filtered = allStudents.filter(student => {
        const matchesCohort = !cohortVal || student.cohort_id === cohortVal;
        const matchesPhase = !phaseVal || student.current_phase === phaseVal;
        const matchesSearch = student.name.toLowerCase().includes(searchVal) || student.email.toLowerCase().includes(searchVal);
        return matchesCohort && matchesPhase && matchesSearch;
    });
    renderStudentTable(filtered);
}

function setupFilters() {
    document.getElementById('cohortFilter').addEventListener('change', filterStudents);
    document.getElementById('phaseFilter').addEventListener('change', filterStudents);
    document.getElementById('searchInput').addEventListener('input', filterStudents);
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
    saveBtn.disabled = true;
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
        saveBtn.disabled = false;
    });
}

// ========== MODAL DE HISTORIAL ==========

async function openStudentHistoryModal(studentId) {
    const student = allStudents.find(s => s.student_id === studentId);
    if (!student) return;

    const title = document.getElementById('historyTitle');
    title.textContent = "Historico de " + student.name;

    const studentInfo = document.getElementById('studentInfo');
    studentInfo.innerHTML = "<p><strong>Email:</strong> " + student.email + "</p><p><strong>Cohorte:</strong> " + (student.cohort_id || 'Nenhum') + "</p><p><strong>Fase Atual:</strong> " + (student.current_phase || 'initial') + "</p>";

    const response = await apiCall("GET", "/students/" + studentId + "/quizzes");
    const tbody = document.getElementById('historyTable');
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

// ========== CARGA DE COHORTES ==========

async function loadCohorts() {
    const response = await apiCall("GET", "/cohorts");
    if (!response || !response.cohorts) return;
    const tbody = document.getElementById('cohortsTable');
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
    document.getElementById('searchInput').addEventListener('input', filterStudents);
    document.getElementById('cohortFilter').addEventListener('change', filterStudents);
    document.getElementById('phaseFilter').addEventListener('change', filterStudents);

    document.querySelectorAll('.btn-history').forEach(function(btn) {
        btn.addEventListener('click', function() {
            openStudentHistoryModal(btn.dataset.student);
        });
    });

    document.querySelectorAll('.phase-select').forEach(function(select) {
        select.addEventListener('change', function(e) {
            updateStudentPhase(e.target.dataset.student, e.target.value);
        });
    });

    document.querySelectorAll('.btn-save-phase').forEach(function(btn) {
        btn.addEventListener('click', function(e) {
            var select = e.target.previousElementSibling;
            updateStudentPhase(e.target.dataset.student, select.value);
        });
    });

    document.getElementById('logoutBtn').addEventListener('click', function(e) {
        e.preventDefault();
        logout();
    });
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
