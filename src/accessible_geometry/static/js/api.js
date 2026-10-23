// Calls to the Python backend.

export class ApiError extends Error {}

async function parse(response) {
  if (!response.ok) {
    let detail = response.statusText;
    try {
      detail = (await response.json()).detail ?? detail;
    } catch {
      // Not JSON: keep the status text.
    }
    throw new ApiError(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return response.json();
}

export async function getHealth() {
  return parse(await fetch("/api/health"));
}

export async function sendVoiceCommand(audioBlob, language, state) {
  const form = new FormData();
  const extension = audioBlob.type.includes("ogg") ? "ogg" : "webm";
  form.append("audio", audioBlob, `speech.${extension}`);
  form.append("language", language);
  form.append("state", JSON.stringify(state));
  return parse(await fetch("/api/voice", { method: "POST", body: form }));
}

export async function sendTextCommand(text, language, state) {
  return parse(
    await fetch("/api/command", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, language, state }),
    }),
  );
}
