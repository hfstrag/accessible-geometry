// Wrapper around the GeoGebra Apps API (https://geogebra.github.io/docs/reference/en/GeoGebra_Apps_API/).

const DEPLOY_SCRIPT = "https://www.geogebra.org/apps/deployggb.js";

function loadScript(src) {
  return new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = src;
    script.onload = resolve;
    script.onerror = () => reject(new Error(`Could not load ${src}`));
    document.head.append(script);
  });
}

export class GeoGebraBoard {
  constructor(api) {
    this.api = api;
  }

  /** Load GeoGebra into `container` and resolve once the applet is ready. */
  static async create(container, language) {
    await loadScript(DEPLOY_SCRIPT);
    return new Promise((resolve) => {
      const applet = new window.GGBApplet(
        {
          appName: "classic",
          perspective: "AG", // Algebra view (list of objects) + Graphics view.
          width: container.clientWidth,
          height: container.clientHeight,
          language,
          showToolBar: false,
          showMenuBar: false,
          showAlgebraInput: false,
          showResetIcon: false,
          enableRightClick: false,
          enableShiftDragZoom: true,
          enableUndoRedo: true,
          useBrowserForJS: false,
          appletOnLoad: (api) => {
            api.setErrorDialogsActive(false);
            api.setUndoPoint();
            resolve(new GeoGebraBoard(api));
          },
        },
        true,
      );
      applet.inject(container.id);
    });
  }

  setLanguage(language) {
    this.api.setLanguage(language);
  }

  /** Snapshot of the construction, in the shape the server expects (ConstructionState). */
  readState() {
    const objects = this.api.getAllObjectNames().map((name) => {
      const type = this.api.getObjectType(name);
      const object = {
        name,
        type,
        definition: this.api.getCommandString(name, false) || null,
        value: this.api.getValueString(name, false) || null,
      };
      if (type === "point") {
        object.x = this.api.getXcoord(name);
        object.y = this.api.getYcoord(name);
      }
      return object;
    });
    return { objects };
  }

  /**
   * Execute the steps planned by the server. All-or-nothing: if a command fails,
   * the objects created by this batch are deleted again.
   * Each batch becomes a single undo step.
   */
  execute(steps) {
    const created = [];
    let dirty = false;

    for (const step of steps) {
      if (step.op === "eval") {
        const before = new Set(this.api.getAllObjectNames());
        if (!this.api.evalCommand(step.command)) {
          created.reverse().forEach((name) => this.api.deleteObject(name));
          return { ok: false, failedCommand: step.command };
        }
        created.push(...this.api.getAllObjectNames().filter((name) => !before.has(name)));
        dirty = true;
      } else if (step.op === "undo" || step.op === "redo") {
        if (dirty) {
          this.api.setUndoPoint();
          dirty = false;
        }
        step.op === "undo" ? this.api.undo() : this.api.redo();
      }
    }
    if (dirty) this.api.setUndoPoint();
    return { ok: true };
  }
}
