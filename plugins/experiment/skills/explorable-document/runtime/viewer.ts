import validateSnapshot from "./snapshot-validator";

type Payload = {
  descriptor: { title: string; summary: string; handoff?: unknown };
  html: string;
  schema: object | null;
};
function element<T extends HTMLElement>(id: string): T {
  const result = document.getElementById(id);
  if (!result) throw Error(`Missing viewer element: ${id}`);
  return result as T;
}
const status = element("status");
const frame = element<HTMLIFrameElement>("document");
const share = element<HTMLButtonElement>("share");
const review = element<HTMLDialogElement>("review");
const submit = element<HTMLButtonElement>("submit");
const comment = element<HTMLTextAreaElement>("comment");
const receipt = element("receipt");
const theme = element<HTMLSelectElement>("theme");
review.addEventListener("keydown", (event) => {
  if (event.key !== "Tab") return;
  const controls = [
    ...review.querySelectorAll<HTMLElement>(
      "button,textarea,a[href],select,input",
    ),
  ].filter(
    (control) =>
      !control.hasAttribute("disabled") && control.offsetParent !== null,
  );
  const first = controls[0];
  const last = controls[controls.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last?.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first?.focus();
  }
});
const system = matchMedia("(prefers-color-scheme: dark)");
const session = crypto.randomUUID();
let port: MessagePort;
let pending = "";
let timer: ReturnType<typeof setTimeout>;
let snapshot: unknown;
let frozenBody = "";
let key = "";
let capability = "";
let artifactId = "portable";
let buildHash = "";
let verify: ((value: unknown) => boolean) | undefined;
function send(value: Record<string, unknown>): void {
  port?.postMessage({ ...value, version: 1, session });
}
function applyTheme(): void {
  const value =
    theme.value === "system"
      ? system.matches
        ? "dark"
        : "light"
      : theme.value;
  document.documentElement.dataset.theme = value;
  send({ type: "theme", value });
}
theme.onchange = applyTheme;
system.onchange = applyTheme;
applyTheme();
function requestSnapshot(): void {
  pending = crypto.randomUUID();
  share.disabled = true;
  status.textContent = "Requesting a snapshot…";
  send({ type: "snapshot", request: pending });
  clearTimeout(timer);
  timer = setTimeout(() => {
    pending = "";
    share.disabled = false;
    status.textContent =
      "Snapshot provider did not respond. Exploration is still available.";
  }, 5000);
}
share.onclick = requestSnapshot;
review.addEventListener("close", () => share.focus());
element("refresh").onclick = requestSnapshot;
element("cancel").onclick = () => review.close();
element("close-link").onclick = () =>
  element<HTMLDialogElement>("navigation").close();
function body(): string {
  if (!frozenBody)
    frozenBody = JSON.stringify({ snapshot, comment: comment.value });
  return frozenBody;
}
element("download").onclick = () => {
  const blob = new Blob(
    [
      JSON.stringify(
        {
          artifact_id: artifactId,
          rendered_hash: buildHash,
          ...JSON.parse(
            frozenBody || JSON.stringify({ snapshot, comment: comment.value }),
          ),
        },
        null,
        2,
      ),
    ],
    { type: "application/json" },
  );
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${artifactId}-snapshot.json`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  receipt.textContent =
    "Snapshot download requested. It has not been saved for the agent.";
};
submit.onclick = async () => {
  submit.disabled = true;
  comment.disabled = true;
  receipt.textContent = "Saving…";
  try {
    const response = await fetch("./api/submissions", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${capability}`,
        "Idempotency-Key": key,
      },
      body: body(),
    });
    const value = await response.json();
    if (!response.ok) throw Error(value.message || "Save failed");
    receipt.textContent = `Saved for the agent · ${value.submission_id}`;
  } catch (error) {
    receipt.textContent = `Not saved: ${String(error)}. Retry sends the same frozen copy, or download it.`;
    submit.disabled = false;
  }
};
async function start(): Promise<void> {
  const payload: Payload = await (await fetch("./document.json")).json();
  const meta = await (await fetch("./artifact.json")).json();
  artifactId = meta.id;
  buildHash = meta.rendered_hash;
  document.title = payload.descriptor.title;
  element("title").textContent = payload.descriptor.title;
  element("summary").textContent = payload.descriptor.summary;
  element("identity").textContent =
    `${artifactId} · ${meta.source_format} · runtime ${meta.toolchain_version}`;
  element("fallback").textContent = payload.descriptor.summary;
  // The session credential exists only in the URL fragment, never in frame data or exports.
  const fragment = new URLSearchParams(location.hash.slice(1));
  const candidate =
    fragment.get("session") ||
    sessionStorage.getItem(`explorable:${artifactId}`);
  history.replaceState(null, "", location.pathname);
  if (candidate && payload.schema) {
    const response = await fetch("./api/session", {
      headers: { Authorization: `Bearer ${candidate}` },
    });
    if (response.ok) {
      capability = candidate;
      sessionStorage.setItem(`explorable:${artifactId}`, candidate);
    }
  }
  if (payload.schema) {
    verify = validateSnapshot;
    share.hidden = false;
    share.textContent = capability ? "Review snapshot" : "Download snapshot";
    submit.hidden = !capability;
  }
  const readyTimer = setTimeout(() => {
    status.textContent =
      "Document did not become ready. The summary below remains available.";
    element("fallback").hidden = false;
  }, 10000);
  frame.onload = () => {
    const channel = new MessageChannel();
    port?.close();
    port = channel.port1;
    port.onmessage = (e) => {
      const data = e.data;
      if (
        data?.version !== 1 ||
        data?.session !== session ||
        typeof data.type !== "string"
      )
        return;
      if (data.type === "ready") {
        clearTimeout(readyTimer);
        status.textContent = `Ready · browser checks: ${meta.browser_status}. Inputs stay in memory. Reload resets them.`;
        element("fallback").hidden = true;
        applyTheme();
      } else if (
        data.type === "size" &&
        Number.isFinite(data.height) &&
        data.height >= 0 &&
        data.height <= 30000
      ) {
        frame.style.height = `${Math.max(300, data.height + 24)}px`;
      } else if (
        data.type === "snapshot" &&
        verify &&
        pending &&
        data.request === pending
      ) {
        clearTimeout(timer);
        pending = "";
        share.disabled = false;
        const serialized = JSON.stringify(data.value);
        if (
          !serialized ||
          new TextEncoder().encode(serialized).length > 900000 ||
          !verify(data.value)
        ) {
          status.textContent =
            "Snapshot rejected: values do not match this revision's schema.";
          return;
        }
        snapshot = JSON.parse(serialized);
        frozenBody = "";
        key = crypto.randomUUID();
        element("snapshot").textContent = JSON.stringify(snapshot, null, 2);
        comment.value = "";
        comment.disabled = false;
        submit.disabled = false;
        receipt.textContent = "";
        status.textContent = "Snapshot ready for review.";
        if (!review.open) review.showModal();
      } else if (data.type === "error" && typeof data.message === "string") {
        if (data.request && data.request !== pending) return;
        clearTimeout(timer);
        pending = "";
        share.disabled = false;
        status.textContent = `Document error: ${data.message.slice(0, 1000)}`;
        element("fallback").hidden = false;
      } else if (
        data.type === "link" &&
        typeof data.href === "string" &&
        data.href.length <= 2000 &&
        /^https?:\/\//.test(data.href)
      ) {
        const link = element<HTMLAnchorElement>("link");
        link.href = data.href;
        link.textContent = data.href;
        const dialog = element<HTMLDialogElement>("navigation");
        if (!dialog.open) dialog.showModal();
      }
    };
    frame.contentWindow?.postMessage(
      { type: "init", version: 1, session },
      "*",
      [channel.port2],
    );
  };
  frame.srcdoc = payload.html;
}
start().catch((error) => {
  status.textContent = `Unable to open document: ${String(error)}`;
  element("fallback").hidden = false;
});
