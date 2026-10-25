let provider: (() => unknown) | undefined;
let port: MessagePort | undefined;
let session = "";
let enabled = false;
export function registerSnapshot(value: () => unknown): () => void {
  provider = value;
  return () => {
    if (provider === value) provider = undefined;
  };
}
function send(value: Record<string, unknown>): void {
  port?.postMessage({ ...value, version: 1, session });
}
export function connect(handoff: boolean): void {
  enabled = handoff;
  window.addEventListener("message", (e) => {
    if (
      port ||
      e.source !== parent ||
      e.data?.type !== "init" ||
      e.data.version !== 1 ||
      typeof e.data.session !== "string" ||
      !e.ports[0]
    )
      return;
    session = e.data.session;
    port = e.ports[0];
    port.onmessage = (e) => {
      const data = e.data;
      if (data?.session !== session || data?.version !== 1) return;
      if (data.type === "theme" && ["dark", "light"].includes(data.value))
        document.documentElement.dataset.theme = data.value;
      if (
        enabled &&
        data.type === "snapshot" &&
        typeof data.request === "string" &&
        data.request.length <= 64
      ) {
        try {
          if (!provider)
            throw Error(
              "No snapshot provider registered. Exploration is still available.",
            );
          const json = JSON.stringify(provider());
          if (!json || new TextEncoder().encode(json).length > 900000)
            throw Error("Snapshot exceeds the review budget.");
          send({
            type: "snapshot",
            request: data.request,
            value: JSON.parse(json),
          });
        } catch (error) {
          send({
            type: "error",
            request: data.request,
            message: String(error).slice(0, 1000),
          });
        }
      }
    };
    send({ type: "ready" });
    new ResizeObserver(() =>
      send({
        type: "size",
        height: Math.min(
          30000,
          Math.ceil(document.body.getBoundingClientRect().height),
        ),
      }),
    ).observe(document.body);
  });
  document.addEventListener("click", (e) => {
    const link = e.target instanceof Element ? e.target.closest("a") : null;
    if (!link) return;
    const href = link.getAttribute("href") || "";
    if (href.startsWith("#")) return;
    e.preventDefault();
    if (e.isTrusted && /^https?:\/\//.test(href) && href.length <= 2000)
      send({ type: "link", href });
  });
  window.addEventListener("error", (e) =>
    send({ type: "error", message: e.message.slice(0, 1000) }),
  );
}
