// Microphone recording for push-to-talk.

const MIN_DURATION_MS = 300;

export class Recorder {
  #stream = null;
  #recorder = null;
  #chunks = [];
  #startedAt = 0;

  get isRecording() {
    return this.#recorder?.state === "recording";
  }

  async start() {
    if (this.isRecording) return;
    // The stream is kept open after the first press so that the start of
    // the next sentence is not cut off while the microphone wakes up.
    this.#stream ??= await navigator.mediaDevices.getUserMedia({ audio: true });
    this.#chunks = [];
    this.#recorder = new MediaRecorder(this.#stream);
    this.#recorder.ondataavailable = (event) => {
      if (event.data.size > 0) this.#chunks.push(event.data);
    };
    this.#recorder.start();
    this.#startedAt = performance.now();
  }

  /** Stop recording. Resolves to the audio Blob, or null if the press was too short. */
  stop() {
    const recorder = this.#recorder;
    if (!recorder || recorder.state !== "recording") return Promise.resolve(null);
    const tooShort = performance.now() - this.#startedAt < MIN_DURATION_MS;
    return new Promise((resolve) => {
      recorder.onstop = () => {
        resolve(tooShort ? null : new Blob(this.#chunks, { type: recorder.mimeType }));
      };
      recorder.stop();
    });
  }
}
