// Run with Quarto's bundled Deno and Mermaid; only parser input comes from the document.
const [bundlePath, diagramsPath] = Deno.args;
let bundle = Deno.readTextFileSync(bundlePath);
// Parsing labeled flowcharts also calls DOMPurify, whose browser DOM does not
// exist in Deno. This syntax-only adapter supplies identity text handling; it
// never renders HTML. The actual browser bundle retains strict DOMPurify.
const binding = 'purify = createDOMPurify();';
if (bundle.split(binding).length !== 2) throw new Error('Unsupported Mermaid parser bundle; reverify the Quarto version.');
bundle = bundle.replace(binding, 'purify = { sanitize: (text) => text, addHook: () => {} };');
// The browser bundle expects its top-level var to be a global property. In a
// Function scope it is local; adapt that one binding without altering the parser.
new Function(bundle.replace('globalThis.__esbuild_esm_mermaid_nm[', '__esbuild_esm_mermaid_nm['))();
const mermaid = globalThis.mermaid;
mermaid.initialize({ startOnLoad: false, securityLevel: 'strict' });
const results = [];
for (const [index, text] of JSON.parse(Deno.readTextFileSync(diagramsPath)).entries()) {
  try {
    await mermaid.parse(text);
    results.push({ index, valid: true });
  } catch (error) {
    results.push({ index, valid: false, message: String(error).slice(0, 1200) });
  }
}
console.log(JSON.stringify(results));
