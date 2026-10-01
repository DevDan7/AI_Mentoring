// Render compartido del desglose de explicaciones (quiz.html y results.html).
// Muestra la opción correcta con su explicación y cada opción incorrecta con la
// suya, en vez de mostrar explicación solo cuando el alumno responde mal.

function renderExplanationBlock(options) {
    if (!options || !options.length) return '';

    const escLocal = (v) => String(v === undefined || v === null ? '' : v)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');

    // filter, no find: en preguntas "Escolha duas" hay más de una correcta y antes la
    // segunda no aparecía en ningún lado (ni como correcta ni en "outras opções").
    const correct = options.filter(o => o.is_correct);
    const others = options.filter(o => !o.is_correct);

    let html = '<div class="explanation-block">';
    if (correct.length) {
        html += `<p><strong>${escLocal(t("explanation.general"))}</strong></p>`;
        correct.forEach(c => {
            html += `<p><strong>${escLocal(c.key)}) ${escLocal(c.text)}</strong></p>`;
            html += `<p>${escLocal(c.explanation)}</p>`;
        });
    }
    if (others.length) {
        html += `<p><strong>${escLocal(t("explanation.otherOptions"))}</strong></p><ul>`;
        others.forEach(o => {
            html += `<li><strong>${escLocal(o.key)}) ${escLocal(o.text)}:</strong> ${escLocal(o.explanation)}</li>`;
        });
        html += '</ul>';
    }
    html += '</div>';
    return html;
}
