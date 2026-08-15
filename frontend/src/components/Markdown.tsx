import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/** El texto del asistente, renderizado.
 *
 * Escribe en markdown por costumbre: negritas, listas y hasta tablas. Sin
 * renderizarlo, el usuario ve los asteriscos y los pipes, que es peor que si
 * no los hubiera escrito. */
export function Markdown({ text, inverted = false }: { text: string; inverted?: boolean }) {
  const muted = inverted ? "text-bone-100/75" : "text-ink-400";
  return (
    <div className="text-sm leading-relaxed [&>*:first-child]:mt-0 [&>*:last-child]:mb-0">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({ children }) => <p className="my-2">{children}</p>,
          strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
          em: ({ children }) => <em className="italic">{children}</em>,
          ul: ({ children }) => <ul className="my-2 ml-4 list-disc space-y-0.5">{children}</ul>,
          ol: ({ children }) => (
            <ol className="my-2 ml-4 list-decimal space-y-0.5">{children}</ol>
          ),
          li: ({ children }) => <li className="pl-0.5">{children}</li>,
          code: ({ children }) => (
            <code
              className={`rounded px-1 py-0.5 font-mono text-[0.85em] ${
                inverted ? "bg-bone-50/15" : "bg-bone-200"
              }`}
            >
              {children}
            </code>
          ),
          pre: ({ children }) => (
            <pre className="my-2 overflow-x-auto rounded bg-bone-200 p-2 text-xs">{children}</pre>
          ),
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noreferrer" className="underline">
              {children}
            </a>
          ),
          h1: ({ children }) => <p className="my-2 font-semibold">{children}</p>,
          h2: ({ children }) => <p className="my-2 font-semibold">{children}</p>,
          h3: ({ children }) => <p className="my-2 font-semibold">{children}</p>,
          hr: () => <hr className={`my-3 border-t ${inverted ? "border-bone-50/20" : "border-bone-300"}`} />,
          blockquote: ({ children }) => (
            <blockquote className={`my-2 border-l-2 pl-3 ${muted}`}>{children}</blockquote>
          ),
          // El modelo devuelve tablas markdown cuando le pides datos en texto.
          table: ({ children }) => (
            <div className="my-2 overflow-x-auto">
              <table className="w-full border-collapse text-xs">{children}</table>
            </div>
          ),
          th: ({ children }) => (
            <th
              className={`border-b px-2 py-1 text-left font-medium ${
                inverted ? "border-bone-50/25" : "border-bone-300"
              }`}
            >
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td
              className={`border-b px-2 py-1 ${
                inverted ? "border-bone-50/10" : "border-bone-200"
              }`}
            >
              {children}
            </td>
          ),
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}
