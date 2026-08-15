import type { ReactNode } from "react";

/* Resaltado de Python, hecho a mano.
 *
 * Una librería de resaltado trae decenas de lenguajes y su propio tema de
 * colores, y aquí solo se muestra un lenguaje y el tema tiene que ser el de la
 * casa: tonos apagados sobre papel, nada de neón sobre negro. Cincuenta líneas
 * de tokenizador salen más baratas y encajan.
 *
 * No pretende ser un analizador correcto: solo tiene que acertar en el código
 * que genera `explain.py`, que es limitado y conocido.
 */

const KEYWORDS = new Set([
  "import", "as", "from", "lambda", "def", "return", "if", "else", "for", "in",
  "and", "or", "not", "None", "True", "False",
]);

type Kind = "comment" | "string" | "number" | "keyword" | "call" | "plain";

const COLORS: Record<Kind, string> = {
  // Verde salvia: presente pero se aparta de la vista.
  comment: "text-ok",
  string: "text-series-5",
  number: "text-series-2",
  keyword: "text-clay-600",
  call: "text-ink-900",
  plain: "text-ink-700",
};

const PATTERN = new RegExp(
  [
    "(#[^\\n]*)", // comentario
    "('(?:[^'\\\\]|\\\\.)*'|\"(?:[^\"\\\\]|\\\\.)*\")", // cadena
    "(\\b\\d+(?:\\.\\d+)?\\b)", // número
    "([A-Za-z_][A-Za-z0-9_]*)(?=\\s*\\()", // llamada
    "([A-Za-z_][A-Za-z0-9_]*)", // palabra
  ].join("|"),
  "g",
);

function tokenize(code: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  let last = 0;
  let key = 0;

  for (const match of code.matchAll(PATTERN)) {
    const [text, comment, string, number, call, word] = match;
    const start = match.index;
    if (start > last) {
      nodes.push(code.slice(last, start));
    }

    let kind: Kind = "plain";
    if (comment) kind = "comment";
    else if (string) kind = "string";
    else if (number) kind = "number";
    else if (call) kind = "call";
    else if (word) kind = KEYWORDS.has(word) ? "keyword" : "plain";

    nodes.push(
      kind === "plain" ? (
        text
      ) : (
        <span key={key++} className={COLORS[kind]}>
          {text}
        </span>
      ),
    );
    last = start + text.length;
  }
  nodes.push(code.slice(last));
  return nodes;
}

export function Python({ code }: { code: string }) {
  return (
    <code className="font-mono text-[11px] leading-relaxed text-ink-700">
      {tokenize(code)}
    </code>
  );
}
