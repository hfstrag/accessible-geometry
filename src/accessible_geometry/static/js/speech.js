// Spoken feedback with the browser's built-in text-to-speech.

const VOICE_LANGUAGES = { fr: "fr-FR", en: "en-US" };

/** Make notation readable aloud: "[AB]" → "A B", so letters are not read as a word. */
function forSpeech(text) {
  return text
    .replace(/[[\]]/g, " ")
    .replace(/\b[A-Z]{2,4}\b/g, (letters) => letters.split("").join(" "))
    .replace(/\s+/g, " ")
    .trim();
}

export function speak(text, language) {
  if (!("speechSynthesis" in window) || !text) return;
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(forSpeech(text));
  utterance.lang = VOICE_LANGUAGES[language] ?? language;
  window.speechSynthesis.speak(utterance);
}

export function stopSpeaking() {
  if ("speechSynthesis" in window) window.speechSynthesis.cancel();
}
