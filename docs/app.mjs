import { RULES, answerTime, drawExam, markExam } from "./exam.mjs";

const screen = document.querySelector("#screen");
const category = document.querySelector("#category");
const nav = [...document.querySelectorAll("[data-page]")];
const pageNames = { home: "Start", study: "Nauka", exam: "Próbny egzamin" };
const partNames = { basic: "Wiedza podstawowa", specialist: "Wiedza specjalistyczna" };
const escapeMap = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
const h = value => String(value).replace(/[&<>"']/g, character => escapeMap[character]);
const load = key => {
  try { return JSON.parse(localStorage.getItem(`prawko-${key}`)); } catch { return null; }
};
const save = (key, value) => {
  try { localStorage.setItem(`prawko-${key}`, JSON.stringify(value)); } catch { /* Storage can be disabled. */ }
};

let catalog;
let page = "home";
let study = null;
let exam = null;
let result = null;
let clock = null;
let progress = null;
let hasPjm = false;

const selectedQuestions = () => catalog.questions.filter(q => q.categories.includes(category.value));
const categoryLabel = value => value === "PT" ? "Tramwaj" : value;
const choiceLabel = (q, answer) => {
  const text = q.choices.find(([key]) => key === answer)?.[1];
  if (!text) return "Brak odpowiedzi";
  return q.kind === "basic" ? text : `${answer}. ${text}`;
};
const button = (text, action, { primary = false, disabled = false, value = "" } = {}) =>
  `<button type="button" class="button${primary ? " primary" : ""}" data-action="${action}"
    data-value="${h(value)}"${disabled ? " disabled" : ""}>${h(text)}</button>`;

function heading(title, description = "") {
  return `<header class="heading"><h1 tabindex="-1">${h(title)}</h1>
    ${description ? `<p class="lead">${h(description)}</p>` : ""}</header>`;
}

function focusTitle() {
  screen.querySelector("h1")?.focus({ preventScroll: true });
  screen.querySelector("h1")?.scrollIntoView({ block: "nearest" });
}

function activeAttempt() {
  return Boolean(exam);
}

function updateNavigation() {
  document.querySelector("#section").textContent = pageNames[page];
  for (const item of nav) {
    if (item.closest("nav")) {
      if (item.dataset.page === page) item.setAttribute("aria-current", "page");
      else item.removeAttribute("aria-current");
    }
    item.disabled = activeAttempt();
  }
  category.disabled = activeAttempt() || !catalog;
}

function showPage(next) {
  if (!catalog || activeAttempt()) return;
  page = next;
  study = null;
  result = null;
  renderPage();
  focusTitle();
}

function renderPage() {
  updateNavigation();
  if (page === "home") renderHome();
  if (page === "study") renderStudy();
  if (page === "exam") renderExamStart();
}

function renderHome() {
  screen.innerHTML = `<section class="hero">
    <h1 tabindex="-1">Teoria na prawo jazdy</h1>
    <p>Ucz się na pytaniach z oficjalnego katalogu albo sprawdź się w próbnym egzaminie.</p>
  </section>
  <div class="tiles">
    <section class="tile">
      <span class="tile-icon" aria-hidden="true">▤</span>
      <h2>Nauka działami</h2>
      <p>Wybierz temat i sprawdzaj odpowiedzi na bieżąco. Zdjęcia i filmy możesz oglądać we własnym tempie.</p>
      ${button("Wybierz dział", "open-study", { primary: true })}
    </section>
    <section class="tile">
      <span class="tile-icon" aria-hidden="true">◷</span>
      <h2>Próbny egzamin</h2>
      <p>Rozwiąż 32 pytania na czas i przejrzyj odpowiedzi po zakończeniu próby.</p>
      ${button("Przejdź do egzaminu", "open-exam")}
    </section>
  </div>`;
}

function solved(q) {
  return progress[category.value]?.[q.id] === q.revision;
}

function recordCorrect(q) {
  const byCategory = progress[category.value] ??= {};
  byCategory[q.id] = q.revision;
  save("progress", progress);
}

function renderStudy() {
  const questions = selectedQuestions();
  const available = questions.filter(q => !q.missingMedia);
  const missing = questions.length - available.length;
  const tiles = [["all", "Wszystkie pytania"], ...Object.entries(catalog.topics)]
    .map(([id, name]) => {
      const matching = id === "all" ? available : available.filter(q => q.topics.includes(id));
      const done = matching.filter(solved).length;
      return { id, name, total: matching.length, done };
    }).filter(({ total }) => total);

  screen.innerHTML = `${heading("Nauka działami", "Wybierz dział. Po każdym pytaniu zobaczysz, czy Twoja odpowiedź jest poprawna.")}
    ${missing ? `<p class="notice">${missing === 1 ? "Jedno pytanie jest" : `${missing} pytania są`} chwilowo niedostępne z powodu brakujących multimediów.</p>` : ""}
    <div class="topics">${tiles.map(({ id, name, total, done }) =>
      `<button type="button" class="topic" data-action="start-study" data-value="${h(id)}">
        <strong>${h(name)}</strong><span>${done} z ${total} rozwiązanych</span>
        <progress class="progress" value="${done}" max="${total}" aria-label="Poprawnie rozwiązane pytania"></progress>
      </button>`).join("")}</div>`;
}

function startStudy(topic) {
  const questions = selectedQuestions().filter(q => !q.missingMedia && (topic === "all" || q.topics.includes(topic)));
  if (!questions.length) return;
  study = {
    name: topic === "all" ? "Wszystkie pytania" : catalog.topics[topic],
    questions: [...questions.filter(q => !solved(q)), ...questions.filter(solved)],
    index: 0,
    answer: null,
    attempted: 0,
    correct: 0,
  };
  renderStudyQuestion();
}

function mediaNode(media, { controlled = true, eager = false } = {}) {
  const element = document.createElement(media.type === "video" ? "video" : "img");
  element.className = "media";
  if (media.type === "video") {
    element.controls = controlled;
    element.playsInline = true;
    element.muted = !controlled;
    element.preload = eager ? "auto" : "metadata";
    element.disablePictureInPicture = !controlled;
    if (!controlled) element.setAttribute("disableRemotePlayback", "");
  } else {
    element.alt = "Materiał ilustracyjny do pytania";
    element.decoding = "async";
  }
  element.src = `media/${encodeURIComponent(media.file)}`;
  return element;
}

function mountMedia(container, media, options = {}) {
  if (!media) return null;
  const element = options.element ?? mediaNode(media, options);
  container.replaceChildren(element);
  const reportError = () => {
    if (container.querySelector(".media-error")) return;
    const status = document.createElement("p");
    status.className = "media-error";
    status.setAttribute("role", "status");
    status.textContent = "Nie udało się wczytać multimediów.";
    if (options.controlled !== false) {
      const retry = document.createElement("button");
      retry.type = "button";
      retry.className = "button";
      retry.textContent = "Wczytaj ponownie";
      retry.addEventListener("click", () => mountMedia(container, media, options));
      status.append(" ", retry);
    }
    container.append(status);
    options.onError?.();
  };
  element.addEventListener("error", reportError, { once: true });
  if (element.error || (element instanceof HTMLImageElement && element.complete && !element.naturalWidth)) {
    reportError();
  }
  return element;
}

function pjmMarkup(question) {
  return question.pjm ? `<details class="pjm"><summary>Tłumaczenie migowe (PJM)</summary>
    <div data-pjm="${h(question.id)}"></div></details>` : "";
}

function mountPjm(container, question) {
  if (!container || container.childElementCount) return;
  for (const [key, media] of Object.entries(question.pjm ?? {})) {
    const label = document.createElement("p");
    label.textContent = key === "question" ? "Treść pytania" : `Treść odpowiedzi ${key}`;
    const target = document.createElement("div");
    container.append(label, target);
    mountMedia(target, media);
  }
}

function choicesMarkup(question, disabled = false) {
  return `<div class="answers${question.kind === "basic" ? " binary" : ""}" role="group" aria-label="Odpowiedzi">
    ${question.choices.map(([key, text]) => `<button type="button" class="answer" data-action="choose"
     data-value="${h(key)}" aria-pressed="false"${disabled ? " disabled" : ""}>
      ${question.kind === "specialist" ? `<span class="letter">${h(key)}</span>` : ""}<span>${h(text)}</span></button>`).join("")}
  </div>`;
}

function paintAnswers(chosen, correct = null) {
  for (const option of screen.querySelectorAll(".answer")) {
    const value = option.dataset.value;
    option.classList.toggle("selected", value === chosen);
    option.setAttribute("aria-pressed", String(value === chosen));
    if (correct !== null) {
      option.disabled = true;
      option.classList.toggle("good", value === correct);
      option.classList.toggle("bad", value === chosen && value !== correct);
    }
  }
}

function renderStudyQuestion() {
  const { questions, index, name } = study;
  const q = questions[index];
  screen.innerHTML = `<div class="toolbar">
      ${button("Działy", "leave-study")}
      <span class="muted">${h(name)}</span>
    </div>
    <article class="panel question">
      <div class="question-meta"><p>Pytanie ${index + 1} z ${questions.length}</p>
        <p>${partNames[q.kind]} · nr ${h(q.id)}</p></div>
      <h1 tabindex="-1">${h(q.text)}</h1>
      <div id="question-media"></div>${pjmMarkup(q)}
      ${choicesMarkup(q)}
      <p class="feedback" id="feedback" role="status" hidden></p>
      <div class="actions">
        ${button("Sprawdź odpowiedź", "check-study", { primary: true, disabled: true })}
        ${button(index + 1 === questions.length ? "Zakończ naukę" : "Pomiń pytanie", "next-study")}
      </div>
    </article>`;
  mountMedia(screen.querySelector("#question-media"), q.media);
  focusTitle();
}

function checkStudy() {
  if (study.answer === null || study.checked) return;
  const q = study.questions[study.index];
  study.checked = true;
  study.attempted++;
  const correct = study.answer === q.answer;
  if (correct) {
    study.correct++;
    recordCorrect(q);
  }
  paintAnswers(study.answer, q.answer);
  const feedback = screen.querySelector("#feedback");
  feedback.classList.add(correct ? "good" : "bad");
  feedback.hidden = false;
  feedback.textContent = correct ? "Poprawna odpowiedź." : `Błędna odpowiedź. Prawidłowa odpowiedź: ${choiceLabel(q, q.answer)}`;
  screen.querySelector('[data-action="check-study"]').hidden = true;
  const next = screen.querySelector('[data-action="next-study"]');
  next.classList.add("primary");
  if (study.index + 1 < study.questions.length) next.textContent = "Następne pytanie";
  next.focus();
}

function studyNext() {
  if (study.index + 1 < study.questions.length) {
    study.index++;
    study.checked = false;
    study.answer = null;
    renderStudyQuestion();
    return;
  }
  screen.innerHTML = `${heading("Koniec sesji nauki", study.name)}
    <section class="panel"><p>Poprawne odpowiedzi w tej sesji: <strong>${study.correct} z ${study.attempted}</strong>.</p>
      ${button("Wróć do działów", "leave-study", { primary: true })}</section>`;
  focusTitle();
}

function renderExamStart() {
  const categoryName = categoryLabel(category.value);
  const pjmOption = hasPjm ? `<div class="exam-options">
    <label><input type="checkbox" id="extended-pjm"> Tryb PJM z wydłużonym czasem</label>
    <p class="lead">40 minut i tłumaczenia migowe tam, gdzie zostały udostępnione.</p></div>` : "";
  screen.innerHTML = `${heading("Próbny egzamin", category.value === "PT"
    ? "Pozwolenie na kierowanie tramwajem" : `Kategoria ${categoryName}`)}
    <section class="panel">
      <dl class="info-grid">
        <div><dt>Pytania</dt><dd>32</dd></div>
        <div><dt>Czas</dt><dd id="exam-duration">25 min</dd></div>
        <div><dt>Próg zaliczenia</dt><dd>68 / 74</dd></div>
      </dl>
      <p class="lead exam-options">Najpierw 20 pytań TAK/NIE, potem 12 pytań A/B/C. Do zamkniętego pytania nie można wrócić. Odpowiedzi sprawdzisz po zakończeniu.</p>
      ${pjmOption}
      ${button("Rozpocznij egzamin", "start-exam", { primary: true })}
    </section>`;
}

function startExam() {
  try {
    const questions = drawExam(catalog.questions, category.value);
    const pjm = screen.querySelector("#extended-pjm")?.checked ?? false;
    const minutes = pjm ? RULES.pjmMinutes : RULES.standardMinutes;
    result = null;
    exam = { questions, pjm, category: category.value, index: 0, answers: [],
      deadline: Date.now() + minutes * 60000, preload: null };
    updateNavigation();
    renderExamQuestion();
    clock = window.setInterval(tickExam, 150);
  } catch (error) {
    exam = null;
    updateNavigation();
    screen.querySelector(".panel").insertAdjacentHTML("beforeend", `<p class="notice" role="alert">${h(error.message)}</p>`);
  }
}

function renderExamQuestion() {
  const run = exam;
  const { questions, index, pjm } = run;
  const question = questions[index];
  const basic = question.kind === "basic";
  run.phase = basic ? "reading" : "answering";
  run.phaseDeadline = Date.now() + (basic ? (pjm ? 40 : RULES.basic.reading) : answerTime(question.kind, pjm)) * 1000;
  const existing = run.preload?.index === index ? run.preload.element : null;
  run.preload = null;

  screen.innerHTML = `<div class="toolbar">
    <span class="clock" id="global-time" role="timer" aria-label="Czas do końca egzaminu"></span>
    ${button("Zakończ egzamin", "ask-end-exam")}
  </div>
  <article class="panel question">
    <div class="question-meta"><p>${partNames[question.kind]} · ${basic ? index + 1 : index - 19} / ${basic ? 20 : 12}</p>
      <p>Wartość pytania: ${question.points} pkt</p></div>
    <h1 tabindex="-1">${h(question.text)}</h1>
    <div id="question-media"${basic && question.media?.type === "video" ? " hidden" : ""}></div>
    ${pjm ? pjmMarkup(question) : ""}
    <div class="actions">
      <span id="phase-label" role="status"></span>
      <span class="clock" id="question-time" role="timer" aria-label="Czas tej części pytania"></span>
    </div>
    ${choicesMarkup(question, basic)}
    <div class="actions">
      ${button(question.media?.type === "video" ? "Odtwórz film" : "Przejdź do odpowiedzi", "start-answer", { primary: true })}
      ${button(index === questions.length - 1 ? "Wyświetl wynik" : "Następne pytanie", "next-exam", { primary: true })}
    </div>
    <p class="notice" id="exam-media-error" role="status" hidden></p>
  </article>
  <dialog id="end-dialog" aria-labelledby="end-heading"><h2 id="end-heading">Zakończyć egzamin?</h2>
    <p>Za pominięte pytania otrzymasz 0 punktów.</p>
    <div class="actions">${button("Wróć do pytania", "cancel-end-exam")}${button("Zakończ egzamin", "confirm-end-exam", { primary: true })}</div>
  </dialog>`;

  run.videoFailed = false;
  run.media = mountMedia(screen.querySelector("#question-media"), question.media, {
    element: existing, controlled: false, eager: true,
    onError: () => {
      if (run !== exam || run.index !== index) return;
      run.videoFailed = true;
      const message = screen.querySelector("#exam-media-error");
      message.textContent = "Materiał jest niedostępny. Możesz pominąć pytanie albo udzielić odpowiedzi.";
      message.hidden = false;
      if (run.phase === "playing") enterAnswer();
    },
  });
  syncPhase();
  if (!basic && question.media?.type === "video") playExamVideo();
  const ahead = questions[index + 1]?.media;
  if (ahead) run.preload = { index: index + 1, element: mediaNode(ahead, { controlled: false, eager: true }) };
  focusTitle();
  tickExam();
}

function syncPhase() {
  const phase = exam.phase;
  screen.querySelector("#phase-label").textContent = {
    reading: "Czas na przeczytanie pytania",
    playing: "Odtwarzanie filmu",
    answering: "Czas na odpowiedź",
  }[phase];
  screen.querySelector("#question-time").hidden = phase === "playing";
  const start = screen.querySelector('[data-action="start-answer"]');
  const next = screen.querySelector('[data-action="next-exam"]');
  start.hidden = phase !== "reading";
  next.hidden = phase !== "answering";
  for (const option of screen.querySelectorAll(".answer")) option.disabled = phase !== "answering";
  updateClock();
}

function enterAnswer() {
  if (!exam) return;
  const question = exam.questions[exam.index];
  const hadControl = document.activeElement === screen.querySelector('[data-action="start-answer"]');
  exam.phase = "answering";
  exam.phaseDeadline = Date.now() + answerTime(question.kind, exam.pjm) * 1000;
  syncPhase();
  if (hadControl) screen.querySelector(".answer")?.focus();
}

function playExamVideo() {
  const run = exam;
  const { media, index } = run;
  const active = () => run === exam && run.index === index;
  const afterVideo = () => {
    if (active() && run.phase === "playing") enterAnswer();
  };
  media.addEventListener("ended", afterVideo, { once: true });
  media.play().catch(() => {
    if (!active() || run.videoFailed) return;
    const nextTry = document.createElement("button");
    nextTry.type = "button";
    nextTry.className = "button";
    nextTry.textContent = "Uruchom film";
    nextTry.addEventListener("click", () => {
      if (!active()) return;
      media.play().then(() => nextTry.remove()).catch(() => {
        nextTry.remove();
        const message = screen.querySelector("#exam-media-error");
        message.textContent = "Przeglądarka nie mogła odtworzyć filmu.";
        message.hidden = false;
        afterVideo();
      });
    });
    media.after(nextTry);
    nextTry.focus();
  });
}

function startAnswer() {
  if (!exam || exam.phase !== "reading") return;
  if (exam.questions[exam.index].media?.type === "video") {
    screen.querySelector("#question-media").hidden = false;
    if (!exam.videoFailed) {
      exam.phase = "playing";
      exam.phaseDeadline = exam.deadline;
      syncPhase();
      playExamVideo();
      return;
    }
  }
  enterAnswer();
}

function examNext() {
  if (!exam || exam.phase !== "answering") return;
  exam.media?.pause?.();
  if (++exam.index === exam.questions.length) finishExam();
  else renderExamQuestion();
}

function formatTime(seconds) {
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

function setClock(selector, seconds, display) {
  const node = screen.querySelector(selector);
  if (node.textContent !== display) node.textContent = display;
  node.classList.toggle("urgent", seconds <= 5);
}

function updateClock(now = Date.now()) {
  if (!exam) return;
  const global = Math.max(0, Math.ceil((exam.deadline - now) / 1000));
  const current = Math.max(0, Math.ceil((Math.min(exam.phaseDeadline, exam.deadline) - now) / 1000));
  setClock("#global-time", global, formatTime(global));
  setClock("#question-time", current, `${current} s`);
}

function tickExam() {
  if (!exam) return;
  const now = Date.now();
  if (now >= exam.deadline) { finishExam(); return; }
  if (now >= exam.phaseDeadline) {
    if (exam.phase === "reading") startAnswer();
    else if (exam.phase === "answering") examNext();
    return;
  }
  updateClock(now);
}

function finishExam() {
  if (!exam) return;
  window.clearInterval(clock);
  exam.media?.pause?.();
  result = { ...markExam(exam.questions, exam.answers), category: exam.category };
  exam = null;
  updateNavigation();
  renderResult();
  focusTitle();
}

function renderResult() {
  const correct = result.rows.filter(row => row.correct).length;
  const omitted = result.rows.filter(row => row.answer === null).length;
  const wrong = result.rows.length - correct - omitted;
  screen.innerHTML = `${heading("Wynik egzaminu", result.category === "PT"
    ? "Pozwolenie na kierowanie tramwajem" : `Kategoria ${categoryLabel(result.category)}`)}
    <section class="panel">
      <h2 class="${result.passed ? "correct-text" : "incorrect-text"}">${result.passed ? "Wynik pozytywny" : "Wynik negatywny"} · ${result.points} / 74 pkt</h2>
      <p class="lead">${correct} poprawnych · ${wrong} błędnych · ${omitted} bez odpowiedzi</p>
      <div class="actions result-actions">${button("Nowy egzamin", "open-exam", { primary: true })}</div>
    </section>
    <h2 class="review-title">Przegląd odpowiedzi</h2>
    <label class="category">Pokaż
      <select id="review-filter"><option value="all">Wszystkie</option><option value="errors">Błędy i pominięte</option><option value="correct">Poprawne</option></select>
    </label>
    <div class="review" id="review"></div>`;
  displayReview("all");
}

function displayReview(filter) {
  const review = screen.querySelector("#review");
  review.innerHTML = result.rows.map(({ question: q, answer, correct, points }, i) => {
    if ((filter === "correct" && !correct) || (filter === "errors" && correct)) return "";
    const label = correct ? "Poprawna" : answer === null ? "Bez odpowiedzi" : "Błędna";
    return `<details data-review="${i}"><summary>${i + 1}. ${h(q.text)}
      <span class="${correct ? "correct-text" : "incorrect-text"}">${label} · ${points}/${q.points} pkt</span>
    </summary><div class="review-content">
      <p>Twoja odpowiedź: <strong>${h(choiceLabel(q, answer))}</strong></p>
      ${correct ? "" : `<p>Prawidłowa odpowiedź: <strong>${h(choiceLabel(q, q.answer))}</strong></p>`}
      <div class="review-media"></div>${pjmMarkup(q)}
    </div></details>`;
  }).join("");
  if (!review.childElementCount) review.textContent = "Brak pytań spełniających ten warunek.";
}

category.addEventListener("change", () => {
  if (activeAttempt()) return;
  save("category", category.value);
  showPage(page);
});

for (const item of nav) item.addEventListener("click", () => showPage(item.dataset.page));

screen.addEventListener("change", event => {
  if (event.target.id === "review-filter") displayReview(event.target.value);
  if (event.target.id === "extended-pjm") {
    screen.querySelector("#exam-duration").textContent = event.target.checked ? "40 min" : "25 min";
  }
});

screen.addEventListener("toggle", event => {
  const detail = event.target;
  if (!(detail instanceof HTMLDetailsElement)) return;
  if (!detail.open) {
    for (const video of detail.querySelectorAll("video")) video.pause();
    return;
  }
  if (detail.dataset.review !== undefined && result) {
    const mediaTarget = detail.querySelector(".review-media");
    if (!mediaTarget.childElementCount) mountMedia(mediaTarget, result.rows[Number(detail.dataset.review)].question.media);
  }
  if (detail.classList.contains("pjm")) {
    const target = detail.querySelector("[data-pjm]");
    const question = catalog.byId.get(target.dataset.pjm);
    mountPjm(target, question);
  }
}, true);

screen.addEventListener("click", event => {
  const target = event.target.closest("[data-action]");
  if (!target || target.disabled) return;
  const { action, value } = target.dataset;
  if (exam && Date.now() >= exam.deadline && action !== "cancel-end-exam") { finishExam(); return; }
  if (exam && ["choose", "next-exam", "start-answer"].includes(action) && Date.now() >= exam.phaseDeadline) {
    tickExam();
    return;
  }
  switch (action) {
    case "open-study":
    case "leave-study": showPage("study"); break;
    case "open-exam": showPage("exam"); break;
    case "start-study": startStudy(value); break;
    case "check-study": checkStudy(); break;
    case "next-study": studyNext(); break;
    case "start-exam": startExam(); break;
    case "start-answer": startAnswer(); break;
    case "next-exam": examNext(); break;
    case "ask-end-exam": screen.querySelector("#end-dialog").showModal(); break;
    case "cancel-end-exam": screen.querySelector("#end-dialog").close(); break;
    case "confirm-end-exam": finishExam(); break;
    case "choose":
      if (exam?.phase === "answering") exam.answers[exam.index] = value;
      else if (page === "study" && study && !study.checked) {
        study.answer = value;
        screen.querySelector('[data-action="check-study"]').disabled = false;
      } else break;
      paintAnswers(value);
      break;
  }
});

async function loadCatalog() {
  const pointer = await fetch("data/current.json", { cache: "no-store" });
  if (!pointer.ok) throw new Error("No active catalog");
  const { catalog: file } = await pointer.json();
  if (!/^catalog-[a-f0-9]{16}\.json$/.test(file)) throw new Error("Invalid catalog path");
  const response = await fetch(`data/${file}`);
  if (!response.ok) throw new Error("Catalog unavailable");
  const contents = await response.json();
  contents.byId = new Map(contents.questions.map(q => [q.id, q]));
  hasPjm = contents.questions.some(q => q.pjm);
  return contents;
}

try {
  catalog = await loadCatalog();
  const categories = [...new Set(catalog.questions.flatMap(q => q.categories))];
  const order = ["AM", "A1", "A2", "A", "B1", "B", "C1", "C", "D1", "D", "T", "PT"];
  category.innerHTML = order.filter(value => categories.includes(value))
    .map(value => `<option value="${value}">${h(categoryLabel(value))}</option>`).join("");
  const previous = load("category");
  category.value = categories.includes(previous) ? previous : "B";
  const savedProgress = load("progress");
  progress = savedProgress && typeof savedProgress === "object" ? savedProgress : {};
  document.querySelector("#version").textContent = `Katalog MI · ${catalog.version}`;
  document.querySelector("#source").href = catalog.source;
  document.querySelector("#credits").href = catalog.credits ?? document.querySelector("#credits").href;
  renderPage();
} catch {
  document.querySelector("#version").textContent = "Katalog niedostępny";
  screen.innerHTML = `${heading("Nie udało się wczytać katalogu")}
    <p class="panel">Odśwież stronę. Jeśli komunikat się powtarza, sprawdź, czy katalog został zaimportowany i aktywowany.</p>`;
}
