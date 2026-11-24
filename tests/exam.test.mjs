import assert from "node:assert/strict";
import test from "node:test";

import { RULES, answerTime, drawExam, markExam } from "../public/exam.mjs";

const questions = Object.keys(RULES.basic.quotas).flatMap(points =>
  ["basic", "specialist"].flatMap(kind =>
    Array.from({ length: 18 }, (_, i) => ({
      id: `${kind}-${points}-${i}`, categories: ["B"], kind, points: Number(points), answer: "T",
      missingMedia: i === 17,
    }))));

test("the mock exam uses the official quotas and omits unavailable media", () => {
  const drawn = drawExam(questions, "B", () => 0.3);
  assert.equal(drawn.length, 32);
  assert.equal(new Set(drawn.map(q => q.id)).size, 32);
  assert.ok(drawn.every(q => !q.missingMedia && q.categories.includes("B")));
  assert.ok(drawn.slice(0, 20).every(q => q.kind === "basic"));
  assert.ok(drawn.slice(20).every(q => q.kind === "specialist"));
  for (const kind of ["basic", "specialist"]) {
    for (const [points, required] of Object.entries(RULES[kind].quotas)) {
      assert.equal(drawn.filter(q => q.kind === kind && q.points === Number(points)).length, required);
    }
  }
  assert.throws(() => drawExam(questions, "A"), /za mało pytań/);
});

test("only correct answers earn points, with 68 the lowest passing score", () => {
  const drawn = drawExam(questions, "B", () => 0.3);
  const answers = drawn.map(q => q.answer);
  const threePointQuestions = drawn.flatMap((q, i) => q.points === 3 ? [i] : []);
  assert.equal(markExam(drawn, answers).points, 74);
  answers[threePointQuestions[0]] = "N";
  delete answers[threePointQuestions[1]];
  const passing = markExam(drawn, answers);
  assert.equal(passing.points, 68);
  assert.equal(passing.passed, true);
  assert.equal(passing.rows[threePointQuestions[1]].answer, null);
  answers[threePointQuestions[2]] = "N";
  assert.equal(markExam(drawn, answers).passed, false);
});

test("specialist questions have a separate time limit in PJM mode", () => {
  assert.equal(answerTime("basic", true), 15);
  assert.equal(answerTime("specialist", false), 50);
  assert.equal(answerTime("specialist", true), 75);
});
