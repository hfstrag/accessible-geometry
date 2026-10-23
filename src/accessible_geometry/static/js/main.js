// Entry point: wires push-to-talk, the backend and GeoGebra together.

import { ApiError, getHealth, sendTextCommand, sendVoiceCommand } from "./api.js";
import { GeoGebraBoard } from "./geogebra.js";
import { LANGUAGES, applyTranslations, t } from "./i18n.js";
import { Recorder } from "./recorder.js";
import { speak, stopSpeaking } from "./speech.js";

const LANGUAGE_STORAGE_KEY = "accessible-geometry.language";

const elements = {
  language: document.getElementById("language"),
  talkButton: document.getElementById("talk-button"),
  talkLabel: document.getElementById("talk-label"),
  status: document.getElementById("status"),
  history: document.getElementById("history"),
  textForm: document.getElementById("text-form"),
  textInput: document.getElementById("text-input"),
  configWarning: document.getElementById("config-warning"),
  ggbContainer: document.getElementById("ggb-container"),
};

const recorder = new Recorder();
let board = null;
let language = loadLanguage();
let busy = false;

function loadLanguage() {
  try {
    const saved = localStorage.getItem(LANGUAGE_STORAGE_KEY);
    if (LANGUAGES.includes(saved)) return saved;
  } catch {
    // Storage unavailable (private mode...): fall back to the default.
  }
  return "fr";
}

function setLanguage(value) {
  language = value;
  elements.language.value = value;
  applyTranslations(value);
  board?.setLanguage(value);
  try {
    localStorage.setItem(LANGUAGE_STORAGE_KEY, value);
  } catch {
    // Not critical.
  }
}

function setStatus(key) {
  elements.status.textContent = key ? t(language, key) : "";
}

function addHistory(text, className) {
  const item = document.createElement("li");
  item.textContent = text;
  if (className) item.className = className;
  elements.history.append(item);
}

function updateTalkButton() {
  const recording = recorder.isRecording;
  elements.talkButton.setAttribute("aria-pressed", String(recording));
  elements.talkButton.disabled = busy || !board;
  elements.talkLabel.textContent = t(language, recording ? "talkRecording" : "talkIdle");
}

function report(message, isError = false) {
  addHistory(message, isError ? "error" : undefined);
  speak(message, language);
}

async function startRecording() {
  if (busy || !board || recorder.isRecording) return;
  stopSpeaking();
  try {
    await recorder.start();
    setStatus("listening");
  } catch {
    report(t(language, "micDenied"), true);
  }
  updateTalkButton();
}

async function stopRecordingAndSend() {
  if (!recorder.isRecording) return;
  const audio = await recorder.stop();
  updateTalkButton();
  if (!audio) {
    setStatus("ready");
    return;
  }
  await runCommand(() => sendVoiceCommand(audio, language, board.readState()));
}

async function runCommand(send) {
  busy = true;
  updateTalkButton();
  setStatus("thinking");
  try {
    const result = await send();
    if (result.transcript) addHistory(`${t(language, "youSaid")} : ${result.transcript}`, "said");
    const outcome = result.steps.length ? board.execute(result.steps) : { ok: true };
    if (!outcome.ok) {
      console.warn("GeoGebra rejected command:", outcome.failedCommand);
      report(t(language, "executionFailed"), true);
    } else {
      report(result.message, result.status === "rejected");
    }
  } catch (error) {
    console.error(error);
    report(error instanceof ApiError ? error.message : t(language, "serverError"), true);
  } finally {
    busy = false;
    setStatus("ready");
    updateTalkButton();
  }
}

function isTypingTarget(target) {
  return target instanceof HTMLElement && target.matches("input, textarea, select");
}

function bindEvents() {
  elements.language.addEventListener("change", (event) => setLanguage(event.target.value));

  // Button: press once to start, once more to send (easier than holding for many students).
  elements.talkButton.addEventListener("click", () => {
    recorder.isRecording ? stopRecordingAndSend() : startRecording();
  });

  // Space: hold to talk. Captured on window so it works even when GeoGebra has focus.
  window.addEventListener(
    "keydown",
    (event) => {
      if (event.code !== "Space" || isTypingTarget(event.target)) return;
      event.preventDefault();
      event.stopPropagation();
      if (!event.repeat) startRecording();
    },
    { capture: true },
  );
  window.addEventListener(
    "keyup",
    (event) => {
      if (event.code !== "Space" || isTypingTarget(event.target)) return;
      event.preventDefault();
      event.stopPropagation();
      stopRecordingAndSend();
    },
    { capture: true },
  );

  elements.textForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const text = elements.textInput.value.trim();
    if (!text || busy || !board) return;
    elements.textInput.value = "";
    runCommand(() => sendTextCommand(text, language, board.readState()));
  });
}

async function checkHealth() {
  try {
    const health = await getHealth();
    elements.configWarning.hidden = health.ai_configured;
  } catch {
    report(t(language, "serverError"), true);
  }
}

async function init() {
  setLanguage(language);
  bindEvents();
  updateTalkButton();
  setStatus("loading");
  checkHealth();
  board = await GeoGebraBoard.create(elements.ggbContainer, language);
  setStatus("ready");
  updateTalkButton();
}

init();
