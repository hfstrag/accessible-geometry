// Interface strings. Feedback about the figure comes from the server, already translated.

const STRINGS = {
  fr: {
    title: "Géométrie à la voix",
    languageLabel: "Langue",
    boardTitle: "Figure",
    talkIdle: "Appuyer pour parler",
    talkRecording: "J'écoute… appuyer pour envoyer",
    talkHint: "Ou maintenir la touche Espace pendant que vous parlez.",
    textLabel: "Ou écrire une commande",
    send: "Envoyer",
    historyTitle: "Historique",
    notConfigured:
      "La clé GROQ_API_KEY n'est pas configurée sur le serveur : les commandes ne fonctionneront pas.",
    loading: "Chargement de GeoGebra…",
    ready: "Prêt.",
    listening: "J'écoute…",
    thinking: "Je réfléchis…",
    youSaid: "Vous",
    micDenied: "Le micro n'est pas accessible. Vérifiez l'autorisation du navigateur.",
    serverError: "Le serveur ne répond pas. Réessayez.",
    executionFailed: "GeoGebra n'a pas pu exécuter la commande. Rien n'a été modifié.",
  },
  en: {
    title: "Voice Geometry",
    languageLabel: "Language",
    boardTitle: "Figure",
    talkIdle: "Press to talk",
    talkRecording: "Listening… press to send",
    talkHint: "Or hold the Space key while you speak.",
    textLabel: "Or type a command",
    send: "Send",
    historyTitle: "History",
    notConfigured: "GROQ_API_KEY is not configured on the server: commands will not work.",
    loading: "Loading GeoGebra…",
    ready: "Ready.",
    listening: "Listening…",
    thinking: "Thinking…",
    youSaid: "You",
    micDenied: "The microphone is not available. Check the browser permission.",
    serverError: "The server is not responding. Try again.",
    executionFailed: "GeoGebra could not run the command. Nothing was changed.",
  },
};

export const LANGUAGES = Object.keys(STRINGS);

export function t(language, key) {
  return STRINGS[language]?.[key] ?? STRINGS.fr[key] ?? key;
}

/** Translate every element marked with data-i18n. */
export function applyTranslations(language) {
  document.documentElement.lang = language;
  for (const element of document.querySelectorAll("[data-i18n]")) {
    element.textContent = t(language, element.dataset.i18n);
  }
}
