export const RULES = {
  basic: { quotas: { 3: 10, 2: 6, 1: 4 }, reading: 20, answering: 15 },
  specialist: { quotas: { 3: 6, 2: 4, 1: 2 }, answering: 50 },
  standardMinutes: 25,
  pjmMinutes: 40,
  pass: 68,
};

function shuffled(values, random) {
  const result = [...values];
  for (let i = result.length - 1; i > 0; i--) {
    const j = Math.floor(random() * (i + 1));
    [result[i], result[j]] = [result[j], result[i]];
  }
  return result;
}

export function drawExam(questions, category, random = Math.random) {
  const eligible = questions.filter(q => q.categories.includes(category) && !q.missingMedia);
  return ["basic", "specialist"].flatMap(kind => {
    const chosen = Object.entries(RULES[kind].quotas).flatMap(([points, count]) => {
      const pool = eligible.filter(q => q.kind === kind && q.points === Number(points));
      if (pool.length < count) throw new Error("Katalog ma za mało pytań do przeprowadzenia egzaminu.");
      return shuffled(pool, random).slice(0, count);
    });
    return shuffled(chosen, random);
  });
}

export function markExam(questions, answers) {
  const rows = questions.map((question, index) => {
    const answer = answers[index] ?? null;
    const correct = answer === question.answer;
    return { question, answer, correct, points: correct ? question.points : 0 };
  });
  const points = rows.reduce((total, item) => total + item.points, 0);
  return { rows, points, passed: points >= RULES.pass };
}

export function answerTime(kind, pjm) {
  return kind === "specialist" && pjm ? 75 : RULES[kind].answering;
}
